"""Canonical TAP-side Sigstore-bundle → GRIFT-fragment decomposition.

Takes a verified bundle (a ``VerificationResult`` from ``verify_bundle``)
and turns it into the slice of graph data ``sigstore_core`` owns: one
``rekor_log_entry`` node, one ``sigstore_ca`` upsert, one ``CERT_ISSUED_BY``
edge, one ``ATTESTED_BY`` edge, and (when the caller supplies a resolved
identity entity id) one ``SIGNED_BY_IDENTITY`` edge.

The helper performs no graph reads or writes. It returns a ``GriftFragment``
the caller merges into its own GRIFT batch and submits via the normal
collector path.

Spec: plugins/sigstore_core/specs/spec-sigstore-core-v0.md
(req-sigstore-core-decompose, req-sigstore-core-disclosure).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import NAMESPACE_DNS, UUID, uuid5

from plugins.sigstore_core.verify import (
    PUBLIC_GOOD_FULCIO_NAME,
    PUBLIC_GOOD_FULCIO_URL,
    TUF_PUBLIC_GOOD_SOURCE,
    GitHubWorkflowPolicy,
    VerificationPolicy,
    VerificationResult,
)

# sigstore_core-specific UUIDv5 namespace for deterministic entity ids.
SIGSTORE_CORE_NAMESPACE: UUID = uuid5(NAMESPACE_DNS, "sigstore_core.tap")


@dataclass
class GriftFragment:
    """A slice of GRIFT-shaped graph data the caller merges into its batch.

    ``entities`` and ``edges`` are lists of dicts in the GRIFT v0 shape;
    the caller is responsible for merging them into its own envelope along
    with any other entities/edges the collector is producing.

    Spec: req-sigstore-core-decompose-1.
    """

    entities: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)


def _entity_id(entity_type: str, natural_key: str) -> str:
    return str(uuid5(SIGSTORE_CORE_NAMESPACE, f"{entity_type}:{natural_key}"))


def _edge_id(edge_type: str, source: str, target: str) -> str:
    return str(uuid5(SIGSTORE_CORE_NAMESPACE, f"edge:{edge_type}:{source}:{target}"))


def _policy_attrs(policy: VerificationPolicy) -> dict[str, str]:
    """Encode the applied policy into ATTESTED_BY edge attributes.

    Spec: req-sigstore-core-policy-3, req-sigstore-core-disclosure-4.
    """
    if isinstance(policy, GitHubWorkflowPolicy):
        attrs: dict[str, str] = {
            "policy_kind": "github_workflow",
            "policy_oidc_issuer": policy.oidc_issuer,
            "policy_github_repository": policy.github_repository,
        }
        if policy.workflow_identity_uri:
            attrs["policy_workflow_identity_uri"] = policy.workflow_identity_uri
        if policy.workflow_ref:
            attrs["policy_workflow_ref"] = policy.workflow_ref
        if policy.workflow_sha:
            attrs["policy_workflow_sha"] = policy.workflow_sha
        return attrs
    raise TypeError(f"Unknown policy kind: {type(policy).__name__}")


def bundle_to_grift_fragment(
    result: VerificationResult,
    *,
    anchor_entity_id: str,
    policy: VerificationPolicy,
    dimensions: dict[str, str],
    signing_identity_entity_id: str | None = None,
    oidc_issuer_entity_id: str | None = None,
) -> GriftFragment:
    """Turn a verified Sigstore bundle into a GRIFT fragment.

    Spec: req-sigstore-core-decompose (canonical function),
    req-sigstore-core-decompose-3 (unparseable refused),
    req-sigstore-core-decompose-5 (failed verdicts still emitted).

    Args:
        result: A ``VerificationResult`` from ``verify_bundle``. ``result.parsed_bundle``
            must not be ``None`` (caller must check this before calling).
        anchor_entity_id: Entity id of the signed entity. The ``ATTESTED_BY``
            edge source.
        policy: The policy that produced ``result``. Encoded as ATTESTED_BY edge attributes.
        dimensions: Dimensions to apply to emitted nodes/edges (the caller's
            envelope-level dimensions; model defaults handle ``sigstore.*`` ones).
        signing_identity_entity_id: Optional. If supplied, the helper emits a
            ``SIGNED_BY_IDENTITY`` edge from the Rekor entry to this entity.
            The helper performs no graph reads to resolve this — that's the
            caller's job (per req-sigstore-core-edges-5).
        oidc_issuer_entity_id: Optional. If supplied AND the bundle carries a
            signing issuer, the helper emits a hotlink-backed ``IDENTITY_VOUCHED_BY``
            edge from the Rekor entry to this ``oidc_issuer`` node, carrying
            ``properties.hotlink`` so the edge mirrors ``signing_identity_issuer``
            (req-grid-hotlink, mode exact). Caller-resolved, like the identity edge.

    Returns:
        A ``GriftFragment`` with the four or five GRIFT pieces. Caller merges
        into its own batch.

    Raises:
        ValueError: If ``result.parsed_bundle`` is ``None`` (unparseable bundle).
    """
    if result.parsed_bundle is None:
        raise ValueError(
            "bundle_to_grift_fragment requires a parseable bundle "
            "(result.parsed_bundle is None — caller should branch on this before decomposing)"
        )

    fragment = GriftFragment()

    # sigstore_ca upsert (public-good Fulcio in v0).
    ca_id = _entity_id("sigstore_ca", PUBLIC_GOOD_FULCIO_URL)
    fragment.entities.append(
        {
            "entity_type": "sigstore_ca",
            "entity_id": ca_id,
            "fields": {
                "ca_url": PUBLIC_GOOD_FULCIO_URL,
                "ca_name": PUBLIC_GOOD_FULCIO_NAME,
                "ca_kind": "fulcio",
                "trust_root_source": TUF_PUBLIC_GOOD_SOURCE,
            },
            "dimensions": dict(dimensions),
        }
    )

    # rekor_log_entry node. Immutable transparency-log facts only — verdict
    # lives on the ATTESTED_BY edge below.
    entry_natural_key = f"{result.log_key_id}#{result.rekor_log_index}"
    entry_id = _entity_id("rekor_log_entry", entry_natural_key)
    fragment.entities.append(
        {
            "entity_type": "rekor_log_entry",
            "entity_id": entry_id,
            "fields": {
                "log_key_id": result.log_key_id,
                "log_index": int(result.rekor_log_index) if result.rekor_log_index else None,
                "rekor_log_url": result.rekor_log_url,
                "integrated_time": result.integrated_time,
                "entry_kind": result.entry_kind,
                "signing_identity_uri": result.signed_by,
                "signing_identity_issuer": result.signing_issuer,
            },
            "dimensions": dict(dimensions),
        }
    )

    # CERT_ISSUED_BY: rekor_log_entry → sigstore_ca
    fragment.edges.append(
        {
            "edge_type": "CERT_ISSUED_BY",
            "edge_id": _edge_id("CERT_ISSUED_BY", entry_id, ca_id),
            "source_entity_id": entry_id,
            "target_entity_id": ca_id,
            "dimensions": dict(dimensions),
        }
    )

    # ATTESTED_BY: anchor → rekor_log_entry, carrying verdict + applied policy.
    attested_attrs: dict[str, Any] = {
        "signature_verified": bool(result.signature_verified),
        "verified_at": result.verified_at,
        "verification_failure_code": result.failure_code,
        "verification_failure_detail": result.failure_detail,
    }
    attested_attrs.update(_policy_attrs(policy))
    fragment.edges.append(
        {
            "edge_type": "ATTESTED_BY",
            "edge_id": _edge_id("ATTESTED_BY", anchor_entity_id, entry_id),
            "source_entity_id": anchor_entity_id,
            "target_entity_id": entry_id,
            "properties": attested_attrs,
            "dimensions": dict(dimensions),
        }
    )

    # SIGNED_BY_IDENTITY: caller-supplied target only (req-sigstore-core-edges-5).
    if signing_identity_entity_id is not None:
        fragment.edges.append(
            {
                "edge_type": "SIGNED_BY_IDENTITY",
                "edge_id": _edge_id("SIGNED_BY_IDENTITY", entry_id, signing_identity_entity_id),
                "source_entity_id": entry_id,
                "target_entity_id": signing_identity_entity_id,
                "dimensions": dict(dimensions),
            }
        )
        # REQUESTS_SIGSTORE_SIGNATURE: signing identity (workflow) → Fulcio CA.
        # The keyless cert-request step that precedes the signature; emitted only
        # when the caller resolved a signing identity (same precondition as
        # SIGNED_BY_IDENTITY). Source is the identity, target the issuing CA.
        fragment.edges.append(
            {
                "edge_type": "REQUESTS_SIGSTORE_SIGNATURE",
                "edge_id": _edge_id("REQUESTS_SIGSTORE_SIGNATURE", signing_identity_entity_id, ca_id),
                "source_entity_id": signing_identity_entity_id,
                "target_entity_id": ca_id,
                "dimensions": dict(dimensions),
            }
        )

    # IDENTITY_VOUCHED_BY: hotlink-backed edge to the OIDC issuer (caller-
    # supplied target). Emitted only when the bundle carries a signing issuer —
    # otherwise the rekor node's signing_identity_issuer field is empty and the
    # exact-mode hotlink expects zero edges. properties.hotlink mirrors that
    # field so the edge cannot drift from it (req-grid-hotlink, scalar selector).
    if oidc_issuer_entity_id is not None and result.signing_issuer:
        fragment.edges.append(
            {
                "edge_type": "IDENTITY_VOUCHED_BY",
                "edge_id": _edge_id("IDENTITY_VOUCHED_BY", entry_id, oidc_issuer_entity_id),
                "source_entity_id": entry_id,
                "target_entity_id": oidc_issuer_entity_id,
                "properties": {
                    "hotlink": {
                        "model": "rekor_log_entry",
                        "spec": "rekor-issuer",
                        "value": result.signing_issuer,
                    }
                },
                "dimensions": dict(dimensions),
            }
        )

    return fragment
