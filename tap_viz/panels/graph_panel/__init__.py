"""Graph Panel — built-in viz panel type for search-backed Cytoscape graph display.

Search binding:
  Panel links to a Layout via a USES_LAYOUT edge (Panel -> Layout) with
  properties={"layout-id": "default"}.
  Layout links to a Search via a USES_SEARCH edge (Layout -> Search) with
  properties={"search-id": "main"}.

Rendering:
  Server-side: the linked Search executes during panel fragment rendering.
  The resulting nodes and edges are JSON-encoded and embedded in the template
  for Cytoscape to consume client-side.  Search inputs are forwarded from
  request.GET so that context parameters (e.g. entity_id) reach the search.

  Nodes and edges are returned in GRIFT extended layer format so the template
  receives icon_url, shape, url_id, from_name, to_name without additional
  panel-side enrichment.

Read-only: no graph or layout mutation occurs in this panel.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from tap_web.utils import safe_json

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel

logger = logging.getLogger(__name__)


class GraphPanelType:
    """Built-in graph panel type descriptor.

    Implements get_view_context(panel, request) -> dict used by panel_view
    to resolve layout, execute the linked search, and return graph data
    for Cytoscape rendering.
    """

    slug = "graph"
    label = "Graph Panel"
    view = "tap_viz/panels/graph_panel.html"
    js: list[str] = ["tap_viz/js/cytoscape.min.js", "tap_viz/js/panel-graph.js"]
    css: list[str] = ["tap_viz/css/panel-graph.css"]
    config_defaults: dict[str, Any] = {}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        """Resolve layout and searches, execute all, merge results for the template.

        Executes all USES_SEARCH edges from the linked layout and merges nodes and
        edges across results (deduplicating by entity_id). Returns a context dict with:
          graph_nodes_json  - JSON-encoded nodes list
          graph_edges_json  - JSON-encoded edges list
          graph_error       - error string, or None on success
        """
        layout = _get_panel_layout(panel)
        if layout is None:
            return _error_ctx("No layout linked to this panel (USES_LAYOUT edge missing).")

        searches = _get_layout_searches(layout)
        if not searches:
            return _error_ctx("No search linked to this layout (USES_SEARCH edge missing).")

        nodes: dict[str, dict[str, Any]] = {}
        edges: dict[str, dict[str, Any]] = {}

        try:
            from tap_grid.search import execute_search

            raw_inputs = {k: v for k, v in request.GET.items() if k not in ("limit", "offset")}

            for search in searches:
                result = execute_search(search, inputs=raw_inputs or None, layer="extended")
                envelope = result.get("results", result)
                for node in envelope.get("nodes", []):
                    nodes.setdefault(node["entity"]["entity_id"], node)
                for edge in envelope.get("edges", []):
                    key = (
                        edge["entity"]["entity_id"]
                        if edge.get("entity")
                        else (
                            f"{edge['edge']['from_entity_id']}-{edge['edge']['to_entity_id']}-{edge['edge']['edge_type']}"
                        )
                    )
                    edges.setdefault(key, edge)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Graph panel search execution failed for panel %s", panel.entity_id)
            return _error_ctx(f"Search execution failed: {exc}")

        presentation = layout.definition.get("presentation", {})
        placement = presentation.get("placement", "cytoscape:cose")
        nesting_enabled = presentation.get("nesting", {}).get("enabled", False)

        return {
            "graph_nodes_json": safe_json(list(nodes.values())),
            "graph_edges_json": safe_json(list(edges.values())),
            "graph_placement": placement,
            "graph_nesting_enabled": nesting_enabled,
            "graph_error": None,
        }


def _get_panel_layout(panel: Panel) -> Any | None:
    """Return the Layout linked to a Panel via USES_LAYOUT edge (layout-id=default), or None."""
    from tap_grid.models import Edge
    from tap_viz.models import Layout

    edge = (
        Edge.objects.filter(
            from_entity=panel.entity,
            edge_type="USES_LAYOUT",
        )
        .select_related("to_entity")
        .order_by("entity__created_at")
        .first()
    )
    if edge is None:
        return None

    try:
        return Layout.objects.select_related("entity").get(entity=edge.to_entity)
    except Layout.DoesNotExist:
        logger.warning(
            "USES_LAYOUT edge %s points to missing Layout entity %s",
            edge.pk,
            edge.to_entity_id,
        )
        return None


def _get_layout_searches(layout: Any) -> list[Any]:
    """Return all Searches linked to a Layout via USES_SEARCH edges, ordered by creation."""
    from tap_grid.models import Edge, Search

    edges = (
        Edge.objects.filter(
            from_entity=layout.entity,
            edge_type="USES_SEARCH",
        )
        .select_related("to_entity")
        .order_by("entity__created_at")
    )

    results = []
    for edge in edges:
        try:
            results.append(Search.objects.select_related("entity").get(entity=edge.to_entity))
        except Search.DoesNotExist:
            logger.warning(
                "USES_SEARCH edge %s points to missing Search entity %s",
                edge.pk,
                edge.to_entity_id,
            )
    return results


def _error_ctx(message: str) -> dict[str, Any]:
    return {
        "graph_nodes_json": safe_json([]),
        "graph_edges_json": safe_json([]),
        "graph_placement": "cytoscape:cose",
        "graph_error": message,
    }
