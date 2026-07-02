"""Plugin Status panel — the read-only plugin registry rendered as a Tabulator table.

Surfaces `tap_plugins.report.build_report()` (the same service `manage.py plugins` uses)
as a searchable table on an administrivia page. Each row consolidates BOTH dependency
directions — `depends_on` (what this plugin needs) and `required_by` (who needs it) — so
a human reads a plugin's full relationship picture without hunting across rows.

Gated by the `plugins.read` capability in the SERVICE LAYER: the panel routes through
`tap_plugins.report.get_plugin_report()`, which authorizes `plugins.read` before building
(a denial raises AuthzError → clean 403 at the panel view). Gating lives in the service
function every caller shares — not per-panel — so the plugin software bill of materials is
not world-readable. Read-only: no grid writes.

Spec: tap_plugins/specs/spec-plugin-architecture.md req-plugin-arch-install-registry-5.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from tap_web.utils import safe_json

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel

logger = logging.getLogger(__name__)

# Custom Tabulator column spec (panel-table.js buildCustomColumns shape). Field paths
# reference the flat row dicts built in _row_for_plugin. quick_filter searches across
# these fields, so depends_on/required_by are joined strings (searchable + readable).
_COLUMNS: list[dict[str, Any]] = [
    {"title": "Plugin", "field": "slug", "widthGrow": 1, "tooltip": "full_value"},
    {"title": "Name", "field": "name", "widthGrow": 1},
    {"title": "Version", "field": "version", "width": 110, "tooltip": "full_value"},
    {"title": "Source", "field": "source", "width": 90},
    {"title": "Mode", "field": "mode", "width": 95},
    {"title": "Health", "field": "health", "width": 95},
    {"title": "Models", "field": "models", "width": 90},
    {"title": "Edges", "field": "edges", "width": 90},
    {"title": "Depends on", "field": "depends_on", "widthGrow": 1, "tooltip": "full_value"},
    {"title": "Required by", "field": "required_by", "widthGrow": 1, "tooltip": "full_value"},
]


def _surface_cell(counts: dict[str, Any]) -> str:
    """Render a surface's declared/loaded counts as 'declared' or 'declared / loaded'."""
    declared = counts.get("declared", 0)
    loaded = counts.get("loaded")
    if loaded is None or loaded == declared:
        return str(declared)
    return f"{declared} / {loaded}"


def _row_for_plugin(p: dict[str, Any]) -> dict[str, Any]:
    """Flatten one report plugin record into a table row (all fields display-ready)."""
    health = p["load_health"]
    ok = health["loaded"] and health["manifest_valid"]
    deps = p["dependencies"]
    surfaces = p["surfaces"]
    version = p["version"] or "?"
    if p["commit"]:
        version = f"{version} @{p['commit'][:8]}"
    return {
        "slug": p["slug"],
        "name": p["name"],
        "version": version,
        "source": p["source"],
        "mode": p["mode"],
        "health": "ok" if ok else "degraded",
        "models": _surface_cell(surfaces["models"]),
        "edges": _surface_cell(surfaces["edges"]),
        "depends_on": ", ".join(deps["depends_on"]) or "—",
        "required_by": ", ".join(deps["required_by"]) or "—",
    }


class PluginStatusPanelType:
    slug = "plugin_status"
    label = "Plugin Status"
    view = "administrivia/panels/plugin_status.html"
    editor_view = ""
    css: ClassVar[list[str]] = ["tap_web/css/lib/tabulator.min.css", "tap_web/css/tabulator-minimal.css"]
    js: ClassVar[list[str]] = ["tap_web/js/lib/tabulator.min.js", "tap_web/js/panel-table.js"]
    config_defaults: ClassVar[dict[str, Any]] = {"quick_filter": True}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        # Route through the capability-gated service function (authorizes plugins.read).
        from tap_plugins.report import get_plugin_report

        report = get_plugin_report()
        rows = [_row_for_plugin(p) for p in report["plugins"]]
        return {
            "plugin_count": report["plugin_count"],
            "table_nodes_json": safe_json(rows),
            "table_columns_json": safe_json(_COLUMNS),
        }
