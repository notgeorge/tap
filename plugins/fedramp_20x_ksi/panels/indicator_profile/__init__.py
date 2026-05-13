"""FedRAMP 20x KSI Indicator Profile — plugin-owned panel type.

Displays a single KSI indicator's full profile: hero header, requirement
statement with class-variant toggle, NIST controls, terms, references,
and change log. Data is loaded via a gryphon hub-and-spoke query that
returns the indicator and its parent theme in one pass.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, ClassVar

from tap_web.utils import safe_json


def _parse_iso(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _format_timestamp_full(iso: str | None) -> str:
    dt = _parse_iso(iso)
    return dt.strftime("%Y-%m-%d %H:%M UTC") if dt else ""


def _relative_timestamp(iso: str | None) -> str:
    dt = _parse_iso(iso)
    if dt is None:
        return ""
    now = datetime.now(timezone.utc)
    seconds = (now - dt).total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    days = int(seconds // 86400)
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days}d ago"
    if dt.year == now.year:
        return dt.strftime("%b %-d")
    return dt.strftime("%b %-d, %Y")

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel

logger = logging.getLogger(__name__)

CLASS_LABELS: dict[str, str] = {
    "a": "Class A — Pilot",
    "b": "Class B — Low",
    "c": "Class C — Moderate",
    "d": "Class D — High",
}


class KsiIndicatorProfilePanelType:
    """Panel type for the FedRAMP 20x KSI indicator profile page."""

    slug: ClassVar[str] = "fedramp-20x-ksi-indicator-profile"
    label: ClassVar[str] = "FedRAMP 20x KSI Indicator Profile"
    view: ClassVar[str] = "fedramp_20x_ksi/panels/indicator_profile.html"
    css: ClassVar[list[str]] = [
        "tap_web/css/lib/tabulator.min.css",
        "fedramp_20x_ksi/css/panel-ksi-indicator-profile.css",
    ]
    js: ClassVar[list[str]] = [
        "tap_web/js/lib/tabulator.min.js",
        "fedramp_20x_ksi/js/panel-ksi-indicator-profile.js",
    ]
    config_defaults: ClassVar[dict[str, Any]] = {}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        """Load the indicator + neighborhood and build template context."""
        entity_id = request.GET.get("entity_id", "")
        if not entity_id:
            return {"ksi_error": "No indicator specified.", "ksi": None}

        try:
            from tap_grid.models import Search
            from tap_grid.search import execute_search

            search = Search(
                search_type="gryphon",
                root="node",
                name="ksi-indicator-profile",
                definition={
                    "query": [
                        "MATCH (hub)-[e]-(neighbor)",
                        "WHERE hub.entity_id = $entity_id",
                        "RETURN hub, e, neighbor",
                    ]
                },
                default_limit=50,
                max_limit=100,
            )
            result = execute_search(
                search, inputs={"entity_id": entity_id}, layer="extended"
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("KSI profile search failed for %s", entity_id)
            return {"ksi_error": f"Failed to load indicator: {exc}", "ksi": None}

        # Extract subgraph from paginated or flat result.
        if "results" in result:
            subgraph = result["results"]
        else:
            subgraph = result

        nodes = subgraph.get("nodes", [])

        # Find the indicator (hub) and parent theme.
        indicator = None
        theme = None
        for n in nodes:
            etype = n.get("entity", {}).get("entity_type", "")
            eid = n.get("entity", {}).get("entity_id", "")
            if eid == entity_id:
                indicator = n
            elif etype == "ksi_theme":
                theme = n

        if indicator is None:
            return {"ksi_error": "Indicator not found.", "ksi": None}

        ind_node = indicator.get("node", {})
        ind_entity = indicator.get("entity", {})
        theme_node = theme.get("node", {}) if theme else {}
        theme_entity = theme.get("entity", {}) if theme else {}

        has_variants = bool(ind_node.get("class_variants"))

        # Resolve the initial display statement.
        # For direct-statement indicators: use description.
        # For class_variant indicators: use the first class's statement.
        display_statement = ind_node.get("description", "")
        if has_variants and not display_statement:
            cv = ind_node["class_variants"]
            first_class = (
                ind_node.get("classes", [])[0] if ind_node.get("classes") else None
            )
            if first_class and first_class in cv:
                display_statement = cv[first_class].get("statement", "")
            elif cv:
                display_statement = next(iter(cv.values())).get("statement", "")

        ksi = {
            "entity_id": ind_entity.get("entity_id", ""),
            "code": ind_node.get("code", ""),
            "name": ind_node.get("name", ""),
            "description": ind_node.get("description", ""),
            "classes": ind_node.get("classes", []),
            "class_variants": ind_node.get("class_variants"),
            "has_variants": has_variants,
            "controls": ind_node.get("controls", []),
            "status": ind_node.get("status", ""),
            "terms": ind_node.get("terms", []),
            "reference": ind_node.get("reference", ""),
            "reference_url": ind_node.get("reference_url", ""),
            "updated_log": ind_node.get("updated_log", []),
            "theme_code": theme_node.get("code", ""),
            "theme_name": theme_entity.get("name", theme_node.get("name", "")),
            "theme_short_name": theme_node.get("short_name", ""),
            "theme_icon_url": theme.get("icon_url", "") if theme else "",
        }

        # Build class label map for the template.
        class_info = []
        for c in ksi["classes"]:
            class_info.append({"key": c, "label": CLASS_LABELS.get(c, c.upper())})

        findings_rows = _load_findings_rows(entity_id)

        return {
            "ksi": ksi,
            "ksi_display_statement": display_statement,
            "ksi_class_info": class_info,
            "ksi_variants_json": (
                safe_json(ksi["class_variants"]) if has_variants else "null"
            ),
            "ksi_findings_json": safe_json(findings_rows),
            "ksi_findings_count": len(findings_rows),
            "ksi_error": None,
        }


def _load_findings_rows(indicator_entity_id: str) -> list[dict[str, Any]]:
    """Two-hop query: findings linked to this indicator + their HAS_FINDING parents.

    Returns flat (system, finding) row pairs. A finding with multiple parents
    emits multiple rows; a finding with none emits a single row with an empty
    system cell. Sorted with open findings first, newest within status group.
    """
    try:
        from tap_grid.models import Search
        from tap_grid.search import execute_search

        search = Search(
            search_type="gryphon",
            root="node",
            name="ksi-indicator-findings",
            definition={
                "query": [
                    "MATCH (i)<-[r1:RELATED_INDICATOR]-(f:finding)",
                    "MATCH (s)-[r2:HAS_FINDING]->(f)",
                    "WHERE i.entity_id = $entity_id",
                    "RETURN f, r1, r2, s",
                ]
            },
            default_limit=500,
            max_limit=2000,
        )
        result = execute_search(
            search, inputs={"entity_id": indicator_entity_id}, layer="extended"
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "KSI indicator findings query failed for %s", indicator_entity_id
        )
        return []

    envelope = result["results"] if "results" in result else result
    nodes = envelope.get("nodes", [])
    edges = envelope.get("edges", [])

    nodes_by_id: dict[str, dict[str, Any]] = {}
    for n in nodes:
        ent = n.get("entity") or {}
        eid = ent.get("entity_id")
        if eid:
            nodes_by_id[eid] = n

    # Map finding_id -> [parent_system_id, ...] from HAS_FINDING edges.
    parents_by_finding: dict[str, list[str]] = {}
    for edge in edges:
        ebody = edge.get("edge") or {}
        if ebody.get("edge_type") != "HAS_FINDING":
            continue
        fid = ebody.get("to_entity_id")
        sid = ebody.get("from_entity_id")
        if fid and sid:
            parents_by_finding.setdefault(fid, []).append(sid)

    # Walk RELATED_INDICATOR edges that target this indicator. Each edge carries
    # the per-link verdict in `relationship_type` (violation / passing /
    # informational). We render this as the row's status pill instead of the
    # finding's lifecycle status — the user-facing question on this page is
    # "is this finding a violation or passing of *this* indicator", not "is the
    # finding open or resolved." See spec-fedramp-20x-ksi-finding.md
    # req-fedramp-20x-ksi-finding-related-edge.
    finding_ids: list[str] = []
    relationship_by_finding: dict[str, str] = {}
    seen_findings: set[str] = set()
    for edge in edges:
        ebody = edge.get("edge") or {}
        if ebody.get("edge_type") != "RELATED_INDICATOR":
            continue
        if ebody.get("to_entity_id") != indicator_entity_id:
            continue
        fid = ebody.get("from_entity_id")
        if fid and fid not in seen_findings:
            seen_findings.add(fid)
            finding_ids.append(fid)
            props = ebody.get("properties") or {}
            relationship_by_finding[fid] = props.get("relationship_type", "") or ""

    rows: list[dict[str, Any]] = []
    for fid in finding_ids:
        f_node = nodes_by_id.get(fid)
        if f_node is None:
            continue
        f_ent = f_node.get("entity") or {}
        f_body = f_node.get("node") or {}
        f_name = f_ent.get("name") or f_body.get("name") or ""
        f_relationship = relationship_by_finding.get(fid, "")
        f_desc = f_body.get("description", "")
        f_created_iso = f_ent.get("created_at")
        opened_relative = _relative_timestamp(f_created_iso)
        opened_full = _format_timestamp_full(f_created_iso)

        parent_ids = parents_by_finding.get(fid, [])
        if not parent_ids:
            rows.append(
                {
                    "finding_id": fid,
                    "finding_name": f_name,
                    "finding_relationship": f_relationship,
                    "finding_description": f_desc,
                    "system_id": "",
                    "system_name": "",
                    "opened_relative": opened_relative,
                    "opened_full": opened_full,
                }
            )
            continue
        for sid in parent_ids:
            s_node = nodes_by_id.get(sid) or {}
            s_ent = s_node.get("entity") or {}
            s_body = s_node.get("node") or {}
            rows.append(
                {
                    "finding_id": fid,
                    "finding_name": f_name,
                    "finding_relationship": f_relationship,
                    "finding_description": f_desc,
                    "system_id": sid,
                    "system_name": s_ent.get("name") or s_body.get("name") or "",
                    "opened_relative": opened_relative,
                    "opened_full": opened_full,
                }
            )

    # Violations first, then passing, then informational, then unknown.
    # Two-pass stable sort: secondary key first (created desc), then primary
    # (relationship-type rank).
    _REL_RANK = {"violation": 0, "passing": 1, "informational": 2}
    rows.sort(key=lambda r: r["opened_full"], reverse=True)
    rows.sort(key=lambda r: _REL_RANK.get(r["finding_relationship"], 9))
    return rows
