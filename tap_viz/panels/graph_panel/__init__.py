"""Graph Panel — built-in viz panel type for search-backed Cytoscape graph display.

Search binding:
  Panel links to a Layout via a USES_LAYOUT edge (Panel -> Layout) with
  properties={"layout-id": "default"}.
  Layout links to a Search via a USES_SEARCH edge (Layout -> Search) with
  properties={"search-id": "main"}.

Rendering:
  Server-side: the linked Search executes during panel fragment rendering.
  The resulting nodes and edges are JSON-encoded and embedded in the template
  for Cytoscape to consume client-side.

Read-only: no graph or layout mutation occurs in this panel.

Hub-and-spoke runner:
  ``hub_and_spoke_runner`` is a module search runner registered under the
  name ``"hub-and-spoke"``.  It accepts ``inputs={"entity_id": "<uuid>"}``
  and returns the hub entity plus one hop of inbound/outbound edges and
  connected nodes in the standard node/edge envelope.  Enrichment (icons,
  shapes) is applied by ``GraphPanelType.get_neighborhood_context`` after
  the runner returns, using the same pipeline as normal panel rendering.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

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
            from tap_grid.search_service import execute_search

            for search in searches:
                result = execute_search(search)
                envelope = result.get("results", result)
                for node in envelope.get("nodes", []):
                    nodes.setdefault(node["entity_id"], node)
                for edge in envelope.get("edges", []):
                    key = edge.get("entity_id") or f"{edge['from_entity_id']}-{edge['to_entity_id']}-{edge['edge_type']}"
                    edges.setdefault(key, edge)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Graph panel search execution failed for panel %s", panel.entity_id)
            return _error_ctx(f"Search execution failed: {exc}")

        node_list = list(nodes.values())
        _enrich_nodes_with_icons(node_list)
        _enrich_nodes_with_shape(node_list)

        placement = layout.definition.get("presentation", {}).get("placement", "cytoscape:cose")

        return {
            "graph_nodes_json": _safe_json(node_list),
            "graph_edges_json": _safe_json(list(edges.values())),
            "graph_placement": placement,
            "graph_error": None,
        }

    @classmethod
    def get_neighborhood_context(cls, entity_id: Any) -> dict[str, Any]:
        """Return Cytoscape context for an entity's immediate hub-and-spoke graph.

        Runs the ``"hub-and-spoke"`` module search runner via a transient Search
        object (no DB record required) then applies the standard icon and shape
        enrichment pipeline.  The returned dict is ready for use with
        ``tap_viz/graph_context.html``.

        Args:
            entity_id: UUID of the hub entity.

        Returns:
            Context dict with ``graph_nodes_json``, ``graph_edges_json``,
            ``graph_placement``, and ``graph_error``.
        """
        from tap_grid.models import Search
        from tap_grid.search_service import execute_search

        search = Search(
            search_type="module",
            name="hub-and-spoke",
            definition={"runner_key": "hub-and-spoke"},
            default_limit=200,
            max_limit=500,
        )
        try:
            result = execute_search(search, inputs={"entity_id": str(entity_id)})
            envelope = result.get("results", result)
            nodes_raw: list[dict[str, Any]] = envelope.get("nodes", [])
            edges_raw: list[dict[str, Any]] = envelope.get("edges", [])
        except Exception as exc:  # noqa: BLE001
            logger.exception("hub-and-spoke search failed for entity %s", entity_id)
            return _error_ctx(f"Graph context failed: {exc}")

        _enrich_nodes_with_icons(nodes_raw)
        _enrich_nodes_with_shape(nodes_raw)

        return {
            "graph_nodes_json": _safe_json(nodes_raw),
            "graph_edges_json": _safe_json(edges_raw),
            "graph_placement": "cytoscape:cose",
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


def _enrich_nodes_with_icons(nodes: list[dict[str, Any]]) -> None:
    """Add icon_url to each node dict in-place using the canonical grid icon service."""
    from tap_grid.icon_service import resolve_icon_url
    from tap_grid.models import EntityType

    slugs = {n["entity_type"] for n in nodes if n.get("entity_type")}
    if not slugs:
        for node in nodes:
            node["icon_url"] = ""
        return

    icon_map: dict[str, str] = {
        et.slug: resolve_icon_url(et) or ""
        for et in EntityType.objects.filter(slug__in=slugs)
    }
    for node in nodes:
        node["icon_url"] = icon_map.get(node.get("entity_type", ""), "")


def _enrich_nodes_with_shape(nodes: list[dict[str, Any]]) -> None:
    """Add shape to each node dict in-place from the model's DEFAULT_DISPLAY tap_viz hints."""
    from tap_grid.registry import get_model_class

    for node in nodes:
        entity_type = node.get("entity_type", "")
        shape = "ellipse"
        if entity_type:
            try:
                model_cls = get_model_class(entity_type)
                shape = model_cls.DEFAULT_DISPLAY.get("tap_viz", {}).get("shape", "ellipse")
            except KeyError:
                pass
        node["shape"] = shape


