"""Deterministic node and edge identities for the samsite compliance collector.

Identities are ``uuid5`` values over a frozen plugin namespace, so the same
artifact emission re-collected on the same grid lands on the same entity ids
(re-runs upsert; nothing duplicates). The namespace is frozen for the lifetime
of the v0 collector — changing it would re-identify every node on every grid.

Spec: plugins/samsite/specs/spec-samsite-compliance-collector-v0.md
(req-samsite-collector-identity).
"""

from __future__ import annotations

import uuid
from typing import Final

NAMESPACE_SAMSITE_COMPLIANCE: Final[uuid.UUID] = uuid.uuid5(uuid.NAMESPACE_DNS, "tap.samsite.compliance_collector")


def node_entity_id(entity_type: str, natural_key: str) -> uuid.UUID:
    """Deterministic node id: ``uuid5(NS, "<entity_type>:<natural_key>")``."""
    return uuid.uuid5(NAMESPACE_SAMSITE_COMPLIANCE, f"{entity_type}:{natural_key}")


def edge_entity_id(edge_type: str, from_key: str, to_key: str) -> uuid.UUID:
    """Deterministic edge id: ``uuid5(NS, "edge:<edge_type>:<from>-><to>")``."""
    return uuid.uuid5(NAMESPACE_SAMSITE_COMPLIANCE, f"edge:{edge_type}:{from_key}->{to_key}")
