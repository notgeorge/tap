"""Genericom Open Alerts — plugin-owned table panel for the demo.

Renders open Findings (status="open") as a flat Tabulator table beneath the
AWS top-level graph on the Genericom page. Columns are hard-coded for the
Finding model: Title, Associated System, Description, Created, Last Updated.

This panel is a deliberate one-off for the Anwar / Ace of Clouds demo. See
spec-genericom-open-alerts-table.md (One-Off Choices) for the full list of
shortcuts taken and the conditions under which each should be refactored
into the standard tap_web Table Panel.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from tap_web.utils import safe_json

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel

logger = logging.getLogger(__name__)


class GenericomOpenAlertsPanelType:
    """Panel type for the Genericom open alerts table."""

    slug: ClassVar[str] = "genericom-open-alerts"
    label: ClassVar[str] = "Genericom Open Alerts"
    view: ClassVar[str] = "genericom/panels/open_alerts.html"
    css: ClassVar[list[str]] = [
        "tap_web/css/lib/tabulator.min.css",
        "genericom/css/panel-open-alerts.css",
    ]
    js: ClassVar[list[str]] = [
        "tap_web/js/lib/tabulator.min.js",
        "genericom/js/panel-open-alerts.js",
    ]
    config_defaults: ClassVar[dict[str, Any]] = {}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        """Resolve the linked Search, execute it, and emit a flat row payload.

        The panel relies on the dataset invariant that every open Finding has at
        least one HAS_FINDING parent (req-genericom-alerts-no-orphans). Findings
        encountered without a parent are logged at WARNING and skipped — defensive
        guard only; should never fire in seeded data.
        """
        from tap_web.panel import get_panel_search

        search = get_panel_search(panel)
        if search is None:
            return {
                "open_alerts_rows_json": safe_json([]),
                "open_alerts_error": "No search linked to this panel.",
            }

        try:
            from tap_grid.search import execute_search

            result = execute_search(search, layer="extended")
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "[6e34] Genericom open-alerts search execution failed for panel %s",
                panel.entity_id,
            )
            return {
                "open_alerts_rows_json": safe_json([]),
                "open_alerts_error": f"Search execution failed: {exc}",
            }

        envelope = result["results"] if "results" in result else result
        rows = _build_rows(envelope)

        return {
            "open_alerts_rows_json": safe_json(rows),
            "open_alerts_error": None,
            "open_alerts_count": len(rows),
        }


def _build_rows(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    """Walk the subgraph envelope and emit a flat row payload.

    Envelope shape: each node is {"entity": {...}, "node": {...}, ...} with
    entity-spine fields under "entity" and domain fields under "node". Edges
    follow the same nested shape under "entity" / "edge".

    Returns rows sorted by updated_at desc, created_at desc, entity_id (for
    deterministic tie-break per req-genericom-alerts-sort-3).
    """
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for n in envelope.get("nodes", []):
        ent = n.get("entity") or {}
        eid = ent.get("entity_id")
        if eid:
            nodes_by_id[eid] = n

    parents_by_finding: dict[str, str] = {}
    ksi_links_by_finding: dict[str, dict[str, Any]] = {}
    for edge in envelope.get("edges", []):
        edge_body = edge.get("edge") or {}
        et = edge_body.get("edge_type")
        if et == "HAS_FINDING":
            finding_id = edge_body.get("to_entity_id")
            parent_id = edge_body.get("from_entity_id")
            if finding_id and parent_id and finding_id not in parents_by_finding:
                parents_by_finding[finding_id] = parent_id
        elif et == "RELATED_INDICATOR":
            finding_id = edge_body.get("from_entity_id")
            ksi_id = edge_body.get("to_entity_id")
            if finding_id and ksi_id and finding_id not in ksi_links_by_finding:
                rel = (edge_body.get("properties") or {}).get("relationship_type", "")
                ksi_links_by_finding[finding_id] = {
                    "ksi_id": ksi_id,
                    "relationship": rel,
                }

    rows: list[dict[str, Any]] = []
    for n in envelope.get("nodes", []):
        ent = n.get("entity") or {}
        if ent.get("entity_type") != "finding":
            continue

        finding_id = ent.get("entity_id")
        if not finding_id:
            continue

        parent_id = parents_by_finding.get(finding_id)
        if parent_id is None:
            logger.warning(
                "[d639] Genericom open-alerts: finding %s has no HAS_FINDING parent; skipping",
                finding_id,
            )
            continue

        parent = nodes_by_id.get(parent_id)
        if parent is None:
            logger.warning(
                "[00ce] Genericom open-alerts: HAS_FINDING parent %s for finding %s not in envelope; skipping",
                parent_id,
                finding_id,
            )
            continue

        finding_body = n.get("node") or {}
        parent_ent = parent.get("entity") or {}

        ksi_link = ksi_links_by_finding.get(finding_id) or {}
        ksi_code = ""
        ksi_name = ""
        if ksi_link.get("ksi_id"):
            ksi_node = nodes_by_id.get(ksi_link["ksi_id"]) or {}
            ksi_body = ksi_node.get("node") or {}
            ksi_ent = ksi_node.get("entity") or {}
            ksi_code = ksi_body.get("code") or ""
            ksi_name = ksi_ent.get("name") or ksi_body.get("name") or ""

        created_at = ent.get("created_at")
        rows.append(
            {
                "finding_id": finding_id,
                "title": ent.get("name") or finding_body.get("name") or "",
                "system_name": parent_ent.get("name") or (parent.get("node") or {}).get("name") or "",
                "system_id": parent_id,
                "summary": finding_body.get("summary") or "",
                "description": finding_body.get("description") or "",
                "ksi_code": ksi_code,
                "ksi_name": ksi_name,
                "ksi_relationship": ksi_link.get("relationship", ""),
                "created_at": created_at,
                "age_days": _age_in_days(created_at),
            }
        )

    # Default order: youngest findings first (smallest age). Tie-break by raw
    # created_at desc, then entity_id is implicit via stable sort on dict.
    rows.sort(
        key=lambda r: (
            r["age_days"] if r["age_days"] is not None else 10**9,
            -(_iso_to_epoch(r["created_at"]) or 0),
        )
    )
    return rows


def _age_in_days(created_at_iso: str | None) -> int | None:
    """Days since *created_at_iso*, rounding up when more than 12h into the day.

    Example: 1d 11h -> 1; 1d 13h -> 2; 0d 5h -> 0; 0d 13h -> 1.
    Returns None if the timestamp is missing or unparseable.
    """
    if not created_at_iso:
        return None
    try:
        dt = datetime.fromisoformat(created_at_iso)
    except ValueError, TypeError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta = datetime.now(UTC) - dt
    age_days_float = delta.total_seconds() / 86400.0
    if age_days_float < 0:
        return 0
    return math.floor(age_days_float + 0.5)


def _iso_to_epoch(created_at_iso: str | None) -> float | None:
    if not created_at_iso:
        return None
    try:
        dt = datetime.fromisoformat(created_at_iso)
    except ValueError, TypeError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.timestamp()
