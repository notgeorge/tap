"""FedRAMP 20x KSI Finding Profile — plugin-owned panel type.

Displays a single Finding's full story: hero header with status, identity
section (system(s), description), related KSI table, and evidence table with
click-to-expand details. Data is loaded via a gryphon hub-and-spoke query
that returns the finding plus everything connected by HAS_FINDING (inbound),
RELATED_INDICATOR (outbound), and HAS_EVIDENCE (outbound) edges in one pass.

Spec: plugins/fedramp_20x_ksi/specs/spec-fedramp-20x-ksi-finding-profile.md
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from tap_web.utils import safe_json

# Verdict aggregation deferred — see spec-fedramp-20x-ksi-finding.md
# req-fedramp-20x-ksi-finding-verdict-rollup (Backlog). The hero pill was
# removed from finding_profile.html until the rollup rule is spec'd.


# Class precedence for picking a single requirement statement when an indicator's
# requirement varies by class (the FedRAMP catalog uses Shape B: per-class
# statements under varies_by_class). We prefer Class C (High impact) since it is
# the strictest applicable variant, then B, A, D. Indicators with a direct
# top-level `description` (Shape A) skip this fallback path.
_CLASS_PRECEDENCE = ("c", "b", "a", "d")


def _ksi_description(ksi_body: dict[str, Any]) -> str:
    """Return the indicator's requirement text, falling back to class_variants
    when the top-level `description` is empty. See refresh.py / req-fedramp-20x-ksi-*
    for the upstream Shape A vs Shape B distinction."""
    direct = (ksi_body.get("description") or "").strip()
    if direct:
        return direct
    variants = ksi_body.get("class_variants") or {}
    if not isinstance(variants, dict):
        return ""
    for cls in _CLASS_PRECEDENCE:
        entry = variants.get(cls)
        if not isinstance(entry, dict):
            continue
        statement = (entry.get("statement") or "").strip()
        if statement:
            return statement
    # Last resort: any class statement we can find.
    for entry in variants.values():
        if not isinstance(entry, dict):
            continue
        statement = (entry.get("statement") or "").strip()
        if statement:
            return statement
    return ""


def _parse_iso(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError, TypeError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _format_timestamp(iso: str | None) -> str:
    dt = _parse_iso(iso)
    return dt.strftime("%Y-%m-%d %H:%M UTC") if dt else ""


def _relative_timestamp(iso: str | None) -> str:
    """Short, human-friendly relative label. Pairs with a tooltip showing the full timestamp."""
    dt = _parse_iso(iso)
    if dt is None:
        return ""
    now = datetime.now(UTC)
    delta = now - dt
    seconds = delta.total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        m = int(seconds // 60)
        return f"{m}m ago"
    if seconds < 86400:
        h = int(seconds // 3600)
        return f"{h}h ago"
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


class KsiFindingProfilePanelType:
    """Panel type for the FedRAMP 20x KSI finding profile page."""

    slug: ClassVar[str] = "fedramp-20x-ksi-finding-profile"
    label: ClassVar[str] = "FedRAMP 20x KSI Finding Profile"
    view: ClassVar[str] = "fedramp_20x_ksi/panels/finding_profile.html"
    css: ClassVar[list[str]] = [
        "tap_web/css/lib/tabulator.min.css",
        "fedramp_20x_ksi/css/panel-ksi-finding-profile.css",
    ]
    js: ClassVar[list[str]] = [
        "tap_web/js/lib/tabulator.min.js",
        "fedramp_20x_ksi/js/panel-ksi-finding-profile.js",
    ]
    config_defaults: ClassVar[dict[str, Any]] = {}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        """Load the finding + neighborhood and build template context."""
        entity_id = request.GET.get("entity_id", "")
        if not entity_id:
            return {"finding_error": "No finding specified.", "finding": None}

        try:
            from tap_grid.models import Search
            from tap_grid.search import execute_search

            search = Search(
                search_type="gryphon",
                root="node",
                name="ksi-finding-profile",
                definition={
                    "query": [
                        "MATCH (hub)-[e]-(neighbor)",
                        "WHERE hub.entity_id = $entity_id",
                        "RETURN hub, e, neighbor",
                    ]
                },
                default_limit=200,
                max_limit=500,
            )
            result = execute_search(search, inputs={"entity_id": entity_id}, layer="extended")
        except Exception as exc:  # noqa: BLE001
            logger.exception("[52c8] Finding profile search failed for %s", entity_id)
            return {
                "finding_error": f"Failed to load finding: {exc}",
                "finding": None,
            }

        envelope = result["results"] if "results" in result else result
        nodes = envelope.get("nodes", [])
        edges = envelope.get("edges", [])

        nodes_by_id: dict[str, dict[str, Any]] = {}
        for n in nodes:
            ent = n.get("entity") or {}
            eid = ent.get("entity_id")
            if eid:
                nodes_by_id[eid] = n

        finding_node = nodes_by_id.get(entity_id)
        if finding_node is None or (finding_node.get("entity") or {}).get("entity_type") != "finding":
            return {"finding_error": "Finding not found.", "finding": None}

        f_ent = finding_node.get("entity") or {}
        f_body = finding_node.get("node") or {}

        systems: list[dict[str, Any]] = []
        ksis: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []

        for edge in edges:
            ebody = edge.get("edge") or {}
            etype = ebody.get("edge_type")
            from_id = ebody.get("from_entity_id")
            to_id = ebody.get("to_entity_id")
            props = ebody.get("properties") or {}

            if etype == "HAS_FINDING" and to_id == entity_id:
                sys_node = nodes_by_id.get(from_id or "")
                if sys_node is None:
                    continue
                sys_ent = sys_node.get("entity") or {}
                sys_body = sys_node.get("node") or {}
                systems.append(
                    {
                        "entity_id": sys_ent.get("entity_id", ""),
                        "entity_type": sys_ent.get("entity_type", ""),
                        "name": sys_ent.get("name") or sys_body.get("name") or "",
                    }
                )
            elif etype == "RELATED_INDICATOR" and from_id == entity_id:
                ksi_node = nodes_by_id.get(to_id or "")
                if ksi_node is None:
                    continue
                ksi_ent = ksi_node.get("entity") or {}
                ksi_body = ksi_node.get("node") or {}
                ksis.append(
                    {
                        "entity_id": ksi_ent.get("entity_id", ""),
                        "code": ksi_body.get("code", ""),
                        "name": ksi_ent.get("name") or ksi_body.get("name") or "",
                        "description": _ksi_description(ksi_body),
                        "relationship_type": props.get("relationship_type", ""),
                    }
                )
            elif etype == "HAS_EVIDENCE" and from_id == entity_id:
                ev_node = nodes_by_id.get(to_id or "")
                if ev_node is None:
                    continue
                ev_ent = ev_node.get("entity") or {}
                ev_body = ev_node.get("node") or {}
                ev_created_iso = ev_ent.get("created_at")
                ev_updated_iso = ev_ent.get("updated_at")
                evidence.append(
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

        systems.sort(key=lambda s: s["entity_id"])
        ksis.sort(key=lambda k: (k["code"], k["entity_id"]))
        evidence.sort(key=lambda e: (e["support_kind"], e["name"], e["entity_id"]))

        f_created_iso = f_ent.get("created_at")
        f_updated_iso = f_ent.get("updated_at")
        finding = {
            "entity_id": f_ent.get("entity_id", ""),
            "name": f_ent.get("name") or f_body.get("name") or "",
            "summary": f_body.get("summary", ""),
            "description": f_body.get("description", ""),
            "status": f_body.get("status", ""),
            "created_full": _format_timestamp(f_created_iso),
            "updated_full": _format_timestamp(f_updated_iso),
            "created_relative": _relative_timestamp(f_created_iso),
            "updated_relative": _relative_timestamp(f_updated_iso),
        }

        system_label = "System" if len(systems) == 1 else "Systems"

        return {
            "finding": finding,
            "finding_system_label": system_label,
            "finding_systems": systems,
            "finding_ksis_json": safe_json(ksis),
            "finding_evidence_json": safe_json(evidence),
            "finding_ksis_count": len(ksis),
            "finding_evidence_count": len(evidence),
            "finding_error": None,
        }
