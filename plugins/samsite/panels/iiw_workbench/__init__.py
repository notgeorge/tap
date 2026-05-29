"""IIW Inventory Workbench Panel Type — `samsite-iiw-workbench`.

Renders the FedRAMP Integrated Inventory Workbook (IIW) — a whole-blob
``compliance_artifact`` of kind ``iiw`` whose ``content`` is raw CSV — as a
classy workbench: a provenance band (the artifact IS signed, unlike the
decomposed signals), headline counts, and the CSV itself as a Tabulator table
(sortable + quick filter, dynamic columns from the CSV header, horizontal
scroll for the wide inventory).

Resolved via ``tap_web.panels.entity_resolution`` (deep link via
``iiw_artifact_entity_id`` wins; else latest ``iiw`` artifact by fetched_at).

Resolution contract: tap_web/specs/spec-web-panel-entity-resolution-v0.md
"""

from __future__ import annotations

import csv
import io
from typing import Any, ClassVar

from django.http import HttpRequest

from tap_web.models import Panel
from tap_web.panels.entity_resolution import resolve_entity
from tap_web.utils import safe_json

DEFAULT_VAR_NAME = "iiw_artifact_entity_id"


def _parse_csv(content: Any) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Parse the IIW CSV string into (Tabulator column specs, row dicts).

    Columns are keyed positionally (``c0``, ``c1``, …) so arbitrary header
    text — spaces, punctuation — never collides with Tabulator's dotted field
    paths; the header text becomes the column title.
    """
    if not isinstance(content, str) or not content.strip():
        return [], []
    all_rows = list(csv.reader(io.StringIO(content)))
    if not all_rows:
        return [], []
    header = all_rows[0]
    # First column (the asset identifier) carries long values and earns room;
    # the rest stay compact so the angled headers + full-bleed width fit as
    # many columns on screen as possible.
    columns = [
        {
            "field": f"c{i}",
            "title": h or f"Column {i + 1}",
            "minWidth": 220 if i == 0 else 70,
            "widthGrow": 1 if i == 0 else 0,
            "tooltip": "full_value",
        }
        for i, h in enumerate(header)
    ]
    rows: list[dict[str, str]] = []
    for raw in all_rows[1:]:
        if not any((cell or "").strip() for cell in raw):
            continue  # skip blank trailing lines
        rows.append({f"c{i}": (raw[i] if i < len(raw) else "") for i in range(len(header))})
    return columns, rows


def build_context(panel: Any, request: Any) -> dict[str, Any]:
    """Pure function — separated from the classmethod so tests can call it directly."""
    resolution = resolve_entity(panel, request, default_var_name=DEFAULT_VAR_NAME)
    base: dict[str, Any] = {
        "panel_slug": "samsite-iiw-workbench",
        "entity_id": resolution.entity_id,
        "var_name": resolution.var_name,
        "used_fallback": resolution.used_fallback,
        "fallback_description": resolution.fallback_description,
        "fallback_count": resolution.fallback_count,
        "error_phase": None,
        "error_message": None,
        "provenance": None,
        "headline": None,
        "columns_json": "[]",
        "rows_json": "[]",
    }

    if not resolution.ok:
        base["error_phase"] = "load"
        base["error_message"] = resolution.error
        return base

    data = (resolution.node or {}).get("data") or {}
    base["provenance"] = {
        "kind": data.get("kind"),
        "source_url": data.get("source_url"),
        "fetched_at": data.get("fetched_at"),
        "size_bytes": data.get("size_bytes"),
        "signature_verified": data.get("signature_verified"),
        "signed_by": data.get("signed_by"),
        "rekor_log_index": data.get("rekor_log_index"),
        "verified_at": data.get("verified_at"),
    }

    columns, rows = _parse_csv(data.get("content"))
    base["columns_json"] = safe_json(columns)
    base["rows_json"] = safe_json(rows)
    base["headline"] = {"rows": len(rows), "columns": len(columns)}
    return base


class IiwWorkbenchPanelType:
    """Panel type for the IIW inventory workbench."""

    slug: ClassVar[str] = "samsite-iiw-workbench"
    label: ClassVar[str] = "IIW Inventory Workbench"
    view: ClassVar[str] = "samsite/panels/iiw_workbench.html"
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
