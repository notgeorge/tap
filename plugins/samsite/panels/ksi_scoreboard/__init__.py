"""Samsite KSI Scoreboard — `samsite-ksi-scoreboard`.

Joins the on-grid FedRAMP 20x KSI catalog (ksi_indicator + ksi_theme) against
the latest OSCAL SSP and POA&M (compliance_artifact nodes) and renders a
themed grid of indicator status (passing / in-progress / accepted / gap).

This is a Samsite-specific synthesis — it computes a roll-up that neither
the upstream KSI signal nor the SSP carry as a primitive. The math lives in
`plugins.samsite.scoring`; this panel is just resolution + presentation.

Spec: plugins/samsite/specs/spec-samsite-ksi-scoreboard-v0.md (to land).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from plugins.roscale.panels._common import (
    _lookup_by_entity_id,
    _lookup_latest_by_kind,
    build_provenance,
    parse,
    pretty_json,
)
from plugins.samsite.scoring import (
    INDICATOR_ACCEPTED,
    INDICATOR_GAP,
    INDICATOR_IN_PROGRESS,
    INDICATOR_PASSING,
    group_by_theme,
    score,
)

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel


logger = logging.getLogger(__name__)

DEFAULT_SSP_VAR = "oscal_ssp_artifact_entity_id"
DEFAULT_POAM_VAR = "oscal_poam_artifact_entity_id"


def _resolve_one(
    *,
    var_name: str,
    request: Any,
    fallback_kind: str | None,
) -> tuple[dict | None, bool, str | None]:
    """Return (artifact_node, used_fallback, error)."""
    entity_id = (request.GET.get(var_name) or "").strip()
    if entity_id:
        try:
            node = _lookup_by_entity_id(entity_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[scb1] artifact lookup failed for %s", entity_id)
            return None, False, f"Artifact lookup failed: {exc}"
        if node is None:
            return None, False, f"No compliance_artifact with entity_id '{entity_id}'."
        return node, False, None

    if fallback_kind:
        try:
            node = _lookup_latest_by_kind(fallback_kind)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[scb2] artifact fallback lookup failed for kind=%s", fallback_kind)
            return None, True, f"Artifact fallback lookup failed: {exc}"
        if node is None:
            return None, True, f"No compliance_artifact of kind '{fallback_kind}' yet."
        return node, True, None

    return None, False, f"No artifact specified. Expected '{var_name}' in the URL."


def _load_indicators() -> list[dict]:
    """Return all ksi_indicator node bodies via a single Gryphon query."""
    from tap_grid.models import Search
    from tap_grid.search import execute_search

    search = Search(
        search_type="gryphon",
        root="node",
        name="samsite-ksi-scoreboard-indicators",
        input_schema={"type": "object", "properties": {}, "required": []},
        definition={"query": ["MATCH (i:ksi_indicator)"]},
        default_limit=500,
        max_limit=2000,
    )
    result = execute_search(search, inputs={}, layer="extended")
    envelope = result.get("results", result)
    out: list[dict] = []
    for n in envelope.get("nodes", []) or []:
        data = n.get("data") or {}
        if data:
            out.append(data)
    return out


def _load_themes() -> dict[str, dict]:
    """Return ksi_theme nodes keyed by their `code` (e.g. 'KSI-IAM')."""
    from tap_grid.models import Search
    from tap_grid.search import execute_search

    search = Search(
        search_type="gryphon",
        root="node",
        name="samsite-ksi-scoreboard-themes",
        input_schema={"type": "object", "properties": {}, "required": []},
        definition={"query": ["MATCH (t:ksi_theme)"]},
        default_limit=100,
        max_limit=500,
    )
    result = execute_search(search, inputs={}, layer="extended")
    envelope = result.get("results", result)
    out: dict[str, dict] = {}
    for n in envelope.get("nodes", []) or []:
        data = n.get("data") or {}
        code = data.get("code")
        if code:
            out[code] = data
    return out


def _doc_or_none(node: dict | None) -> dict | None:
    """Extract the parsed OSCAL document from a compliance_artifact node, or None."""
    if not node:
        return None
    data = node.get("data") or {}
    content = data.get("content")
    if not content:
        return None
    parsed = parse(content)
    return parsed.document


# Status display order for the headline strip (left to right).
_STATUS_DISPLAY_ORDER = [
    INDICATOR_PASSING,
    INDICATOR_IN_PROGRESS,
    INDICATOR_ACCEPTED,
    INDICATOR_GAP,
]


def build_context(panel: Any, request: Any) -> dict[str, Any]:
    """Pure function — separated from the classmethod so tests can call it directly."""
    config = getattr(panel, "config", None) or {}
    ssp_var = config.get("ssp_artifact_entity_id_var", DEFAULT_SSP_VAR)
    poam_var = config.get("poam_artifact_entity_id_var", DEFAULT_POAM_VAR)
    fb = config.get("fallback") or {}
    ssp_fallback_kind = fb.get("ssp_kind") if isinstance(fb, dict) else None
    poam_fallback_kind = fb.get("poam_kind") if isinstance(fb, dict) else None

    base: dict[str, Any] = {
        "panel_slug": "samsite-ksi-scoreboard",
        "ssp_var_name": ssp_var,
        "poam_var_name": poam_var,
        "ssp_used_fallback": False,
        "poam_used_fallback": False,
        "ssp_provenance": None,
        "poam_provenance": None,
        "error_phase": None,
        "error_message": None,
        "system_class": None,
        # Pre-built list of {status, count} in display order so the template
        # iterates without needing a custom dict-indexing filter.
        "totals_strip": [{"status": s, "count": 0} for s in _STATUS_DISPLAY_ORDER],
        "excluded_class_mismatch": 0,
        "indicator_count": 0,
        "themed": [],
        "raw_indicator_count": 0,
    }

    ssp_node, ssp_used_fb, ssp_err = _resolve_one(
        var_name=ssp_var, request=request, fallback_kind=ssp_fallback_kind
    )
    poam_node, poam_used_fb, poam_err = _resolve_one(
        var_name=poam_var, request=request, fallback_kind=poam_fallback_kind
    )
    base["ssp_used_fallback"] = ssp_used_fb
    base["poam_used_fallback"] = poam_used_fb

    if ssp_err and poam_err:
        base["error_phase"] = "load"
        base["error_message"] = f"SSP: {ssp_err}  ·  POA&M: {poam_err}"
        return base
    if ssp_err:
        # Hard fail — without the SSP there's no scoring possible.
        base["error_phase"] = "load"
        base["error_message"] = f"SSP not available: {ssp_err}"
        return base
    # POA&M missing is recoverable — we can score against the SSP alone (all
    # controls treated as not-in-POA&M). Continue but flag it.
    poam_warning = poam_err

    if ssp_node:
        base["ssp_provenance"] = build_provenance(ssp_node)
    if poam_node:
        base["poam_provenance"] = build_provenance(poam_node)

    ssp_doc = _doc_or_none(ssp_node)
    poam_doc = _doc_or_none(poam_node)

    try:
        indicators = _load_indicators()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[scb3] indicator load failed")
        base["error_phase"] = "load"
        base["error_message"] = f"KSI indicator lookup failed: {exc}"
        return base

    base["raw_indicator_count"] = len(indicators)
    if not indicators:
        base["error_phase"] = "load"
        base["error_message"] = (
            "No ksi_indicator nodes on the grid. Import the fedramp_20x_ksi "
            "plugin's GRIFT seed first."
        )
        return base

    try:
        themes = _load_themes()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[scb4] theme load failed; proceeding without theme labels")
        themes = {}

    result = score(indicators=indicators, ssp_doc=ssp_doc, poam_doc=poam_doc)
    base["system_class"] = result.system_class
    base["totals_strip"] = [
        {"status": s, "count": result.totals.get(s, 0)} for s in _STATUS_DISPLAY_ORDER
    ]
    base["excluded_class_mismatch"] = result.excluded_class_mismatch
    base["indicator_count"] = len(result.indicators)
    base["poam_warning"] = poam_warning

    themed_groups = group_by_theme(result)
    for g in themed_groups:
        theme_meta = themes.get(g["theme_code"]) or {}
        g["theme_name"] = theme_meta.get("name") or g["theme_code"]
        g["theme_description"] = theme_meta.get("description") or ""
    base["themed"] = themed_groups

    return base


class KsiScoreboardPanelType:
    slug: ClassVar[str] = "samsite-ksi-scoreboard"
    label: ClassVar[str] = "Samsite KSI Scoreboard"
    view: ClassVar[str] = "samsite/panels/ksi_scoreboard.html"
    css: ClassVar[list[str]] = ["samsite/css/panel-ksi-scoreboard.css"]
    js: ClassVar[list[str]] = []
    config_defaults: ClassVar[dict[str, Any]] = {
        "ssp_artifact_entity_id_var": DEFAULT_SSP_VAR,
        "poam_artifact_entity_id_var": DEFAULT_POAM_VAR,
        "fallback": {"ssp_kind": "oscal_ssp", "poam_kind": "oscal_poam"},
    }

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        return build_context(panel, request)
