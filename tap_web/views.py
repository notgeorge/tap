"""TAP Web views."""

import json
import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tap_grid.caller_context import CallerContext

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from tap_web.page import get_landing_page, get_page_by_slug, get_page_panels, parse_panel_url_id

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Page views
# ---------------------------------------------------------------------------


def landing_view(request: HttpRequest) -> HttpResponse:
    """Serve the root URL via LandingPage indirection."""
    page = get_landing_page()
    if page is None:
        return _render_grid_placeholder(request)
    return _render_page(request, page)


def page_view(request: HttpRequest, page_slug: str) -> HttpResponse:
    """Render a Page by its slug."""
    slug = f"/{page_slug}"
    page = get_page_by_slug(slug)
    if page is None:
        raise Http404(f"Page '{slug}' not found.")
    return _render_page(request, page)


def parameterized_page_view(
    request: HttpRequest,
    page_slug: str,
    **kwargs: Any,
) -> HttpResponse:
    """Render a Page by slug with URL path segments injected as search inputs.

    Captures like ``entity_id`` from URL patterns are merged into query
    parameters so panel seed searches receive them as ``$entity_id`` inputs.
    """
    slug = f"/{page_slug}"
    page = get_page_by_slug(slug)
    if page is None:
        raise Http404(f"Page '{slug}' not found.")
    extra = {k: str(v) for k, v in kwargs.items()}
    return _render_page(request, page, extra_query_params=extra)


# ---------------------------------------------------------------------------
# Panel views
# ---------------------------------------------------------------------------


def panel_view(request: HttpRequest, panel_url_id: str) -> HttpResponse:
    """Render a Panel fragment for HTMX consumption.

    URL format: /panel/<slug>--<entity-uuid>/
    On any exception returns an error fragment so the HTMX swap completes.
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

        # POST dispatch: if the panel type defines handle_post, route POST there.
        if request.method == "POST" and panel_type and hasattr(panel_type, "handle_post"):
            return panel_type.handle_post(panel, request)

        extra_ctx: dict = {}
        if panel_type and hasattr(panel_type, "get_view_context"):
            extra_ctx = panel_type.get_view_context(panel, request) or {}
        return render(
            request,
            panel.view,
            {
                "panel": panel,
                "edit_url": f"/panel/{panel_url_id}/edit/",
                **extra_ctx,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("[1899] Error rendering panel %s (view=%s)", entity_uuid, panel.view)
        return _panel_error(request, str(exc))


@require_http_methods(["GET", "POST"])
def panel_edit_view(request: HttpRequest, panel_url_id: str) -> HttpResponse:
    """Editor for a Panel object — routes through the generic editor shell.

    URL format: /panel/<slug>--<entity-uuid>/edit/
    Dispatches to the panel's registered PanelType for typed form handling.
    Falls back to raw JSON config editing when no PanelType is registered.
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
    editor_template = getattr(panel_type, "editor_view", "") if panel_type else ""

    if request.method == "POST":
        if form_class is not None:
            form = form_class(request.POST)
            if form.is_valid():
                if panel_type and hasattr(panel_type, "handle_save"):
                    panel_type.handle_save(form, panel, request)
                else:
                    from tap_grid.services import patch_node

                    patch_node(
                        target=panel.entity.pk,
                        payload=_form_to_patch_payload(form, panel),
                        caller_context=_build_caller_context(request),
                    )
                return redirect("panel-edit", panel_url_id=panel_url_id)
            return render(
                request,
                "tap_web/editor.html",
                _panel_editor_context(panel_url_id, panel, form=form, editor_template=editor_template),
            )
        # Generic fallback — no registered PanelType; raw JSON config editing.
        payload: dict[str, Any] = {
            "name": request.POST.get("name", panel.name),
            "description": request.POST.get("description", panel.description),
        }
        raw_config = request.POST.get("config", "")
        if raw_config:
            try:
                payload["config"] = json.loads(raw_config)
            except json.JSONDecodeError as exc:
                return render(
                    request,
                    "tap_web/editor.html",
                    _panel_editor_context(panel_url_id, panel, config_error=str(exc)),
                )
        from tap_grid.services import patch_node

        patch_node(
            target=panel.entity.pk,
            payload=payload,
            caller_context=_build_caller_context(request),
        )
        return redirect("panel-edit", panel_url_id=panel_url_id)

    # GET
    form = None
    if form_class is not None:
        if panel_type and hasattr(panel_type, "get_editor_initial"):
            initial = panel_type.get_editor_initial(panel)
        else:
            initial = {"name": panel.name, "description": panel.description, **panel.config}
        form = form_class(initial=initial)

    return render(
        request,
        "tap_web/editor.html",
        _panel_editor_context(panel_url_id, panel, form=form, editor_template=editor_template),
    )


