"""Glue between the samsite compliance collector and ``sigstore_core``.

The collector fetches signed ``/.well-known/`` artifacts + their Sigstore
bundles, verifies them with ``sigstore_core.verify_bundle``, and turns each
verified bundle into transparency-log graph data with
``sigstore_core.bundle_to_grift_fragment``. This module owns the consumer-side
wiring that sigstore_core deliberately leaves to its callers:

- parsing the signing-cert SAN URI into ``(full_name, path)``,
- resolving that to a ``github_workflow`` entity id via Gryphon (so the
  ``SIGNED_BY_IDENTITY`` edge points at the workflow that signed — a
  cross-plugin *read*, the caller's job per req-sigstore-core-edges-5),
- translating sigstore_core's ``GriftFragment`` into the node/edge envelope
  shape this collector's batch assembler expects,
- and adapting a ``VerificationResult`` into the back-compat verification dict
  the artifact decompose functions still stamp onto their nodes.

Spec: plugins/samsite/specs/spec-samsite-compliance-collector-v0.md.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_GITHUB_PREFIX = "https://github.com/"


def parse_signing_san(uri: str) -> tuple[str | None, str | None]:
    """Split a Fulcio SAN URI into ``(full_name, workflow_path)``.

    The GitHub Actions signing identity looks like
    ``https://github.com/<owner>/<repo>/.github/workflows/<file>@<ref>``.
    Returns ``(None, None)`` for anything that isn't a github.com workflow URI.
    """
    if not uri or not uri.startswith(_GITHUB_PREFIX):
        return None, None
    rest = uri[len(_GITHUB_PREFIX) :].split("@", 1)[0]
    parts = rest.split("/")
    if len(parts) < 3:
        return None, None
    full_name = "/".join(parts[:2])
    workflow_path = "/".join(parts[2:])
    return full_name, workflow_path


def resolve_workflow_entity_id(full_name: str, workflow_path: str) -> str | None:
    """Return the ``github_workflow`` entity id for ``(full_name, path)``, or None.

    A single exact match resolves; zero or multiple matches return None (the
    caller then omits the ``SIGNED_BY_IDENTITY`` edge rather than guess). The
    workflow's natural key is ``full_name#<numeric id>``, not the path, so this
    must be a content match on the ``path`` field — hence a Gryphon read rather
    than a deterministic id computation.
    """
    if not full_name or not workflow_path:
        return None
    # Local imports keep tap_grid out of the collector module's import graph
    # for unit tests that don't need it.
    from tap_grid.models import Search
    from tap_grid.search import execute_search

    search = Search(
        search_type="gryphon",
        root="node",
        name="samsite-compliance-signing-workflow-resolver",
        input_schema={
            "type": "object",
            "properties": {"fn": {"type": "string"}, "path": {"type": "string"}},
            "required": ["fn", "path"],
        },
        definition={
            "query": [
                "MATCH (w:github_core__github_workflow)",
                "WHERE w.data.full_name = $fn AND w.data.path = $path",
                "RETURN w",
            ]
        },
        default_limit=10,
        max_limit=50,
    )
    result = execute_search(search, inputs={"fn": full_name, "path": workflow_path}, layer="extended")
    nodes = list((result.get("results", result) or {}).get("nodes", []) or [])
    if len(nodes) == 1:
        return str(nodes[0]["entity_id"])
    if not nodes:
        # No github_workflow node on the grid for this signing identity — almost
        # always because github_core hasn't collected yet (boot ordering). The
        # SIGNED_BY_IDENTITY / REQUESTS_SIGSTORE_SIGNATURE edges are omitted; log
        # so the absence is visible rather than indistinguishable from "unsigned".
        logger.info(
            "[3e92] sigstore_link: no github_workflow matched %s path=%s — omitting signing-identity edges "
            "(run github_core before samsite-compliance)",
            full_name,
            workflow_path,
        )
        return None
    logger.warning(
        "[5b05] sigstore_link: %d github_workflow nodes matched %s path=%s — ambiguous, omitting signing-identity edges",
        len(nodes),
        full_name,
        workflow_path,
    )
    return None


def oidc_issuer_entity_id(issuer_url: str) -> str:
    """Deterministic entity id of the github_core-owned ``oidc_issuer`` node for
    ``issuer_url``. Uses github_core's identity scheme so this collector's upsert
    and github_core's own singleton synthesis converge on the same node."""
    from tap_plugin.github_core.collectors.github_collector.identity import oidc_issuer_id

    return str(oidc_issuer_id(issuer_url))


