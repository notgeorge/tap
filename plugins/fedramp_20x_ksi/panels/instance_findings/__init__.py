"""FedRAMP 20x KSI Instance Findings — plugin-owned panel type.

Asset-scoped findings panel: lists every Finding attached to a single asset
(e.g. an EC2 instance) with each row inline-expandable to reveal description,
related KSI indicators, and supporting evidence. Mirrors the dedicated finding
profile's chevron + evidence-detail pattern for visual continuity.

Spec: plugins/fedramp_20x_ksi/specs/spec-fedramp-20x-ksi-instance-findings.md
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from tap_web.utils import safe_json

from plugins.fedramp_20x_ksi.panels.finding_profile import (
    _format_timestamp,
    _ksi_description,
    _relative_timestamp,
)

# Aggregated-verdict precedence for HAS_EVIDENCE.support_kind values: any
# violation wins; otherwise any passing wins; otherwise informational.
# (Mirrors the precedence used elsewhere in the plugin; defined locally because
# the helper is not exported from finding_profile.)
_VERDICT_PRIORITY_AGG = {"violation": 3, "passing": 2, "informational": 1}


def _aggregate_verdict(evidence_list: list[dict[str, Any]]) -> str:
    best = ("", 0)
    for ev in evidence_list:
        sk = ev.get("support_kind") or ""
        weight = _VERDICT_PRIORITY_AGG.get(sk, 0)
        if weight > best[1]:
            best = (sk, weight)
    return best[0]

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel

logger = logging.getLogger(__name__)


class KsiInstanceFindingsPanelType:
    """Panel type for the asset-scoped instance findings table."""

    slug: ClassVar[str] = "fedramp-20x-ksi-instance-findings"
    label: ClassVar[str] = "FedRAMP 20x KSI Instance Findings"
    view: ClassVar[str] = "fedramp_20x_ksi/panels/instance_findings.html"
    css: ClassVar[list[str]] = [
        "tap_web/css/lib/tabulator.min.css",
        "fedramp_20x_ksi/css/panel-ksi-instance-findings.css",
    ]
    js: ClassVar[list[str]] = [
        "tap_web/js/lib/tabulator.min.js",
        "fedramp_20x_ksi/js/panel-ksi-instance-findings.js",
    ]
    config_defaults: ClassVar[dict[str, Any]] = {}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        entity_id = request.GET.get("entity_id", "")
        if not entity_id:
            return {
                "instance_findings_error": "No asset specified.",
                "instance_findings_rows_json": safe_json([]),
                "instance_findings_count": 0,
            }

        try:
            from tap_web.panel import get_panel_search

            search = get_panel_search(panel)
            if search is None:
                return {
                    "instance_findings_error": "No search linked to this panel.",
                    "instance_findings_rows_json": safe_json([]),
                    "instance_findings_count": 0,
                }
            from tap_grid.search import execute_search

            result = execute_search(
                search, inputs={"entity_id": entity_id}, layer="extended"
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[efc9] Instance findings search failed for %s", entity_id)
            return {
                "instance_findings_error": f"Failed to load findings: {exc}",
                "instance_findings_rows_json": safe_json([]),
                "instance_findings_count": 0,
            }

        envelope = result["results"] if "results" in result else result
        rows = _build_rows(envelope, entity_id)

        return {
            "instance_findings_error": None,
            "instance_findings_rows_json": safe_json(rows),
            "instance_findings_count": len(rows),
        }


def _build_rows(envelope: dict[str, Any], asset_id: str) -> list[dict[str, Any]]:
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for n in envelope.get("nodes", []):
        ent = n.get("entity") or {}
        eid = ent.get("entity_id")
        if eid:
            nodes_by_id[eid] = n

    findings_by_id: dict[str, dict[str, Any]] = {}
    for n in envelope.get("nodes", []):
        ent = n.get("entity") or {}
        if ent.get("entity_type") != "finding":
            continue
        fid = ent.get("entity_id")
        if not fid:
            continue
        body = n.get("node") or {}
        if (body.get("status") or "open") != "open":
            continue
        findings_by_id[fid] = {
            "entity_id": fid,
            "entity": ent,
            "body": body,
            "ksis": [],
            "evidence": [],
        }

    asset_findings: set[str] = set()
    for edge in envelope.get("edges", []):
        ebody = edge.get("edge") or {}
        et = ebody.get("edge_type")
        from_id = ebody.get("from_entity_id")
        to_id = ebody.get("to_entity_id")
        props = ebody.get("properties") or {}

        if et == "HAS_FINDING" and from_id == asset_id and to_id in findings_by_id:
            asset_findings.add(to_id)
        elif et == "RELATED_INDICATOR" and from_id in findings_by_id:
            ksi_node = nodes_by_id.get(to_id or "")
            if ksi_node is None:
                continue
            ksi_ent = ksi_node.get("entity") or {}
            ksi_body = ksi_node.get("node") or {}
            findings_by_id[from_id]["ksis"].append(
                {
                    "entity_id": ksi_ent.get("entity_id", ""),
                    "code": ksi_body.get("code", ""),
                    "name": ksi_ent.get("name") or ksi_body.get("name") or "",
                    "description": _ksi_description(ksi_body),
                    "relationship_type": props.get("relationship_type", ""),
                }
            )
        elif et == "HAS_EVIDENCE" and from_id in findings_by_id:
            ev_node = nodes_by_id.get(to_id or "")
            if ev_node is None:
                continue
            ev_ent = ev_node.get("entity") or {}
            ev_body = ev_node.get("node") or {}
            ev_created_iso = ev_ent.get("created_at")
            ev_updated_iso = ev_ent.get("updated_at")
            findings_by_id[from_id]["evidence"].append(
                {
                    "entity_id": ev_ent.get("entity_id", ""),
                    "name": ev_ent.get("name") or ev_body.get("name") or "",
                    "kind": ev_body.get("kind", ""),
                    "description": ev_body.get("description", ""),
                    "support_kind": props.get("support_kind", ""),
                    "note": props.get("note", ""),
                    "updated_relative": _relative_timestamp(ev_updated_iso),
                    "timestamp_tooltip": (
                        f"Created: {_format_timestamp(ev_created_iso)}\n"
                        f"Updated: {_format_timestamp(ev_updated_iso)}"
                    ),
                }
            )

    rows: list[dict[str, Any]] = []
    for fid in asset_findings:
        f = findings_by_id[fid]
        ent = f["entity"]
        body = f["body"]
        f["evidence"].sort(
            key=lambda e: (e["support_kind"], e["name"], e["entity_id"])
        )
        f["ksis"].sort(key=lambda k: (k["code"], k["entity_id"]))
        primary_ksi = f["ksis"][0] if f["ksis"] else {}
        # Verdict precedence: aggregate-from-evidence wins, then the
        # RELATED_INDICATOR.relationship_type signal (so a violation finding
        # without seeded evidence still reads as "violation"), then the raw
        # lifecycle status as a final fallback.
        verdict = (
            _aggregate_verdict(f["evidence"])
            or primary_ksi.get("relationship_type", "")
            or (body.get("status") or "open")
        )
        created_iso = ent.get("created_at")
        rows.append(
            {
                "finding_id": fid,
                "name": ent.get("name") or body.get("name") or "",
                "summary": body.get("summary") or "",
                "description": body.get("description") or "",
                "verdict": verdict,
                "ksi_code": primary_ksi.get("code", ""),
                "ksi_name": primary_ksi.get("name", ""),
                "age_relative": _relative_timestamp(created_iso),
                "ksis": f["ksis"],
                "evidence": f["evidence"],
            }
        )

    rows.sort(key=lambda r: (-_VERDICT_PRIORITY.get(r["verdict"], 0), r["name"]))
    return rows


_VERDICT_PRIORITY = {"violation": 3, "open": 2, "informational": 1, "passing": 0}
