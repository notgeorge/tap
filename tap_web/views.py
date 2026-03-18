"""TAP Web views."""

import json
import logging
import re
from typing import Any

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from tap_web.page_service import get_landing_page, get_page_by_slug, get_page_panels, parse_panel_url_id

logger = logging.getLogger(__name__)


def home(request: HttpRequest) -> HttpResponse:
    """TAP home page — Cytoscape graph visualization (legacy/fallback)."""
    return render(request, "tap_web/home.html")


def landing_view(request: HttpRequest) -> HttpResponse:
    """Serve the root URL via LandingPage indirection.

    Resolves the earliest LandingPage → USES_LANDING_PAGE edge → Page and
    renders that Page inline without issuing a redirect. Query params from the
    root request are passed through unchanged to the page rendering context.

    Renders a live all-nodes table when no LandingPage is configured.
    """
    page = get_landing_page()
    if page is None:
        return _render_grid_placeholder(request)

    return _render_page(request, page)


def page_view(request: HttpRequest, page_slug: str) -> HttpResponse:
    """Render a Page by its slug.

    Args:
        page_slug: URL path captured by the catch-all pattern (without leading /).
    """
    slug = f"/{page_slug}"
    page = get_page_by_slug(slug)
    if page is None:
        raise Http404(f"Page '{slug}' not found.")

    return _render_page(request, page)


def panel_view(request: HttpRequest, panel_url_id: str) -> HttpResponse:
    """Render a Panel fragment for HTMX consumption.

    URL format: /panel/<slug>--<entity-uuid>/
    The UUID portion is used for lookup; the slug is decorative.

    On any exception during rendering, returns an error fragment at HTTP 200
    so the HTMX swap completes and the layout slot shows 'Panel Error'.
    """
    from tap_web.models import Panel

    entity_uuid = parse_panel_url_id(panel_url_id)
    if entity_uuid is None:
        return _panel_error(request, f"Invalid panel URL: '{panel_url_id}'")

    try:
        panel = Panel.objects.select_related("entity").get(entity__pk=entity_uuid)
    except Panel.DoesNotExist:
        return _panel_error(request, f"Panel '{entity_uuid}' not found.")

    try:
        panel_type = _get_panel_type_for_panel(panel)
        extra_ctx: dict = {}
        if panel_type and hasattr(panel_type, "get_view_context"):
            extra_ctx = panel_type.get_view_context(panel, request) or {}
        return render(request, panel.view, {"panel": panel, **extra_ctx})
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error rendering panel %s (view=%s)", entity_uuid, panel.view)
        return _panel_error(request, str(exc))


@require_http_methods(["GET", "POST"])
def panel_edit_view(request: HttpRequest, panel_url_id: str) -> HttpResponse:
    """Render or save the panel editor page.

    URL format: /panel/<slug>--<entity-uuid>/edit/
    The UUID is used for lookup; the slug is decorative.

    GET: Renders a two-region editor page — preview on top, editor below.
         If the panel has a registered PanelType with a form_class, passes an
         initialised Django Form in context for the typed editor template.
    POST: If a PanelType form_class is found, validates via Django Form (server-
          side sanitization) then saves. Falls back to direct JSON config editing
          for panels without a registered PanelType.
    """
    from tap_web.models import Panel

    entity_uuid = parse_panel_url_id(panel_url_id)
    if entity_uuid is None:
        return _panel_error(request, f"Invalid panel URL: '{panel_url_id}'")

    try:
        panel = Panel.objects.select_related("entity").get(entity__pk=entity_uuid)
    except Panel.DoesNotExist:
        return _panel_error(request, f"Panel '{entity_uuid}' not found.")

    panel_type = _get_panel_type_for_panel(panel)
    form_class = getattr(panel_type, "form_class", None) if panel_type else None

    if request.method == "POST":
        if form_class is not None:
            form = form_class(request.POST)
            if form.is_valid():
                if panel_type and hasattr(panel_type, "handle_save"):
                    panel_type.handle_save(form, panel, request)
                else:
                    _apply_form_to_panel(form, panel)
                    panel.save()
                return redirect("panel-edit", panel_url_id=panel_url_id)
            return render(
                request,
                "tap_web/panel_edit.html",
                _panel_edit_context(panel_url_id, panel, form=form),
            )
        # Generic fallback — no registered PanelType; raw JSON config editing.
        panel.name = request.POST.get("name", panel.name)
        panel.description = request.POST.get("description", panel.description)
        raw_config = request.POST.get("config", "")
        if raw_config:
            try:
                panel.config = json.loads(raw_config)
            except json.JSONDecodeError as exc:
                return render(
                    request,
                    "tap_web/panel_edit.html",
                    _panel_edit_context(panel_url_id, panel, config_error=str(exc)),
                )
        panel.save()
        return redirect("panel-edit", panel_url_id=panel_url_id)

    # GET
    form = None
    if form_class is not None:
        if panel_type and hasattr(panel_type, "get_editor_initial"):
            initial = panel_type.get_editor_initial(panel)
        else:
            initial = {"name": panel.name, "description": panel.description, **panel.config}
        form = form_class(initial=initial)
    return render(request, "tap_web/panel_edit.html", _panel_edit_context(panel_url_id, panel, form=form))


