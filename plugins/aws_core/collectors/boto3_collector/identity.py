"""Deterministic identity for boto3-collected nodes and edges.

Spec: plugins/aws_core/specs/spec-aws-core-collector-v0.md
(req-aws-collector-identity).

The same AWS resource always yields the same ``entity_id`` across runs and
grids, so repeated collection upserts in place rather than duplicating — the
property that makes "re-run the collector live in the demo" safe. Edge
endpoints are computed from the same scheme, so an edge resolves by identity
without its target having been collected in the same run.

``NAMESPACE_AWS_COLLECTOR`` is frozen for the lifetime of the v0 collector;
changing it would re-identify every collected node on every grid.
"""

from __future__ import annotations

import uuid
from typing import Final

NAMESPACE_AWS_COLLECTOR: Final[uuid.UUID] = uuid.uuid5(uuid.NAMESPACE_DNS, "tap.aws_core.boto3_collector")


def node_entity_id(entity_type: str, natural_key: str) -> uuid.UUID:
    """Deterministic node id: ``uuid5(NS, "<entity_type>:<natural_key>")``."""
    return uuid.uuid5(NAMESPACE_AWS_COLLECTOR, f"{entity_type}:{natural_key}")


def edge_entity_id(edge_type: str, from_key: str, to_key: str) -> uuid.UUID:
    """Deterministic edge id: ``uuid5(NS, "edge:<edge_type>:<from>-><to>")``."""
    return uuid.uuid5(NAMESPACE_AWS_COLLECTOR, f"edge:{edge_type}:{from_key}->{to_key}")
