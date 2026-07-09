"""Issuer identity primitives — the one place OIDC-issuer convergence is defined.

Any observer that sees an issuer URL mints its node through this module: github
reading its Actions issuer, aws reading an IAM OIDC provider ``url``, samsite
reading a verification policy's ``oidc_issuer``. Because the id and the ``host``
key both derive from ``canonical_issuer_url``, independent observers of the same
issuer produce the same node id and merge — convergence is guaranteed, not
coincidental, and there is no privileged creator or run-order dependency.

This module is mechanism, not catalog: it ships the general capability to mint an
issuer from a URL, never a seeded list of well-known issuers.

Spec: plugins/identity_core/specs/spec-identity-core-v0.md
(req-identity-core-canonical-url, req-identity-core-issuer-id, req-identity-core-envelope).
"""

from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_DNS, UUID, uuid5

# A stable, identity_core-specific namespace derived from the canonical DNS
# namespace, mirroring the per-plugin scheme every collector uses. A fixed UUID
# keeps issuer ids reproducible across environments with no runtime seed. (There
# is no repo-wide TAP namespace constant; the per-plugin form is the convention.)
IDENTITY_CORE_NAMESPACE: UUID = uuid5(NAMESPACE_DNS, "identity_core.tap")

_ENTITY_TYPE = "identity_core__oidc_issuer"


def canonical_issuer_url(raw: str) -> str:
    """Return the single canonical issuer key so independent observers converge.

    Normalizes: strips the ``https://`` / ``http://`` scheme, lowercases the host,
    strips a trailing slash, and preserves any path (the OIDC ``iss`` may carry
    one, and the path is case-sensitive so only the host is lowercased). Both
    github's scheme'd ``iss`` and AWS IAM's scheme-less provider ``url`` normalize
    to the same value (e.g. ``token.actions.githubusercontent.com``). The scheme
    is dropped from the *key* because AWS stores none; the scheme'd form is kept
    as the model's ``issuer_url`` display field.
    """
    s = raw.strip()
    if "://" in s:
        s = s.split("://", 1)[1]
    s = s.rstrip("/")
    if "/" in s:
        host, path = s.split("/", 1)
        return f"{host.lower()}/{path}"
    return s.lower()


def oidc_issuer_id(raw: str) -> UUID:
    """Deterministic entity id of the ``oidc_issuer`` node for ``raw``.

    ``uuid5(IDENTITY_CORE_NAMESPACE, "identity_core__oidc_issuer:" +
    canonical_issuer_url(raw))``. This is the only sanctioned way to compute an
    issuer id — no consumer hardcodes one or re-derives it from a different string
    (the collector-identity-fragility lesson). Because it keys on the canonical
    form, github and AWS produce the same id and their nodes merge; because it is
    a pure function of the URL, synthesis is idempotent across runs and observers.
    """
    return uuid5(IDENTITY_CORE_NAMESPACE, f"{_ENTITY_TYPE}:{canonical_issuer_url(raw)}")


def _infer_provider(host: str) -> str:
    # Non-authoritative provider label inferred from the host. Kept here so every
    # observer's envelope agrees on the field (github's collector and samsite's
    # collector must produce identical node payloads to merge cleanly).
    return "github-actions" if "githubusercontent.com" in host else ""


def oidc_issuer_node_envelope(raw: str, *, dimensions: dict[str, str] | None = None) -> dict[str, Any]:
    """Build the GRIFT node fragment for the ``oidc_issuer`` identified by ``raw``.

    Returns the standard ``{"entity": {...}, "node": {...}}`` envelope a consumer
    merges into its own GRIFT batch (the helper never writes to the grid itself —
    GRIFT flows through the caller's normal batch, no parallel mutation path).
    ``entity_id`` comes from :func:`oidc_issuer_id`; ``host`` is the canonical
    form; ``issuer_url`` is ``raw`` as observed. Consumers supply their own
    dimensions/anchor context; the default is ``{"identity.protocol": "oidc"}``.

    The node ``name`` is the issuer_url (matches ``OidcIssuer.get_name()``, the
    authority the spine projects on save — a divergent name would be overwritten).
    """
    host = canonical_issuer_url(raw)
    return {
        "entity": {
            "entity_id": str(oidc_issuer_id(raw)),
            "entity_type": _ENTITY_TYPE,
            "name": raw,
            "dimensions": dimensions or {"identity.protocol": "oidc"},
        },
        "node": {
            "issuer_url": raw,
            "host": host,
            "provider": _infer_provider(host),
            "configuration": {},
            "tags": {},
        },
    }
