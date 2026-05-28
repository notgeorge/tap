"""OSCAL SSP Workbench Panel Type — `roscale-oscal-workbench`.

Renders a system-security-plan OSCAL document as a single-page compliance
workbench. Resolves the underlying `compliance_artifact` via the canonical
entity-resolution helper at `tap_web.panels.entity_resolution`: URL deep
link wins via `entity_id_var`; otherwise the panel's `fallback.query`
Gryphon query picks the latest emission.

Spec: plugins/roscale/specs/spec-roscale-v0.md
      (req-roscale-panel, req-roscale-input, req-roscale-rendering,
       req-roscale-errors)
Resolution contract: tap_web/specs/spec-web-panel-entity-resolution-v0.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from plugins.roscale.panels._common import (
    build_provenance,
    parse_and_validate,
    pretty_json,
    ssp_back_matter,
    ssp_components,
    ssp_headline_stats,
    ssp_implemented_requirements,
    ssp_implemented_requirements_by_family,
    ssp_metadata,
    ssp_self_attestation_signal,
    ssp_system_overview,
    ssp_users,
)
from tap_web.panels.entity_resolution import resolve_entity

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel


DEFAULT_VAR_NAME = "oscal_ssp_artifact_entity_id"


def build_context(panel: Any, request: Any) -> dict[str, Any]:
    """Pure function — separated from the classmethod so tests can call it directly."""
    resolution = resolve_entity(panel, request, default_var_name=DEFAULT_VAR_NAME)
    base: dict[str, Any] = {
        "panel_slug": "roscale-oscal-workbench",
        "entity_id": resolution.entity_id,
        "var_name": resolution.var_name,
        "used_fallback": resolution.used_fallback,
        "fallback_description": resolution.fallback_description,
        "error_phase": None,
        "error_message": None,
        "provenance": None,
        "metadata": None,
        "validation": None,
        "system_overview": None,
        "self_attestation": None,
        "headline_stats": None,
        "components": [],
        "users": [],
        "requirements_by_family": [],
        "back_matter": [],
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

    if parsed.root_key != "system-security-plan":
        base["error_phase"] = "root-detect"
        base["error_message"] = (
            f"Expected an OSCAL System Security Plan; got root '{parsed.root_key}'. "
            "Use the POA&M workbench panel for plan-of-action-and-milestones documents."
        )
        return base

    doc = parsed.document or {}
    impl_reqs = ssp_implemented_requirements(doc)
    base["metadata"] = ssp_metadata(doc)
    base["system_overview"] = ssp_system_overview(doc)
    base["self_attestation"] = ssp_self_attestation_signal(doc)
    base["headline_stats"] = ssp_headline_stats(doc, impl_reqs)
    base["components"] = ssp_components(doc)
    base["users"] = ssp_users(doc)
    base["requirements_by_family"] = ssp_implemented_requirements_by_family(impl_reqs)
    base["back_matter"] = ssp_back_matter(doc)
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


class OscalWorkbenchPanelType:
    """Panel type for the OSCAL SSP workbench."""

    slug: ClassVar[str] = "roscale-oscal-workbench"
    label: ClassVar[str] = "OSCAL SSP Workbench"
    view: ClassVar[str] = "roscale/panels/oscal_workbench.html"
    css: ClassVar[list[str]] = ["roscale/css/workbench.css"]
    js: ClassVar[list[str]] = []
    config_defaults: ClassVar[dict[str, Any]] = {
        "entity_id_var": DEFAULT_VAR_NAME,
    }

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        return build_context(panel, request)
