"""Shared row-building helpers for the Findings page panels.

The findings_by_system and findings_by_ksi panels render the same dataset
(all open findings with their HAS_COMPLIANCE_FINDING parent and any RELATED_INDICATOR
linkage) under different group-by lenses. This module centralizes the
envelope→row flattening so both panels stay in sync. See
spec-fedramp-20x-ksi-findings-page.md.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


def build_findings_rows(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    """Walk the gryphon subgraph envelope and emit a flat row payload.

    Envelope shape: each node is {"entity": {...}, "node": {...}, ...} with
    entity-spine fields under "entity" and domain fields under "node". Edges
    follow the same nested shape under "entity" / "edge".

    Each row carries everything either panel needs:
      finding_id, title, system_name, system_id, summary, description,
      ksi_id, ksi_code, ksi_name, ksi_relationship, created_at, age_days.
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
        if et == "HAS_COMPLIANCE_FINDING__compliance_core":
            finding_id = edge_body.get("to_entity_id")
            parent_id = edge_body.get("from_entity_id")
            if finding_id and parent_id and finding_id not in parents_by_finding:
                parents_by_finding[finding_id] = parent_id
        elif et == "RELATED_INDICATOR__fedramp_20x_ksi":
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
        if ent.get("entity_type") != "compliance_core__compliance_finding":
            continue

        finding_id = ent.get("entity_id")
        if not finding_id:
            continue

        parent_id = parents_by_finding.get(finding_id)
        parent = nodes_by_id.get(parent_id or "") if parent_id else None

        finding_body = n.get("node") or {}
        parent_ent = (parent or {}).get("entity") or {}
        parent_body = (parent or {}).get("node") or {}

        ksi_link = ksi_links_by_finding.get(finding_id) or {}
        ksi_id = ksi_link.get("ksi_id") or ""
        ksi_code = ""
        ksi_name = ""
        if ksi_id:
            ksi_node = nodes_by_id.get(ksi_id) or {}
            ksi_body = ksi_node.get("node") or {}
            ksi_ent = ksi_node.get("entity") or {}
            ksi_code = ksi_body.get("code") or ""
            ksi_name = ksi_ent.get("name") or ksi_body.get("name") or ""

        created_at = ent.get("created_at")
        rows.append(
            {
                "finding_id": finding_id,
                "title": ent.get("name") or finding_body.get("name") or "",
                "system_name": parent_ent.get("name") or parent_body.get("name") or "",
                "system_id": parent_id or "",
                "summary": finding_body.get("summary") or "",
                "description": finding_body.get("description") or "",
                "ksi_id": ksi_id,
                "ksi_code": ksi_code,
                "ksi_name": ksi_name,
                "ksi_relationship": ksi_link.get("relationship", ""),
                "created_at": created_at,
                "age_days": _age_in_days(created_at),
            }
        )

    rows.sort(
        key=lambda r: (
            r["age_days"] if r["age_days"] is not None else 10**9,
            -(_iso_to_epoch(r["created_at"]) or 0),
        )
    )
    return rows


def _age_in_days(created_at_iso: str | None) -> int | None:
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