# ---------------------------------------------------------------------------
# Generic object editor + viewer
# ---------------------------------------------------------------------------


@require_http_methods(["GET", "POST"])
def object_edit_view(request: HttpRequest, entity_type: str, object_url_id: str) -> HttpResponse:
    """Generic editor for any registered TAP entity type.

    URL format: /object/<entity-type>/<slug>--<entity-uuid>/edit/
    GET renders via the synthetic page builder using the entity-editor GRIFT
    subgraph. POST is handled by the EditorPanelType via the panel endpoint
    when using persisted pages; for synthetic pages, POST falls back to the
    legacy editor path since synthetic panels are rendered inline.
    """
    from tap_grid.registry import get_model_class

    entity_uuid = parse_panel_url_id(object_url_id)
    if entity_uuid is None:
        raise Http404(f"Invalid object URL: '{object_url_id}'")

    try:
        model_cls = get_model_class(entity_type)
    except KeyError:
        raise Http404(f"Unknown entity type '{entity_type}'.")

    try:
        obj = model_cls.objects.select_related("entity").get(entity__pk=entity_uuid)
    except model_cls.DoesNotExist:
        raise Http404(f"{entity_type} '{entity_uuid}' not found.")

    # POST: handle form submission directly (synthetic panels render inline,
    # so the editor panel's HTMX post targets the object edit URL).
    if request.method == "POST":
        return _handle_object_edit_post(request, obj, entity_type, object_url_id)

    # GET: render via synthetic page builder.
    from tap_web.synthetic import load_subgraph, render_synthetic_page

    subgraph = load_subgraph("entity-editor")
    return render_synthetic_page(
        request,
        subgraph,
        extra_query_params={
            "entity_id": str(entity_uuid),
            "entity_type": entity_type,
            "subject_entity_id": str(entity_uuid),
        },
    )


def object_view(request: HttpRequest, entity_type: str, object_url_id: str) -> HttpResponse:
    """Generic viewer for any registered TAP entity type.

    URL format: /object/<entity-type>/<slug>--<entity-uuid>/
    Renders via the synthetic page builder using the entity-viewer GRIFT
    subgraph in tap_web/data/.
    """
    from tap_grid.registry import get_model_class

    entity_uuid = parse_panel_url_id(object_url_id)
    if entity_uuid is None:
        raise Http404(f"Invalid object URL: '{object_url_id}'")

    try:
        model_cls = get_model_class(entity_type)
    except KeyError:
        raise Http404(f"Unknown entity type '{entity_type}'.")

    try:
        model_cls.objects.select_related("entity").get(entity__pk=entity_uuid)
    except model_cls.DoesNotExist:
        raise Http404(f"{entity_type} '{entity_uuid}' not found.")

    from tap_web.synthetic import load_subgraph, render_synthetic_page

    subgraph = load_subgraph("entity-viewer")
    return render_synthetic_page(
        request,
        subgraph,
        extra_query_params={
            "entity_id": str(entity_uuid),
            "entity_type": entity_type,
            "subject_entity_id": str(entity_uuid),
        },
    )


def _handle_object_edit_post(
    request: HttpRequest,
    obj: Any,
    entity_type: str,
    object_url_id: str,
) -> HttpResponse:
    """Handle POST for the generic object editor — validate and save via EditorDescriptor."""
    from tap_web.registry import get_editor

    descriptor = get_editor(entity_type)
    if descriptor is None:
        raise Http404(f"No editor registered for entity type '{entity_type}'.")

    form_class = descriptor.get_form_class(obj)
    if form_class is None:
        override = descriptor.get_extra_context(obj).get("edit_url_override")
        if override:
            return redirect(override)
        raise Http404(f"No form registered for entity type '{entity_type}'.")

    form = form_class(request.POST)
    if form.is_valid():
        descriptor.handle_save(form, obj, request)
        return redirect("object-edit", entity_type=entity_type, object_url_id=object_url_id)

    # Validation failed — re-render the synthetic editor page with errors.
    # The editor panel will pick up form errors from the re-rendered context.
    from tap_web.synthetic import load_subgraph, render_synthetic_page

    subgraph = load_subgraph("entity-editor")
    return render_synthetic_page(
        request,
        subgraph,
        extra_query_params={
            "entity_id": str(obj.entity_id),
            "entity_type": entity_type,
            "subject_entity_id": str(obj.entity_id),
        },
    )


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------


