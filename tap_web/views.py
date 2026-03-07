"""TAP Web views."""

import logging
import re

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render

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

    Falls back to the home view when no LandingPage is configured.
    """
    page = get_landing_page()
    if page is None:
        return home(request)

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
        return render(request, panel.view)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error rendering panel %s (view=%s)", entity_uuid, panel.view)
        return _panel_error(request, str(exc))


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
