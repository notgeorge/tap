"""GRIFT envelope + batch assembly for the github_core collector.

Spec: plugins/github_core/specs/spec-github-core-v0.md
(req-github-core-collector, req-github-core-dimensions-2 / repo scope
dimensions emitted per envelope). Two batches per run: the GitHub batch
(nodes + spine edges) and the enrichment batch (REFERENCES_RESOURCE edges
only).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid7

COLLECTION_FORMAT = "tap.github_core.collection-v0"
_GRIFT_VERSION = "0"


def node_envelope(
    *,
    entity_id: UUID,
    entity_type: str,
    name: str,
    dimensions: dict[str, str],
    fields: dict[str, Any],
) -> dict[str, Any]:
    return {
        "entity": {
            "entity_id": str(entity_id),
            "entity_type": entity_type,
            "name": name,
            "dimensions": dimensions,
        },
        "node": fields,
    }


def edge_envelope(
    *,
    entity_id: UUID,
    edge_type: str,
    source_id: UUID,
    target_id: UUID,
    dimensions: dict[str, str],
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "entity": {
            "entity_id": str(entity_id),
            "entity_type": edge_type,
            "name": edge_type,
            "dimensions": dimensions,
        },
        "edge": {
            "source_id": str(source_id),
            "target_id": str(target_id),
            "properties": properties or {},
        },
    }


def assemble_batch(
    *,
    batch_name: str,
    description: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    batch_dimensions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a single GRIFT document for one phase of one collection run."""
    now = datetime.now(UTC).isoformat()
    return {
        "grift_version": _GRIFT_VERSION,
        "batch_entity": {
            "entity_id": str(uuid7()),
            "entity_type": "grift_batch",
            "name": batch_name,
            "dimensions": batch_dimensions or {"github.platform": "github.com"},
            "description_json": {
                "format": COLLECTION_FORMAT,
                "description": description,
                "collected_at": now,
                "node_count": len(nodes),
                "edge_count": len(edges),
            },
        },
        "nodes": nodes,
        "edges": edges,
    }