def _safe_json(value: Any) -> str:
    """Serialize value to a JSON string safe for embedding in HTML script blocks."""
    raw = json.dumps(value)
    return raw.replace("<", r"\u003c").replace(">", r"\u003e").replace("&", r"\u0026")


def hub_and_spoke_runner(
    search: Any,
    inputs: dict[str, Any],
    *,
    db_alias: str = "default",
) -> dict[str, Any]:
    """Module search runner — hub-and-spoke graph for a single entity.

    Returns the hub entity plus one hop of inbound and outbound edges and all
    directly connected entities.  Registered under the name ``"hub-and-spoke"``
    in ``TapVizConfig.ready()``.

    Args:
        search: The triggering Search instance (not used by this runner).
        inputs: Must contain ``"entity_id"`` (UUID string of the hub entity).
        db_alias: Database alias for all queries.

    Returns:
        Standard runner envelope: ``{"nodes": [...], "edges": [...]}``.
    """
    from tap_grid.models import Edge, Entity

    entity_id = inputs.get("entity_id", "")
    if not entity_id:
        return {"nodes": [], "edges": [], "warnings": ["hub-and-spoke: no entity_id in inputs."]}

    try:
        hub = Entity.objects.using(db_alias).get(pk=entity_id)
    except Entity.DoesNotExist:
        return {"nodes": [], "edges": [], "warnings": [f"hub-and-spoke: entity {entity_id} not found."]}

    outbound = list(
        Edge.objects.using(db_alias)
        .filter(from_entity=hub)
        .select_related("to_entity")
        .order_by("entity__created_at")
    )
    inbound = list(
        Edge.objects.using(db_alias)
        .filter(to_entity=hub)
        .select_related("from_entity")
        .order_by("entity__created_at")
    )

    neighbor_ids: set[str] = set()
    for edge in outbound:
        neighbor_ids.add(str(edge.to_entity_id))
    for edge in inbound:
        neighbor_ids.add(str(edge.from_entity_id))

    neighbors = (
        {str(e.pk): e for e in Entity.objects.using(db_alias).filter(pk__in=neighbor_ids)}
        if neighbor_ids
        else {}
    )

    nodes: list[dict[str, Any]] = [_node_dict(hub)]
    for entity in neighbors.values():
        nodes.append(_node_dict(entity))

    node_ids = {str(hub.pk)} | neighbor_ids
    edges: list[dict[str, Any]] = []
    for edge in outbound:
        if str(edge.to_entity_id) in node_ids:
            edges.append(_edge_dict(edge))
    for edge in inbound:
        if str(edge.from_entity_id) in node_ids:
            edges.append(_edge_dict(edge))

    return {"nodes": nodes, "edges": edges}


def _node_dict(entity: Any) -> dict[str, Any]:
    """Serialize an Entity to the standard node envelope format."""
    return {
        "entity_id": str(entity.pk),
        "entity_type": entity.entity_type,
        "name": entity.name or "",
    }


def _edge_dict(edge: Any) -> dict[str, Any]:
    """Serialize an Edge to the standard edge envelope format."""
    return {
        "entity_id": str(edge.entity_id),
        "from_entity_id": str(edge.from_entity_id),
        "to_entity_id": str(edge.to_entity_id),
        "edge_type": edge.edge_type,
    }


def _error_ctx(message: str) -> dict[str, Any]:
    return {
        "graph_nodes_json": _safe_json([]),
        "graph_edges_json": _safe_json([]),
        "graph_placement": "cytoscape:cose",
        "graph_error": message,
    }