# Standard Panel fields that map directly to Panel model attributes.
# All other form cleaned_data keys are merged into panel.config.
_STANDARD_PANEL_FIELDS = frozenset({"name", "description"})


def _apply_form_to_panel(form: object, panel: object) -> None:
    """Apply validated Django Form cleaned_data to a Panel instance.

    Standard fields (title, description) map to Panel attributes.
    All remaining fields are merged into panel.config.
    """
    from django.forms import BaseForm

    from tap_web.models import Panel

    assert isinstance(form, BaseForm)
    assert isinstance(panel, Panel)
    cleaned = form.cleaned_data
    panel.name = cleaned["name"]
    panel.description = cleaned.get("description", panel.description)
    config_updates = {k: v for k, v in cleaned.items() if k not in _STANDARD_PANEL_FIELDS}
    if config_updates:
        panel.config = {**panel.config, **config_updates}


def _get_panel_type_for_panel(panel: object) -> type | None:
    """Return the registered PanelType whose view matches panel.view, or None."""
    from tap_web.registry import panel_type_registry

    panel_view = getattr(panel, "view", None)
    for scope_data in panel_type_registry.all().values():
        for panel_type_cls in scope_data.values():
            if getattr(panel_type_cls, "view", None) == panel_view:
                return panel_type_cls
    return None


