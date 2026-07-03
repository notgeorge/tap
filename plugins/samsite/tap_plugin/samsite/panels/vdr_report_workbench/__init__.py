"""VDR Report Workbench Panel Type — `samsite-vdr-report-workbench`.

Renders one Vulnerability Detection & Response report as a classy workbench
(same mold as the KSI signal workbench): a coverage band (did the KEV catalog
and Dependabot alerts actually load — the consumer-side complement to the
upstream disclose-shortcut flags), headline stats, and the report's findings
as a Tabulator table (sortable + quick filter), with report metadata as a
footer.

Resolved via ``tap_web.panels.entity_resolution`` (deep link via
``vdr_report_entity_id`` wins; else latest by emitted_at). Findings are walked
over the ``REPORTS_FINDING`` edge; the traversal envelope is filtered to
``vdr_finding``.

Resolution contract: tap_web/specs/spec-web-panel-entity-resolution-v0.md
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.http import HttpRequest

from tap_grid.gryphon.executor import execute_gryphon_raw
from tap_web.models import Panel
from tap_web.panels.entity_resolution import resolve_entity
from tap_web.utils import safe_json

DEFAULT_VAR_NAME = "vdr_report_entity_id"


def _findings(report_entity_id: str) -> list[dict[str, Any]]:
    query = "MATCH (r:fedramp_20x_ksi__vdr_report)-[:REPORTS_FINDING__fedramp_20x_ksi]->(f:fedramp_20x_ksi__vdr_finding) WHERE r.entity_id = $id RETURN f"
    envelope = execute_gryphon_raw(query, {"id": report_entity_id}, layer="extended")
    return [n.get("data") or {} for n in (envelope.get("nodes") or []) if n.get("entity_type") == "fedramp_20x_ksi__vdr_finding"]


def build_context(panel: Any, request: Any) -> dict[str, Any]:
    """Pure function — separated from the classmethod so tests can call it directly."""
    resolution = resolve_entity(panel, request, default_var_name=DEFAULT_VAR_NAME)
    base: dict[str, Any] = {
        "panel_slug": "samsite-vdr-report-workbench",
        "entity_id": resolution.entity_id,
        "var_name": resolution.var_name,
        "used_fallback": resolution.used_fallback,
        "fallback_description": resolution.fallback_description,
        "fallback_count": resolution.fallback_count,
        "error_phase": None,
        "error_message": None,
        "report": None,
        "coverage": None,
        "headline": None,
        "findings_json": "[]",
    }

    if not resolution.ok:
        base["error_phase"] = "load"
        base["error_message"] = resolution.error
        return base

    data = (resolution.node or {}).get("data") or {}
    summary = data.get("summary") or {}

    base["report"] = {
        "report_id": data.get("report_id"),
        "emitted_at": data.get("emitted_at"),
        "system_id": data.get("system_id"),
        "vdr_class": data.get("vdr_class"),
    }
    # Coverage band — did the evaluation actually run? unknown != false.
    base["coverage"] = {
        "kev_catalog_loaded": summary.get("kev_catalog_loaded"),
        "dependabot_alerts_loaded": summary.get("dependabot_alerts_loaded"),
    }

    findings = _findings(resolution.entity_id)
    rows = [
        {
            "tracking_id": f.get("tracking_id"),
            "title": f.get("title") or f.get("tracking_id"),
            "resource": f.get("resource"),
            "source": f.get("source"),
            "cve": f.get("cve"),
            "pain": f.get("pain"),
            "internet_reachable": bool(f.get("internet_reachable")),
            "likely_exploitable": bool(f.get("likely_exploitable")),
            "is_kev": bool(f.get("is_kev")),
            "disposition": f.get("current_disposition"),
            "due": f.get("remediation_due_at"),
            "is_blocking": bool(f.get("is_blocking")),
        }
        for f in findings
    ]
    base["findings_json"] = safe_json(rows)
    # Count from the rows actually rendered so the headline stats == the table
    # == the toggle filters (summary.total_findings counts only active findings,
    # not the risk-accepted ledger that's also on the grid).
    base["headline"] = {
        "total": len(rows),
        "kev": sum(1 for r in rows if r["is_kev"]),
        "blocking": sum(1 for r in rows if r["is_blocking"]),
        "internet_reachable": sum(1 for r in rows if r["internet_reachable"]),
        "risk_accepted": sum(1 for r in rows if r["disposition"] == "risk-accepted"),
    }
    return base


class VdrReportWorkbenchPanelType:
    """Panel type for the VDR report workbench."""

    slug: ClassVar[str] = "samsite-vdr-report-workbench"
    label: ClassVar[str] = "VDR Report Workbench"
    view: ClassVar[str] = "samsite/panels/vdr_report_workbench.html"
    css: ClassVar[list[str]] = [
        "samsite/css/viewers.css",
        "tap_web/css/lib/tabulator.min.css",
    ]
    js: ClassVar[list[str]] = [
        "tap_web/js/lib/tabulator.min.js",
        "tap_web/js/panel-table.js",
    ]
    config_defaults: ClassVar[dict[str, Any]] = {"entity_id_var": DEFAULT_VAR_NAME}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        return build_context(panel, request)
