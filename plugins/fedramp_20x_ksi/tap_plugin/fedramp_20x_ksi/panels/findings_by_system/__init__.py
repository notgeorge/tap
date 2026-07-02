"""Findings By System — plugin-owned table panel grouped by system.

Renders all open findings as a Tabulator table grouped by the asset the
finding applies to. Sister panel to findings_by_ksi (same dataset, different
group_by). See spec-fedramp-20x-ksi-findings-page.md.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from tap_plugin.fedramp_20x_ksi.panels.findings_table_helpers import build_findings_rows
from tap_web.utils import safe_json

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel

logger = logging.getLogger(__name__)


class FindingsBySystemPanelType:
    slug: ClassVar[str] = "findings_by_system"
    label: ClassVar[str] = "Findings By System"
    view: ClassVar[str] = "fedramp_20x_ksi/panels/findings_by_system.html"
    css: ClassVar[list[str]] = [
        "tap_web/css/lib/tabulator.min.css",
        "fedramp_20x_ksi/css/findings_table.css",
    ]
    js: ClassVar[list[str]] = [
        "tap_web/js/lib/tabulator.min.js",
        "fedramp_20x_ksi/js/findings_by_system.js",
    ]
    config_defaults: ClassVar[dict[str, Any]] = {}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        from tap_web.panel import get_panel_search

        search = get_panel_search(panel)
        if search is None:
            return {
                "findings_rows_json": safe_json([]),
                "findings_error": "No search linked to this panel.",
            }

        try:
            from tap_grid.search import execute_search

            result = execute_search(search, layer="extended")
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "[ba4a] findings_by_system search execution failed for panel %s",
                panel.entity_id,
            )
            return {
                "findings_rows_json": safe_json([]),
                "findings_error": f"Search execution failed: {exc}",
            }

        envelope = result["results"] if "results" in result else result
        rows = build_findings_rows(envelope)

        return {
            "findings_rows_json": safe_json(rows),
            "findings_error": None,
            "findings_count": len(rows),
        }
