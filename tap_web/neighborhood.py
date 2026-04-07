"""Neighborhood service — graph context for legacy viewer and editor shells.

Executes a transient gryphon hub-and-spoke search and returns the results
in GRIFT extended layer format for Cytoscape rendering.  Used only by the
legacy monolithic viewer/editor templates; new code uses the GRIFT-defined
entity pages instead.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def get_entity_neighborhood(entity_id: uuid.UUID | str) -> dict[str, Any]:
    """Return Cytoscape context for an entity and its immediate neighbors.

    Args:
        entity_id: UUID of the hub entity.

    Returns:
        Context dict with ``graph_nodes_json``, ``graph_edges_json``,
        ``graph_placement``, ``graph_error``, and ``graph_context_id``.
    """
    from tap_grid.models import Search
    from tap_grid.search import execute_search

    search = Search(
        search_type="gryphon",
        root="node",
        name="hub-and-spoke",
        definition={
            "query": [
                "MATCH (hub)-[e]-(neighbor)",
                "WHERE hub.entity_id = $entity_id",
                "RETURN hub, e, neighbor",
            ]
        },
        default_limit=200,
        max_limit=500,
    )
    try:
        result = execute_search(search, inputs={"entity_id": str(entity_id)}, layer="extended")
        envelope = result.get("results", result)
        nodes_raw: list[dict[str, Any]] = envelope.get("nodes", [])
        edges_raw: list[dict[str, Any]] = envelope.get("edges", [])
    except Exception as exc:  # noqa: BLE001
        logger.exception("hub-and-spoke search failed for entity %s", entity_id)
        ctx = _error_ctx(f"Graph context failed: {exc}")
        ctx["graph_context_id"] = str(entity_id)
        return ctx

    return {
        "graph_nodes_json": _safe_json(nodes_raw),
        "graph_edges_json": _safe_json(edges_raw),
        "graph_placement": "cytoscape:cose",
        "graph_error": None,
        "graph_context_id": str(entity_id),
    }


def _safe_json(value: Any) -> str:
    """Serialize value to a JSON string safe for embedding in HTML script blocks."""
    raw = json.dumps(value)
    return raw.replace("<", r"\u003c").replace(">", r"\u003e").replace("&", r"\u0026")


def _error_ctx(message: str) -> dict[str, Any]:
    return {
        "graph_nodes_json": _safe_json([]),
        "graph_edges_json": _safe_json([]),
        "graph_placement": "cytoscape:cose",
        "graph_error": message,
    }
