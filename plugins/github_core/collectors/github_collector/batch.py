"""GRIFT envelope + batch assembly for the github_core collector.

Spec: plugins/github_core/specs/spec-github-core-v0.md
(req-github-core-collector). Two batches per run: the GitHub batch (nodes +
spine edges) and the enrichment batch (REFERENCES_RESOURCE edges only).

Document shape per `tap_grid/schemas/grift-document.schema.json`:
  {metadata: {grift_version}, _reserved: {}, batches: [GriftBatchContainer]}
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
            "entity_type": "edge",
            "name": edge_type,
            "dimensions": dimensions,
        },
        "edge": {
            "from_entity_id": str(source_id),
            "to_entity_id": str(target_id),
            "edge_type": edge_type,
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
    """Wrap nodes + edges into a single-batch GRIFT v0 document."""
    moment = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    batch = {
        "batch_entity": {
            "entity_id": str(uuid7()),
            "entity_type": "batch",
            "name": batch_name,
            "dimensions": batch_dimensions or {"github.platform": "github.com"},
        },
        "batch_node": {
            "source": "github_core",
            "name": batch_name,
            "description": description,
            "description_json": {
                "format": COLLECTION_FORMAT,
                "collected_at": moment,
                "counts": {"nodes": len(nodes), "edges": len(edges)},
            },
        },
        "nodes": nodes,
        "edges": edges,
    }
    return {
        "metadata": {"grift_version": _GRIFT_VERSION},
        "_reserved": {},
        "batches": [batch],
    }
