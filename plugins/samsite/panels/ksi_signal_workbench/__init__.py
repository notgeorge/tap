"""KSI Signal Workbench Panel Type — `samsite-ksi-signal-workbench`.

Renders one FedRAMP 20x KSI signal as a classy compliance workbench, in the
spirit of the roscale OSCAL workbench: a trust band (signature + disclosure),
headline stats, the signal's declared components (grouped table), its
validations, any violations, and signal metadata + provenance as footers.

The signal is resolved via ``tap_web.panels.entity_resolution`` (URL deep link
via ``ksi_signal_entity_id`` wins; else the fallback query picks the latest
emission). The decomposed children are recomposed by walking the
``DECLARES_COMPONENT`` / ``DECLARES_VALIDATION`` / ``REPORTS_VIOLATION`` edges
with Gryphon — each traversal returns the matched subgraph envelope, which we
filter to the child node type.

Resolution contract: tap_web/specs/spec-web-panel-entity-resolution-v0.md
"""

from __future__ import annotations

from collections import Counter
from typing import Any, ClassVar

from django.http import HttpRequest

from tap_grid.gryphon.executor import execute_gryphon_raw
from tap_web.models import Panel
from tap_web.panels.entity_resolution import resolve_entity

DEFAULT_VAR_NAME = "ksi_signal_entity_id"


def _children(signal_entity_id: str, edge_type: str, child_type: str) -> list[dict[str, Any]]:
    """Walk one edge type from the signal; return the child nodes' ``data`` dicts.

    The traversal envelope includes the source signal node too, so filter to
    the requested child type.
    """
    query = f"MATCH (s:ksi_signal)-[:{edge_type}]->(c:{child_type}) WHERE s.entity_id = $id RETURN c"
    envelope = execute_gryphon_raw(query, {"id": signal_entity_id}, layer="extended")
    return [n.get("data") or {} for n in (envelope.get("nodes") or []) if n.get("entity_type") == child_type]


def _component_family(component_id: str, component_type: str) -> str:
    """Coarse grouping family from the component_id prefix.

    Collapses every AWS resource type under one "AWS" family; non-AWS prefixes
    map to their natural family; anything else falls back to its type.
    """
    if component_id.startswith("aws::"):
        return "AWS"
    if component_id.startswith("ext::"):
        return "External services"
    if component_id.startswith("html::"):
        return "HTML artifacts"
    if component_id.startswith("npm::"):
        return "npm packages"
    return component_type or "Other"


def _component_identifier(c: dict[str, Any]) -> str:
    """The component's most specific global/native identifier, in priority order."""
    return c.get("native_id") or c.get("global_purl") or c.get("global_sha256") or c.get("global_image_digest") or ""


def build_context(panel: Any, request: Any) -> dict[str, Any]:
    """Pure function — separated from the classmethod so tests can call it directly."""
    resolution = resolve_entity(panel, request, default_var_name=DEFAULT_VAR_NAME)
    base: dict[str, Any] = {
        "panel_slug": "samsite-ksi-signal-workbench",
        "entity_id": resolution.entity_id,
        "var_name": resolution.var_name,
        "used_fallback": resolution.used_fallback,
        "fallback_description": resolution.fallback_description,
        "fallback_count": resolution.fallback_count,
        "error_phase": None,
        "error_message": None,
        "signal": None,
        "provenance": None,
        "disclosure": None,
        "headline": None,
        "component_groups": [],
        "validations": [],
        "violations": [],
    }

    if not resolution.ok:
        base["error_phase"] = "load"
        base["error_message"] = resolution.error
        return base

    data = (resolution.node or {}).get("data") or {}
    sid = resolution.entity_id

    base["signal"] = {
        "signal_id": data.get("signal_id"),
        "emitted_at": data.get("emitted_at"),
        "emitter": data.get("emitter"),
        "csp": data.get("csp"),
        "system_id": data.get("system_id"),
    }
    base["provenance"] = {
        "signature_verified": data.get("signature_verified"),
        "signed_by": data.get("signed_by"),
        "rekor_log_index": data.get("rekor_log_index"),
        "verified_at": data.get("verified_at"),
        "source_repository": data.get("provenance_source_repository"),
        "source_commit": data.get("provenance_source_commit"),
    }
    base["disclosure"] = {
        "fedramp_certified": data.get("fedramp_certified"),  # True / False / None — unknown != false
        "authorization_status": data.get("authorization_status"),
        "remarks": data.get("disclosure_remarks"),
    }

    components = _children(sid, "DECLARES_COMPONENT", "ksi_component")
    validations = _children(sid, "DECLARES_VALIDATION", "ksi_validation")
    violations = _children(sid, "REPORTS_VIOLATION", "ksi_violation")

    comp_rows = [
        {
            "component_id": c.get("component_id"),
            "component_type": c.get("component_type") or "(none)",
            "identifier": _component_identifier(c),
            "c": c.get("security_confidentiality"),
            "i": c.get("security_integrity"),
            "a": c.get("security_availability"),
        }
        for c in components
    ]
    # Group by component family (component_id prefix), not by individual type:
    # all AWS resource types collapse under one "AWS" heading — janky but
    # information-rich (the specific type stays in the Type column).
    fam_order = ["AWS", "External services", "HTML artifacts", "npm packages"]
    fam_rank = {f: i for i, f in enumerate(fam_order)}
    for r in comp_rows:
        r["family"] = _component_family(r["component_id"] or "", r["component_type"])
    fam_counts = Counter(r["family"] for r in comp_rows)
    base["component_groups"] = [
        {
            "label": f,
            "count": fam_counts[f],
            "items": sorted(
                (r for r in comp_rows if r["family"] == f),
                key=lambda r: (r["component_type"] or "", r["component_id"] or ""),
            ),
        }
        for f in sorted(fam_counts, key=lambda f: (fam_rank.get(f, 99), f))
    ]

    base["validations"] = sorted(
        (
            {
                "validation_id": v.get("validation_id"),
                "result": (v.get("result") or "").lower(),
                "policy_id": v.get("policy_id"),
                "policy_version": v.get("policy_version"),
            }
            for v in validations
        ),
        key=lambda v: v["validation_id"] or "",
    )
    base["violations"] = [
        {
            "violation_type": v.get("violation_type"),
            "severity": v.get("severity"),
            "resource": v.get("resource"),
            "message": v.get("message"),
        }
        for v in violations
    ]

    passed = sum(1 for v in base["validations"] if v["result"] == "pass")
    base["headline"] = {
        "components_total": len(comp_rows),
        "component_type_count": len({r["component_type"] for r in comp_rows}),
        "validations_total": len(base["validations"]),
        "validations_passed": passed,
        "validations_failed": len(base["validations"]) - passed,
        "violations_total": len(base["violations"]),
    }
    return base


class KsiSignalWorkbenchPanelType:
    """Panel type for the KSI signal workbench."""

    slug: ClassVar[str] = "samsite-ksi-signal-workbench"
    label: ClassVar[str] = "KSI Signal Workbench"
    view: ClassVar[str] = "samsite/panels/ksi_signal_workbench.html"
    css: ClassVar[list[str]] = ["samsite/css/viewers.css"]
    js: ClassVar[list[str]] = []
    config_defaults: ClassVar[dict[str, Any]] = {"entity_id_var": DEFAULT_VAR_NAME}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        return build_context(panel, request)