def _panel_editor_context(
    panel_url_id: str,
    panel: object,
    form: object = None,
    editor_template: str = "",
    config_error: str = "",
) -> dict:
    """Build template context for the panel editor page."""
    from tap_web.models import Panel

    assert isinstance(panel, Panel)
    graph_ctx = _get_neighborhood_context(panel.entity_id)
    # Editor assets come from the panel type, not the panel instance.
    panel_type = _get_panel_type_for_panel(panel)
    editor_css: dict[str, None] = dict.fromkeys(getattr(panel_type, "editor_css", []) or [])
    editor_js: dict[str, None] = dict.fromkeys(getattr(panel_type, "editor_js", []) or [])
    view_url = f"/object/panel/{panel.slug}--{panel.entity_id}/"
    return {
        "obj": panel,
        "obj_name": panel.name or panel.slug,
        "entity_type": "panel",
        "object_url_id": panel_url_id,
        "form": form,
        "editor_template": editor_template,
        "editor_css_assets": list(editor_css),
        "editor_js_assets": list(editor_js),
        "config_json": json.dumps(panel.config or {}, indent=2),
        "config_error": config_error,
        "view_url": view_url,
        **graph_ctx,
    }


def _object_editor_context(
    entity_type: str,
    object_url_id: str,
    obj: object,
    form: object,
    *,
    editor_template: str = "",
    view_url: str = "",
    extra: dict | None = None,
) -> dict:
    """Build template context for the generic object editor page."""
    graph_ctx = _get_neighborhood_context(obj.entity_id)
    return {
        "obj": obj,
        "obj_name": str(obj),
        "entity_type": entity_type,
        "object_url_id": object_url_id,
        "form": form,
        "editor_template": editor_template,
        "editor_css_assets": [],
        "editor_js_assets": [],
        "config_json": None,
        "config_error": "",
        "view_url": view_url,
        **(extra or {}),
        **graph_ctx,
    }


# ---------------------------------------------------------------------------
# Graph context helper (replaces neighborhood.py)
# ---------------------------------------------------------------------------


def _get_neighborhood_context(entity_id: object) -> dict[str, Any]:
    """Return Cytoscape graph context for the panel/object editor templates.

    Executes a transient gryphon hub-and-spoke search using the same Search
    definition as the synthetic entity page subgraph.
    """
    from tap_grid.models import Search
    from tap_grid.search import execute_search
    from tap_web.utils import safe_json

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
        nodes_raw = envelope.get("nodes", [])
        edges_raw = envelope.get("edges", [])
    except Exception as exc:  # noqa: BLE001
        logger.exception("[f200] hub-and-spoke search failed for entity %s", entity_id)
        return {
            "graph_nodes_json": safe_json([]),
            "graph_edges_json": safe_json([]),
            "graph_placement": "cytoscape:cose",
            "graph_error": f"Graph context failed: {exc}",
            "graph_context_id": str(entity_id),
        }

    return {
        "graph_nodes_json": safe_json(nodes_raw),
        "graph_edges_json": safe_json(edges_raw),
        "graph_placement": "cytoscape:cose",
        "graph_error": None,
        "graph_context_id": str(entity_id),
    }


# ---------------------------------------------------------------------------
# Standard panel helpers
# ---------------------------------------------------------------------------

_STANDARD_PANEL_FIELDS = frozenset({"name", "description"})


def _build_caller_context(request: HttpRequest) -> CallerContext:
    """Build a CallerContext from the current HTTP request."""
    from tap_grid.caller_context import CallerContext

    user = request.user if hasattr(request.user, "pk") and request.user.pk else None
    return CallerContext(user=user, batch_id=None)


def _form_to_patch_payload(form: object, panel: object) -> dict[str, Any]:
    """Return a patch payload dict from validated form cleaned_data for use with patch_node()."""
    from django.forms import BaseForm

    from tap_web.models import Panel

    assert isinstance(form, BaseForm)
    assert isinstance(panel, Panel)
    cleaned = form.cleaned_data
    payload: dict[str, Any] = {"name": cleaned["name"]}
    if "description" in cleaned:
        payload["description"] = cleaned["description"]
    config_updates = {k: v for k, v in cleaned.items() if k not in _STANDARD_PANEL_FIELDS}
    if config_updates:
        payload["config"] = config_updates
    return payload


def _get_panel_type_for_panel(panel: object) -> type | None:
    """Return the registered PanelType whose view matches panel.view, or None."""
    from tap_web.registry import panel_type_registry

    panel_view = getattr(panel, "view", None)
    for scope_data in panel_type_registry.all().values():
        for panel_type_cls in scope_data.values():
            if getattr(panel_type_cls, "view", None) == panel_view:
                return panel_type_cls
    return None


# ---------------------------------------------------------------------------
# Internal page rendering helpers
# ---------------------------------------------------------------------------