def _panel_edit_context(
    panel_url_id: str,
    panel: object,
    form: object = None,
    config_error: str = "",
) -> dict:
    """Build template context for the panel edit page."""
    from tap_web.models import Panel

    assert isinstance(panel, Panel)
    editor_css: dict[str, None] = dict.fromkeys(panel.editor_css or [])
    editor_js: dict[str, None] = dict.fromkeys(panel.editor_js or [])
    return {
        "panel": panel,
        "panel_url_id": panel_url_id,
        "preview_url": f"/panel/{panel_url_id}/",
        "editor_css_assets": list(editor_css),
        "editor_js_assets": list(editor_js),
        "config_json": json.dumps(panel.config or {}, indent=2),
        "config_error": config_error,
        "form": form,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _render_page(request: HttpRequest, page: object) -> HttpResponse:
    """Render a Page using the page template.

    Gathers panels from USES_PANEL edges, collects and deduplicates their
    static assets, builds the sorted column/row structure for CSS Grid, and
    passes everything to the page template.
    """
    panel_slots = get_page_panels(page)  # type: ignore[arg-type]

    # Build a panel_id → panel URL mapping for layout rendering.
    panels_by_id: dict[str, str] = {}
    for panel_id, panel in panel_slots:
        panels_by_id[panel_id] = f"{panel.slug}--{panel.entity_id}"

    # Deduplicate CSS and JS across all panels (order-preserving via dict).
    css: dict[str, None] = {}
    js: dict[str, None] = {}
    for _panel_id, panel in panel_slots:
        for asset_path in panel.css:
            css[asset_path] = None
        for asset_path in panel.js:
            js[asset_path] = None

    # Pre-process the layout JSONField into a sorted structure for the template.
    layout = getattr(page, "layout", {}) or {}
    processed_columns = _process_layout(layout, panels_by_id)

    context = {
        "page": page,
        "processed_columns": processed_columns,
        "css_assets": list(css),
        "js_assets": list(js),
        "query_params": request.GET,
    }
    return render(request, "tap_web/page.html", context)


_NUMERIC_PREFIX_RE = re.compile(r"^[a-z]+-(\d+)")


def _extract_numeric_key(key: str) -> int:
    """Extract the leading integer from a col-N or row-N layout key."""
    m = _NUMERIC_PREFIX_RE.match(key)
    return int(m.group(1)) if m else 0


def _process_layout(layout: dict, panels_by_id: dict[str, str]) -> list[dict]:
    """Convert raw layout JSON into a sorted structure the template can iterate.

    Returns a list of column dicts, each containing a sorted list of row dicts.
    Each row dict includes the panel HTMX URL (or None if the panel_id has no match).
    """
    columns_raw = layout.get("columns", {})
    columns = sorted(columns_raw.items(), key=lambda kv: _extract_numeric_key(kv[0]))

    processed: list[dict] = []
    for col_key, col_data in columns:
        rows_raw = col_data.get("rows", {})
        rows = sorted(rows_raw.items(), key=lambda kv: _extract_numeric_key(kv[0]))

        processed_rows: list[dict] = []
        for row_key, row_data in rows:
            panel_id = row_data.get("panel-id", "")
            processed_rows.append({
                "key": row_key,
                "panel_id": panel_id,
                "panel_url_id": panels_by_id.get(panel_id),  # None if no panel linked
                "row_span": row_data.get("row_span", 1),
                "col_span": row_data.get("col_span", 1),
            })

        processed.append({
            "key": col_key,
            "width": col_data.get("width", "1fr"),
            "rows": processed_rows,
        })

    return processed


def _panel_error(request: HttpRequest, message: str) -> HttpResponse:
    """Return a panel error HTML fragment so HTMX swap completes."""
    return render(request, "tap_web/panel_error.html", {"message": message})


def _render_grid_placeholder(request: HttpRequest) -> HttpResponse:
    """Render a live all-nodes + all-edges view when no LandingPage is configured.

    Uses transient (unsaved) Search instances — execute_search reads only model
    fields, never queries by PK, so no DB writes occur.
    """
    from tap_grid.models import Entity as _Entity
    from tap_grid.models import Search
    from tap_grid.search_service import execute_search
    from tap_web.panels.table_panel import _safe_int, _safe_json

    _SEARCH_DB = "search_readonly"

    node_limit = _safe_int(request.GET.get("limit"), 25)
    node_offset = _safe_int(request.GET.get("offset"), 0)
    edge_limit = _safe_int(request.GET.get("edge_limit"), 50)
    edge_offset = _safe_int(request.GET.get("edge_offset"), 0)

    node_search = Search(
        search_type="orm",
        root="node",
        definition={"filters": {}, "order_by": ["name"]},
        default_limit=25,
        max_limit=200,
    )
    edge_search = Search(
        search_type="orm",
        root="edge",
        definition={"filters": {}, "order_by": ["edge_type"]},
        default_limit=50,
        max_limit=500,
    )

    _empty_ctx: dict[str, Any] = {
        "nodes_json": _safe_json([]),
        "meta": {},
        "edges_json": _safe_json([]),
        "edges_meta": {},
        "table_error": None,
    }

    try:
        node_result = execute_search(node_search, limit=node_limit, offset=node_offset)
        edge_result = execute_search(edge_search, limit=edge_limit, offset=edge_offset)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Grid placeholder search failed")
        return render(
            request,
            "tap_web/setup_placeholder.html",
            {**_empty_ctx, "table_error": str(exc)},
        )

    # --- Nodes ---
    if "results" in node_result:
        nodes: list[dict[str, Any]] = node_result["results"].get("nodes", [])
        n_lim: int = node_result["limit"]
        n_off: int = node_result["offset"]
        n_count: int = node_result["count"]
        meta: dict[str, Any] = {
            "count": n_count,
            "limit": n_lim,
            "offset": n_off,
            "has_prev": n_off > 0,
            "has_next": n_off + n_lim < n_count,
            "prev_offset": max(0, n_off - n_lim),
            "next_offset": n_off + n_lim,
            "display_end": min(n_off + n_lim, n_count),
        }
    else:
        nodes = node_result.get("nodes", [])
        meta = {}

    # --- Edges ---
    # result["count"] for root="edge" = len(current page), not total.
    # Use info["total_count"] from the ORM compiler for correct pagination.
    if "results" in edge_result:
        edges: list[dict[str, Any]] = edge_result["results"].get("edges", [])
        e_lim: int = edge_result["limit"]
        e_off: int = edge_result["offset"]
        e_count: int = edge_result["results"]["info"].get("total_count", len(edges))
        edges_meta: dict[str, Any] = {
            "count": e_count,
            "limit": e_lim,
            "offset": e_off,
            "has_prev": e_off > 0,
            "has_next": e_off + e_lim < e_count,
            "prev_offset": max(0, e_off - e_lim),
            "next_offset": e_off + e_lim,
            "display_end": min(e_off + e_lim, e_count),
        }
    else:
        edges = edge_result.get("edges", [])
        edges_meta = {}

    # Enrich edges with from/to display names via bulk lookup.
    if edges:
        all_ids = {e["from_entity_id"] for e in edges} | {e["to_entity_id"] for e in edges}
        names: dict[str, str] = dict(
            _Entity.objects.using(_SEARCH_DB).filter(id__in=all_ids).values_list("id", "name")
        )
        for edge in edges:
            edge["from_name"] = names.get(edge["from_entity_id"]) or edge["from_entity_id"][-8:]
            edge["to_name"] = names.get(edge["to_entity_id"]) or edge["to_entity_id"][-8:]

    return render(
        request,
        "tap_web/setup_placeholder.html",
        {
            "nodes_json": _safe_json(nodes),
            "meta": meta,
            "edges_json": _safe_json(edges),
            "edges_meta": edges_meta,
            "table_error": None,
        },
    )
