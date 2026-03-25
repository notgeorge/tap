"""Neighborhood service — graph context for viewer and editor shells.

Thin adapter over ``GraphPanelType.get_neighborhood_context``.  All rendering
logic, icon enrichment, and shape resolution stays in tap_viz where it belongs.
"""

from __future__ import annotations

import uuid
from typing import Any


def get_entity_neighborhood(entity_id: uuid.UUID | str) -> dict[str, Any]:
    """Return Cytoscape context for an entity and its immediate neighbors.

    Delegates to ``GraphPanelType.get_neighborhood_context`` which runs the
    ``"hub-and-spoke"`` module search runner and applies the standard
    enrichment pipeline (icons, shapes).

    Args:
        entity_id: UUID of the hub entity.

    Returns:
        Context dict with ``graph_nodes_json``, ``graph_edges_json``,
        ``graph_placement``, ``graph_error``, and ``graph_context_id``.
    """
    from tap_viz.panels.graph_panel import GraphPanelType

    ctx = GraphPanelType.get_neighborhood_context(entity_id)
    ctx["graph_context_id"] = str(entity_id)
    return ctx