def _render_page(
    request: HttpRequest,
    page: object,
    extra_query_params: dict[str, str] | None = None,
) -> HttpResponse:
    """Render a Page using the page template."""
    panel_slots = get_page_panels(page)  # type: ignore[arg-type]

    panels_by_id: dict[str, str] = {}
    for panel_id, panel in panel_slots:
        panels_by_id[panel_id] = f"{panel.slug}--{panel.entity_id}"

    # Static assets come exclusively from the panel type. Panel instances do
    # not declare assets — a panel is identified by its `view` and the type
    # owns all css/js the panel needs to render.
    css: dict[str, None] = {}
    js: dict[str, None] = {}
    for _panel_id, panel in panel_slots:
        panel_type = _get_panel_type_for_panel(panel)
        for asset_path in getattr(panel_type, "css", []):
            css[asset_path] = None
        for asset_path in getattr(panel_type, "js", []):
            js[asset_path] = None

    layout = getattr(page, "layout", {}) or {}
    processed_columns = _process_layout(layout, panels_by_id)

    query_params = request.GET.copy()
    if extra_query_params:
        query_params.update(extra_query_params)

    context = {
        "page": page,
        "processed_columns": processed_columns,
        "css_assets": list(css),
        "js_assets": list(js),
        "query_params": query_params,
    }
    return render(request, "tap_web/page.html", context)


_NUMERIC_PREFIX_RE = re.compile(r"^[a-z]+-(\d+)")


def _extract_numeric_key(key: str) -> int:
    m = _NUMERIC_PREFIX_RE.match(key)
    return int(m.group(1)) if m else 0


def _process_layout(layout: dict, panels_by_id: dict[str, str]) -> list[dict]:
    """Convert raw layout JSON into a sorted structure the template can iterate."""
    columns_raw = layout.get("columns", {})
    columns = sorted(columns_raw.items(), key=lambda kv: _extract_numeric_key(kv[0]))

    processed: list[dict] = []
    for col_key, col_data in columns:
        rows_raw = col_data.get("rows", {})
        rows = sorted(rows_raw.items(), key=lambda kv: _extract_numeric_key(kv[0]))

        processed_rows: list[dict] = []
        for row_key, row_data in rows:
            panel_id = row_data.get("panel-id", "")
            processed_rows.append(
                {
                    "key": row_key,
                    "panel_id": panel_id,
                    "panel_url_id": panels_by_id.get(panel_id),
                    "row_span": row_data.get("row_span", 1),
                    "col_span": row_data.get("col_span", 1),
                    "height": row_data.get("height", "auto"),
                }
            )

        processed.append(
            {
                "key": col_key,
                "width": col_data.get("width", "1fr"),
                "rows": processed_rows,
            }
        )

    return processed


def _panel_error(request: HttpRequest, message: str) -> HttpResponse:
    return render(request, "tap_web/panel_error.html", {"message": message})


def _render_grid_placeholder(request: HttpRequest) -> HttpResponse:
    """Render a live all-nodes + all-edges view when no LandingPage is configured."""
    from tap_grid.models import Entity as _Entity
    from tap_grid.models import Search
    from tap_grid.search import execute_search
    from tap_web.panels.table_panel import _safe_int
    from tap_web.utils import safe_json

    _SEARCH_DB = "search_readonly"

    node_limit = _safe_int(request.GET.get("limit"), 100)
    node_offset = _safe_int(request.GET.get("offset"), 0)
    edge_limit = _safe_int(request.GET.get("edge_limit"), 100)
    edge_offset = _safe_int(request.GET.get("edge_offset"), 0)

    node_search = Search(
        search_type="orm",
        root="node",
        definition={"filters": {}, "order_by": ["name"]},
        default_limit=100,
        max_limit=500,
    )
    edge_search = Search(
        search_type="orm",
        root="edge",
        definition={"filters": {}, "order_by": ["edge_type"]},
        default_limit=100,
        max_limit=500,
    )

    _empty_ctx: dict[str, Any] = {
        "nodes_json": safe_json([]),
        "meta": {},
        "edges_json": safe_json([]),
        "edges_meta": {},
        "table_error": None,
    }

    try:
        node_result = execute_search(node_search, limit=node_limit, offset=node_offset)
        edge_result = execute_search(edge_search, limit=edge_limit, offset=edge_offset)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[5c03] Grid placeholder search failed")
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

    from tap_web.panels.table_panel import _enrich_nodes_with_icons

    _enrich_nodes_with_icons(nodes)

    if edges:
        all_ids = {e["from_entity_id"] for e in edges} | {e["to_entity_id"] for e in edges}
        names: dict[str, str] = dict(_Entity.objects.using(_SEARCH_DB).filter(id__in=all_ids).values_list("id", "name"))
        for edge in edges:
            edge["from_name"] = names.get(edge["from_entity_id"]) or edge["from_entity_id"][-8:]
            edge["to_name"] = names.get(edge["to_entity_id"]) or edge["to_entity_id"][-8:]

    return render(
        request,
        "tap_web/setup_placeholder.html",
        {
            "nodes_json": safe_json(nodes),
            "meta": meta,
            "edges_json": safe_json(edges),
            "edges_meta": edges_meta,
            "table_error": None,
        },
    )
