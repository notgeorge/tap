"""Findings By KSI — plugin-owned table panel grouped by indicator.

Renders all open findings (with a RELATED_INDICATOR linkage) as a Tabulator
table grouped by KSI code. Sister panel to findings_by_system (same dataset,
different group_by). Findings without a RELATED_INDICATOR edge are excluded
from this panel since there's no group to put them under. See
spec-fedramp-20x-ksi-findings-page.md.
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


class FindingsByKsiPanelType:
    slug: ClassVar[str] = "findings_by_ksi"
    label: ClassVar[str] = "Findings By KSI"
    view: ClassVar[str] = "fedramp_20x_ksi/panels/findings_by_ksi.html"
    css: ClassVar[list[str]] = [
        "tap_web/css/lib/tabulator.min.css",
        "fedramp_20x_ksi/css/findings_table.css",
    ]
    js: ClassVar[list[str]] = [
        "tap_web/js/lib/tabulator.min.js",
        "fedramp_20x_ksi/js/findings_by_ksi.js",
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
                "[6fad] findings_by_ksi search execution failed for panel %s",
                panel.entity_id,
            )
            return {
                "findings_rows_json": safe_json([]),
                "findings_error": f"Search execution failed: {exc}",
            }

        envelope = result["results"] if "results" in result else result
        rows = build_findings_rows(envelope)
        # Drop findings without a KSI linkage (no group to render them under).
        rows = [r for r in rows if r.get("ksi_code")]

        return {
            "findings_rows_json": safe_json(rows),
            "findings_error": None,
            "findings_count": len(rows),
        }
