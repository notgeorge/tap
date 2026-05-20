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
import re
from typing import TYPE_CHECKING, Any

from tap_web.utils import safe_json

# Accept only a narrow set of height values from panel config so the value can
# be emitted into an inline style attribute safely. Allowed:
#   - "100%"
#   - an integer-px value like "420px" (1..9999)
# Anything else falls back to the default (legacy 420px behaviour).
_ALLOWED_PANEL_HEIGHT = re.compile(r"^(100%|[1-9][0-9]{0,3}px)$")
_DEFAULT_PANEL_HEIGHT = "420px"


def _sanitize_panel_height(raw: Any) -> str:
    if isinstance(raw, str) and _ALLOWED_PANEL_HEIGHT.match(raw):
        return raw
    return _DEFAULT_PANEL_HEIGHT

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
    js: list[str] = [
        "tap_viz/js/lib/cytoscape.min.js",
        "tap_viz/js/lib/cytoscape-grid-guide.js",
        "tap_viz/js/panel-graph.js",
    ]
    css: list[str] = ["tap_viz/css/panel-graph.css"]
    config_defaults: dict[str, Any] = {}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        """Resolve projection (preferred) or legacy layout, execute seed search, and
        pre-bake results for Cytoscape rendering.

        Resolution order:
          1. USES_PROJECTION edge -> Projection (new, projection-hosted panels)
          2. USES_LAYOUT edge -> Layout (legacy fallback)

        For projection-hosted panels: serializes the projection definition into
        the context so the client runtime can orchestrate elevations + layouts
        after bootstrap. The seed search (if any) is pre-baked for fast first
        paint, mirroring the legacy rendering path.
        """
        projection = _get_panel_projection(panel)
        if projection is not None:
            return cls._projection_context(panel, projection, request)

        layout = _get_panel_layout(panel)
        if layout is None:
            return _error_ctx("No projection or layout linked to this panel.")

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
                # Envelopes follow spec-grift-envelope: spine fields flat at top;
                # edge endpoint refs live in `data` for the lite-fallback key.
                for node in envelope.get("nodes", []):
                    nodes.setdefault(node["entity_id"], node)
                for edge in envelope.get("edges", []):
                    if "entity_id" in edge:
                        key = edge["entity_id"]
                    else:
                        ed = edge.get("data") or edge
                        key = f"{ed['from_entity_id']}-{ed['to_entity_id']}-{ed['edge_type']}"
                    edges.setdefault(key, edge)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[b9e0] Graph panel search execution failed for panel %s", panel.entity_id)
            return _error_ctx(f"Search execution failed: {exc}")

        presentation = layout.definition.get("presentation", {})
        placement = presentation.get("placement", "cytoscape:cose")
        nesting_enabled = presentation.get("nesting", {}).get("enabled", False)

        return {
            "graph_nodes_json": safe_json(list(nodes.values())),
            "graph_edges_json": safe_json(list(edges.values())),
            "graph_projection_json": safe_json(None),
            "graph_inputs_json": safe_json({}),
            "graph_placement": placement,
            "graph_nesting_enabled": nesting_enabled,
            "graph_height": _sanitize_panel_height((panel.config or {}).get("height")),
            "graph_error": None,
        }

    @classmethod
    def _projection_context(
        cls,
        panel: Panel,
        projection: Any,
        request: HttpRequest,
    ) -> dict[str, Any]:
        """Build a context dict for a projection-hosted graph panel.

        Pre-bakes the optional seed search (via USES_SEARCH on the Panel itself)
        for fast first paint; otherwise starts with an empty node/edge set. The
        client-side projection runtime takes over after handoff.
        """
        nodes: dict[str, dict[str, Any]] = {}
        edges: dict[str, dict[str, Any]] = {}

        seed_searches = _get_panel_seed_searches(panel)
        try:
            from tap_grid.search import execute_search

            raw_inputs = {k: v for k, v in request.GET.items() if k not in ("limit", "offset")}
            for search in seed_searches:
                result = execute_search(search, inputs=raw_inputs or None, layer="extended")
                envelope = result.get("results", result)
                # Envelopes follow spec-grift-envelope: spine fields flat at top.
                for node in envelope.get("nodes", []):
                    nodes.setdefault(node["entity_id"], node)
                for edge in envelope.get("edges", []):
                    if "entity_id" in edge:
                        key = edge["entity_id"]
                    else:
                        ed = edge.get("data") or edge
                        key = f"{ed['from_entity_id']}-{ed['to_entity_id']}-{ed['edge_type']}"
                    edges.setdefault(key, edge)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[b601] Graph panel seed search failed for panel %s", panel.entity_id)
            return _error_ctx(f"Seed search execution failed: {exc}")

        from tap_viz.panels.graph_panel.projection_resolver import resolve_projection_definition

        resolved_definition = resolve_projection_definition(projection.definition or {})

        return {
            "graph_nodes_json": safe_json(list(nodes.values())),
            "graph_edges_json": safe_json(list(edges.values())),
            "graph_projection_json": safe_json(resolved_definition),
            "graph_inputs_json": safe_json(raw_inputs),
            "graph_placement": "projection",
            "graph_nesting_enabled": False,
            "graph_height": _sanitize_panel_height((panel.config or {}).get("height")),
            "graph_error": None,
        }


def _get_panel_projection(panel: Panel) -> Any | None:
    """Return the Projection linked to a Panel via USES_PROJECTION edge, or None."""
    from tap_grid.models import Edge
    from tap_viz.models import Projection

    edge = (
        Edge.objects.filter(
            from_entity=panel.entity,
            edge_type="USES_PROJECTION",
        )
        .select_related("to_entity")
        .order_by("entity__created_at")
        .first()
    )
    if edge is None:
        return None

    try:
        return Projection.objects.select_related("entity").get(entity=edge.to_entity)
    except Projection.DoesNotExist:
        logger.warning(
            "[eb52] USES_PROJECTION edge %s points to missing Projection entity %s",
            edge.pk,
            edge.to_entity_id,
        )
        return None


def _get_panel_seed_searches(panel: Panel) -> list[Any]:
    """Return any seed Searches linked directly to a Panel via USES_SEARCH edges."""
    from tap_grid.models import Edge, Search

    edges = (
        Edge.objects.filter(
            from_entity=panel.entity,
            edge_type="USES_SEARCH",
        )
        .select_related("to_entity")
        .order_by("entity__created_at")
    )

    results: list[Any] = []
    for edge in edges:
        try:
            results.append(Search.objects.select_related("entity").get(entity=edge.to_entity))
        except Search.DoesNotExist:
            logger.warning(
                "[1cbb] USES_SEARCH edge %s points to missing Search entity %s",
                edge.pk,
                edge.to_entity_id,
            )
    return results


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
            "[6f4e] USES_LAYOUT edge %s points to missing Layout entity %s",
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
                "[3255] USES_SEARCH edge %s points to missing Search entity %s",
                edge.pk,
                edge.to_entity_id,
            )
    return results


def _error_ctx(message: str) -> dict[str, Any]:
    return {
        "graph_nodes_json": safe_json([]),
        "graph_edges_json": safe_json([]),
        "graph_projection_json": safe_json(None),
        "graph_inputs_json": safe_json({}),
        "graph_placement": "cytoscape:cose",
        "graph_height": _DEFAULT_PANEL_HEIGHT,
        "graph_error": message,
    }
