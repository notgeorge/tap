"""The samsite compliance collector.

A ``CollectorBase`` subclass that fetches samsite's signed ``/.well-known/``
compliance artifacts over HTTPS, decomposes them into the
``fedramp_20x_ksi`` compliance-artifact graph, and submits one GRIFT batch.
Unlike the boto3 collector it needs no cloud credentials — it reads public
URLs.

Spec: plugins/samsite/specs/spec-samsite-compliance-collector-v0.md.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any

from plugins.sigstore_core.decompose import bundle_to_grift_fragment
from plugins.sigstore_core.verify import GitHubWorkflowPolicy, verify_bundle
from tap_cares.collectors.base import CollectorBase

from . import sigstore_link
from .batch import assemble_batch
from .decompose import (
    decompose_compliance_artifact,
    decompose_ksi_signal,
    decompose_vdr_report,
)
from .manifest import ArtifactManifestError, load_manifest

_SITE_RUN_STARTED = "be33"
_SITE_MANIFEST_LOADED = "3a92"
_SITE_RUN_FINISHED = "c94a"
_SITE_ARTIFACT_FETCHED = "c7ac"
_SITE_ARTIFACT_FETCH_FAILED = "147c"
_SITE_BUNDLE_FETCH_FAILED = "f159"
_SITE_MANIFEST_INVALID = "8c42"
_SITE_DECOMPOSE_FAILED = "55c8"
_SITE_BATCH_SUBMITTED = "0772"
_SITE_NOTHING_TO_SUBMIT = "12f5"
_SITE_VERIFY_PASSED = "8acc"
_SITE_VERIFY_FAILED = "9394"
_SITE_SIGNATURE_GRAPH = "f587"
_SITE_SIGNATURE_NO_WORKFLOW = "ce2f"

_FETCH_TIMEOUT_SECONDS = 30
_USER_AGENT = "tap-samsite-compliance-collector"
_COLLECTOR_SOURCE = "plugins.samsite.collectors.compliance_collector"


class SamsiteComplianceCollectorError(Exception):
    """Unrecoverable samsite compliance collector failure."""


def _fetch(url: str) -> bytes:
    """HTTP GET — return the response body, or raise.

    HTTPS-only: a non-HTTPS URL is refused before the request is made (the
    artifacts are public TLS-served documents; there is no reason to fetch
    one over plaintext).
    """
    if not url.startswith("https://"):
        raise ValueError(f"Refusing to fetch non-HTTPS URL: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(
        request, timeout=_FETCH_TIMEOUT_SECONDS
    ) as response:  # noqa: S310 — HTTPS-guarded above
        return response.read()


class SamsiteComplianceCollector(CollectorBase):
    """Fetches samsite's signed ``/.well-known/`` compliance artifacts and lands
    them on the grid as the fedramp_20x_ksi compliance-artifact subgraph."""

    def _abort(self, site: str, code: str, message: str) -> None:
        """Record a structured error and raise to halt the run."""
        self.record_error(site, code, message)
        raise SamsiteComplianceCollectorError(message)

    def _emit_signature_graph(
        self,
        fetched_item: dict[str, Any],
        anchor_entity_id: str,
        policy: GitHubWorkflowPolicy,
        all_nodes: list[dict[str, Any]],
        all_edges: list[dict[str, Any]],
        seen_node_ids: set[str],
    ) -> None:
        """Merge one artifact's sigstore_core signature graph into the batch.

        Turns the verified bundle into a ``rekor_log_entry`` + ``sigstore_ca``
        upsert + ``CERT_ISSUED_BY``/``ATTESTED_BY`` (and ``SIGNED_BY_IDENTITY``
        when the signing workflow resolves to a single ``github_workflow``).
        No-op when no bundle came back or it was unparseable. The shared
        ``sigstore_ca`` node repeats across artifacts, so it's deduped by id.
        """
        result = fetched_item.get("verify_result")
        if result is None or result.parsed_bundle is None or not anchor_entity_id:
            return
        full_name, workflow_path = sigstore_link.parse_signing_san(result.signed_by)
        workflow_id = sigstore_link.resolve_workflow_entity_id(full_name, workflow_path) if full_name else None
        if workflow_id is None and result.signed_by:
            self.record_info(
                _SITE_SIGNATURE_NO_WORKFLOW,
                "SIGNING_WORKFLOW_UNRESOLVED",
                f"Signed by {result.signed_by} but no single github_workflow matched; " f"SIGNED_BY_IDENTITY omitted.",
                message_data={"signed_by": result.signed_by},
            )
        fragment = bundle_to_grift_fragment(
            result,
            anchor_entity_id=anchor_entity_id,
            policy=policy,
            dimensions={},
            signing_identity_entity_id=workflow_id,
        )
        nodes, edges = sigstore_link.fragment_to_envelopes(fragment)
        for node in nodes:
            nid = node["entity"]["entity_id"]
            if nid in seen_node_ids:
                continue
            seen_node_ids.add(nid)
            all_nodes.append(node)
        all_edges.extend(edges)
        self.record_info(
            _SITE_SIGNATURE_GRAPH,
            "SIGNATURE_GRAPH_EMITTED",
            f"{fetched_item['artifact']['name']}: rekor_log_entry emitted "
            f"(log_index={result.rekor_log_index or '<none>'}, verified={result.signature_verified}).",
            message_data={
                "artifact": fetched_item["artifact"]["name"],
                "rekor_log_index": result.rekor_log_index,
                "signed_by_identity": workflow_id,
            },
        )

    def run(self) -> None:
        self.record_info(_SITE_RUN_STARTED, "RUN_STARTED", "Samsite compliance collection started.")
        fetched_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        try:
            manifest = load_manifest()
        except ArtifactManifestError as exc:
            self._abort(_SITE_MANIFEST_INVALID, "MANIFEST_INVALID", str(exc))

        base_url = manifest["site_base_url"]
        artifacts = manifest["artifacts"]
        verification_policy = manifest["verification"]
        # One policy for the whole run — verify_bundle enforces it and
        # bundle_to_grift_fragment records it on the ATTESTED_BY edge.
        policy = GitHubWorkflowPolicy(
            oidc_issuer=verification_policy["oidc_issuer"],
            github_repository=verification_policy["github_repository"],
        )
        self.record_info(
            _SITE_MANIFEST_LOADED,
            "MANIFEST_LOADED",
            f"Artifact manifest loaded — {len(artifacts)} artifact(s) from {base_url}.",
            message_data={"site_base_url": base_url, "artifact_count": len(artifacts)},
        )

        # ---- Phase 1: fetch every artifact + its bundle -----------------------
        fetched: list[dict[str, Any]] = []
        for artifact in artifacts:
            name = artifact["name"]
            doc_url = base_url + artifact["path"]
            try:
                body = _fetch(doc_url)
            except (urllib.error.URLError, OSError, ValueError) as exc:
                self.record_warn(
                    _SITE_ARTIFACT_FETCH_FAILED,
                    "ARTIFACT_FETCH_FAILED",
                    f"Could not fetch {name} from {doc_url}: {exc}",
                    message_data={"artifact": name, "url": doc_url},
                )
                continue

            bundle_bytes: bytes | None = None
            bundle_path = artifact.get("bundle_path")
            if bundle_path:
                try:
                    bundle_bytes = _fetch(base_url + bundle_path)
                except (urllib.error.URLError, OSError, ValueError) as exc:
                    self.record_warn(
                        _SITE_BUNDLE_FETCH_FAILED,
                        "BUNDLE_FETCH_FAILED",
                        f"Fetched {name} but its signature bundle is unavailable: {exc}",
                        message_data={"artifact": name},
                    )

            # Verify the signature if a bundle came back — via sigstore_core,
            # the canonical verifier. Keep the back-compat verification dict for
            # the artifact decompose functions; keep the full VerificationResult
            # for the sigstore_core signature-graph emission in Phase 2.
            verification: dict[str, Any] | None = None
            verify_result: Any = None
            if bundle_bytes is not None:
                verify_result = verify_bundle(body, bundle_bytes, policy=policy)
                verification = sigstore_link.verification_dict(verify_result)
                if verification["signature_verified"] is True:
                    self.record_info(
                        _SITE_VERIFY_PASSED,
                        "SIGNATURE_VERIFIED",
                        f"{name}: signature verified, signed by {verification['signed_by'] or '<unknown>'}.",
                        message_data={"artifact": name, "signed_by": verification["signed_by"]},
                    )
                else:
                    self.record_warn(
                        _SITE_VERIFY_FAILED,
                        "SIGNATURE_UNVERIFIED",
                        f"{name}: signature {('failed verification' if verification['signature_verified'] is False else 'could not be verified')} "
                        f"(signed_by={verification['signed_by'] or '<unknown>'}).",
                        message_data={
                            "artifact": name,
                            "signature_verified": verification["signature_verified"],
                            "signed_by": verification["signed_by"],
                        },
                    )

            fetched.append(
                {
                    "artifact": artifact,
                    "body": body,
                    "bundle": bundle_bytes,
                    "verification": verification,
                    "verify_result": verify_result,
                }
            )
            self.record_info(
                _SITE_ARTIFACT_FETCHED,
                "ARTIFACT_FETCHED",
                f"Fetched {name} ({len(body)} bytes)"
                + ("" if bundle_bytes is None else f" + signature bundle ({len(bundle_bytes)} bytes)"),
                message_data={
                    "artifact": name,
                    "size_bytes": len(body),
                    "bundle_available": bundle_bytes is not None,
                },
            )

        # ---- Phase 2: decompose ---------------------------------------------
        # KSI signals first — they populate the system/component indexes that
        # the VDR decomposition uses for REFERENCES_SIGNAL and AFFECTS_RESOURCE.
        all_nodes: list[dict[str, Any]] = []
        all_edges: list[dict[str, Any]] = []
        ksi_signal_by_system: dict[str, str] = {}
        ksi_component_by_id: dict[str, str] = {}
        # Dedupes the shared sigstore_ca node across artifacts (one CA, many entries).
        sig_seen_node_ids: set[str] = set()

        for fetched_item in fetched:
            if fetched_item["artifact"]["handling"] != "ksi_signal":
                continue
            artifact = fetched_item["artifact"]
            try:
                signal = json.loads(fetched_item["body"])
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                self.record_warn(
                    _SITE_DECOMPOSE_FAILED,
                    "DECOMPOSE_FAILED",
                    f"Could not parse {artifact['name']} as JSON: {exc}",
                    message_data={"artifact": artifact["name"]},
                )
                continue
            decomp = decompose_ksi_signal(signal, verification=fetched_item.get("verification"))
            all_nodes.extend(decomp.nodes)
            all_edges.extend(decomp.edges)
            ksi_signal_by_system.update(decomp.ksi_signal_by_system)
            ksi_component_by_id.update(decomp.ksi_component_by_id)
            self._emit_signature_graph(
                fetched_item, decomp.anchor_entity_id, policy, all_nodes, all_edges, sig_seen_node_ids
            )

        for fetched_item in fetched:
            if fetched_item["artifact"]["handling"] != "vdr_report":
                continue
            artifact = fetched_item["artifact"]
            try:
                report = json.loads(fetched_item["body"])
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                self.record_warn(
                    _SITE_DECOMPOSE_FAILED,
                    "DECOMPOSE_FAILED",
                    f"Could not parse {artifact['name']} as JSON: {exc}",
                    message_data={"artifact": artifact["name"]},
                )
                continue
            decomp = decompose_vdr_report(
                report,
                ksi_signal_by_system=ksi_signal_by_system,
                ksi_component_by_id=ksi_component_by_id,
                verification=fetched_item.get("verification"),
            )
            all_nodes.extend(decomp.nodes)
            all_edges.extend(decomp.edges)
            self._emit_signature_graph(
                fetched_item, decomp.anchor_entity_id, policy, all_nodes, all_edges, sig_seen_node_ids
            )

        for fetched_item in fetched:
            artifact = fetched_item["artifact"]
            if artifact["handling"] != "compliance_artifact":
                continue
            decomp = decompose_compliance_artifact(
                body=fetched_item["body"],
                artifact_kind=artifact["artifact_kind"],
                source_url=base_url + artifact["path"],
                fetched_at=fetched_at,
                content_format=artifact["content_format"],
                verification=fetched_item.get("verification"),
            )
            all_nodes.extend(decomp.nodes)
            all_edges.extend(decomp.edges)
            self._emit_signature_graph(
                fetched_item, decomp.anchor_entity_id, policy, all_nodes, all_edges, sig_seen_node_ids
            )

        # ---- Phase 3: assemble + submit -------------------------------------
        if not all_nodes:
            self.summary = "No artifacts decomposed; nothing to submit."
            self.record_warn(
                _SITE_NOTHING_TO_SUBMIT,
                "NOTHING_TO_SUBMIT",
                self.summary,
            )
            return

        document = assemble_batch(
            source=_COLLECTOR_SOURCE,
            manifest_version=manifest["manifest_version"],
            site_base_url=base_url,
            nodes=all_nodes,
            edges=all_edges,
        )
        self.submit_grift(document)

        # Brief per-type tally for the summary.
        from collections import Counter

        node_tally = Counter(env["entity"]["entity_type"] for env in all_nodes)
        edge_tally = Counter(env["entity"]["entity_type"] for env in all_edges)
        node_breakdown = ", ".join(f"{count} {entity_type}" for entity_type, count in sorted(node_tally.items()))
        edge_breakdown = ", ".join(f"{count} {entity_type}" for entity_type, count in sorted(edge_tally.items()))
        self.summary = (
            f"Fetched {len(fetched)}/{len(artifacts)} artifacts; "
            f"submitted {len(all_nodes)} node(s) + {len(all_edges)} edge(s)."
        )
        self.record_info(
            _SITE_BATCH_SUBMITTED,
            "BATCH_SUBMITTED",
            f"GRIFT batch submitted — nodes: {node_breakdown}; edges: {edge_breakdown or 'none'}.",
            message_data={
                "node_counts": dict(node_tally),
                "edge_counts": dict(edge_tally),
            },
        )
        self.record_info(_SITE_RUN_FINISHED, "RUN_FINISHED", self.summary)
