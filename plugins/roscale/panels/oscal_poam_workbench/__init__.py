"""OSCAL POA&M Workbench Panel Type — `roscale-oscal-poam-workbench`.

Renders a plan-of-action-and-milestones OSCAL document as a readable
action/risk register. Same input contract and resolution path as the
SSP workbench, including the optional latest-emission fallback via
`config.fallback.kind` — different default page variable.

Spec: plugins/roscale/specs/spec-roscale-v0.md
      (req-roscale-poam-panel, req-roscale-input, req-roscale-poam-rendering,
       req-roscale-errors)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from plugins.roscale.panels._common import (
    build_provenance,
    parse_and_validate,
    poam_headline_stats,
    poam_items,
    poam_items_by_status,
    poam_metadata,
    pretty_json,
    resolve_artifact,
)

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel


DEFAULT_VAR_NAME = "oscal_poam_artifact_entity_id"


def build_context(panel: Any, request: Any) -> dict[str, Any]:
    """Pure function — separated from the classmethod so tests can call it directly."""
    resolution = resolve_artifact(panel, request, DEFAULT_VAR_NAME)
    base: dict[str, Any] = {
        "panel_slug": "roscale-oscal-poam-workbench",
        "entity_id": resolution.entity_id,
        "var_name": resolution.var_name,
        "used_fallback": resolution.used_fallback,
        "fallback_kind": resolution.fallback_kind,
        "error_phase": None,
        "error_message": None,
        "provenance": None,
        "metadata": None,
        "validation": None,
        "headline_stats": None,
        "items": [],
        "items_by_status": [],
        "raw_json": None,
    }
    if not resolution.ok:
        base["error_phase"] = "load"
        base["error_message"] = resolution.error
        return base

    data = resolution.node.get("data") or {}
    content = data.get("content")
    base["provenance"] = build_provenance(resolution.node)

    parsed, result = parse_and_validate(content)

    if parsed.raw_content:
        base["raw_json"] = parsed.raw_content if isinstance(parsed.raw_content, str) else pretty_json(content)
    elif content is not None:
        base["raw_json"] = pretty_json(content)

    if not parsed.ok:
        first_error = parsed.errors[0] if parsed.errors else None
        base["error_phase"] = first_error.phase if first_error else "parse"
        base["error_message"] = first_error.message if first_error else "OSCAL parse failed."
        return base

    if parsed.root_key != "plan-of-action-and-milestones":
        base["error_phase"] = "root-detect"
        base["error_message"] = (
            f"Expected an OSCAL Plan of Action and Milestones; got root '{parsed.root_key}'. "
            "Use the SSP workbench panel for system-security-plan documents."
        )
        return base

    doc = parsed.document or {}
    items = poam_items(doc)
    base["metadata"] = poam_metadata(doc)
    base["headline_stats"] = poam_headline_stats(items)
    base["items"] = items
    base["items_by_status"] = poam_items_by_status(items)
    base["validation"] = {
        "schema_ok": result.schema_ok,
        "schema_errors": [{"path": e.path, "message": e.message} for e in result.schema_errors[:50]],
        "schema_errors_total": len(result.schema_errors),
        "semantic_warnings": [
            {"check": w.check, "message": w.message, "path": w.path}
            for w in result.semantic_warnings
        ],
        "schema_skipped_reason": result.schema_skipped_reason,
        "unsupported_keywords": list(result.unsupported_keywords),
    }
    return base


class OscalPoamWorkbenchPanelType:
    """Panel type for the OSCAL POA&M workbench."""

    slug: ClassVar[str] = "roscale-oscal-poam-workbench"
    label: ClassVar[str] = "OSCAL POA&M Workbench"
    view: ClassVar[str] = "roscale/panels/oscal_poam_workbench.html"
    css: ClassVar[list[str]] = ["roscale/css/workbench.css"]
    js: ClassVar[list[str]] = []
    config_defaults: ClassVar[dict[str, Any]] = {
        "artifact_entity_id_var": DEFAULT_VAR_NAME,
    }

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        return build_context(panel, request)