def oidc_issuer_node_envelope(issuer_url: str) -> dict[str, Any]:
    """Build the ``oidc_issuer`` node envelope for ``issuer_url``.

    The consumer ensures this node exists in its own batch so the rekor entry's
    hotlinked ``IDENTITY_VOUCHED_BY`` edge has a valid, present target regardless
    of whether github_core's collector has run. ``host`` is the scheme-less form
    (matches ``aws_iam_oidc_provider.url`` for the AWS-side ``TRUSTS_ISSUER`` link).
    """
    host = issuer_url.split("://", 1)[-1]
    provider = "github-actions" if "githubusercontent.com" in host else ""
    return {
        "entity": {
            "entity_id": oidc_issuer_entity_id(issuer_url),
            "entity_type": "github_core__oidc_issuer",
            "name": issuer_url,
            "dimensions": {"identity.protocol": "oidc"},
        },
        "node": {
            "issuer_url": issuer_url,
            "host": host,
            "provider": provider,
            "configuration": {},
            "tags": {},
        },
    }


def verification_dict(result: Any) -> dict[str, Any]:
    """Adapt a ``sigstore_core`` ``VerificationResult`` into the verification dict
    the artifact decompose functions still consume (back-compat field stamping).

    Kept while the artifact nodes carry their own signature fields; the
    canonical verdict now lives on the ``ATTESTED_BY`` edge (single-source
    consolidation is a follow-up — see the collector spec).
    """
    return {
        "signature_verified": result.signature_verified,
        "signed_by": result.signed_by or "",
        "rekor_log_index": result.rekor_log_index or "",
        "verified_at": result.verified_at or "",
    }


def _entry_name(fields: dict[str, Any]) -> str:
    idx = fields.get("log_index")
    return f"Rekor entry #{idx}" if idx is not None else "Rekor entry"


def _ca_name(fields: dict[str, Any]) -> str:
    return fields.get("ca_name") or "Sigstore CA"


def fragment_to_envelopes(fragment: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Translate a ``sigstore_core`` ``GriftFragment`` into this collector's
    node/edge envelope shape (mirrors decompose's ``_node_envelope`` /
    ``_edge_envelope``)."""
    nodes: list[dict[str, Any]] = []
    for ent in fragment.entities:
        et = ent["entity_type"]
        fields = dict(ent.get("fields") or {})
        name = _entry_name(fields) if et == "sigstore_core__rekor_log_entry" else _ca_name(fields)
        nodes.append(
            {
                "entity": {
                    "entity_id": ent["entity_id"],
                    "entity_type": et,
                    "name": name,
                    "dimensions": ent.get("dimensions") or {},
                },
                # Node payload is exactly the model fields — sigstore_core models
                # declare additionalProperties:false and have no `name` field
                # (the display name lives on the entity spine, above).
                "node": dict(fields),
            }
        )

    edges: list[dict[str, Any]] = []
    for edg in fragment.edges:
        edges.append(
            {
                "entity": {
                    "entity_id": edg["edge_id"],
                    "entity_type": "edge",
                    "name": edg["edge_type"],
                    "dimensions": edg.get("dimensions") or {},
                },
                "edge": {
                    "from_entity_id": edg["source_entity_id"],
                    "to_entity_id": edg["target_entity_id"],
                    "edge_type": edg["edge_type"],
                    "properties": edg.get("properties") or {},
                },
            }
        )
    return nodes, edges
