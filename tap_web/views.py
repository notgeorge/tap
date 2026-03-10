"""TAP Web views."""

import json
import logging
import re

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

    Renders a setup placeholder when no LandingPage is configured.
    """
    page = get_landing_page()
    if page is None:
        return render(request, "tap_web/setup_placeholder.html")

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
        return render(request, panel.view, {"panel": panel})
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
                _apply_form_to_panel(form, panel)
                panel.save()
                return redirect("panel-edit", panel_url_id=panel_url_id)
            return render(
                request,
                "tap_web/panel_edit.html",
                _panel_edit_context(panel_url_id, panel, form=form),
            )
        # Generic fallback — no registered PanelType; raw JSON config editing.
        panel.title = request.POST.get("title", panel.title)
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
        form = form_class(initial={
            "title": panel.title,
            "description": panel.description,
            **panel.config,
        })
    return render(request, "tap_web/panel_edit.html", _panel_edit_context(panel_url_id, panel, form=form))


# Standard Panel fields that map directly to Panel model attributes.
# All other form cleaned_data keys are merged into panel.config.
_STANDARD_PANEL_FIELDS = frozenset({"title", "description"})


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
    panel.title = cleaned["title"]
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
    editor_css: dict[str, None] = {path: None for path in (panel.editor_css or [])}
    editor_js: dict[str, None] = {path: None for path in (panel.editor_js or [])}
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
