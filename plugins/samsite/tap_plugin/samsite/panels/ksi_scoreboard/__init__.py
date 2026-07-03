"""Samsite KSI Scoreboard — `samsite-ksi-scoreboard`.

Joins the on-grid FedRAMP 20x KSI catalog (ksi_indicator + ksi_theme) against
the latest OSCAL SSP and POA&M (compliance_artifact nodes) and renders a
themed grid of indicator status (passing / in-progress / accepted / gap).

This is a Samsite-specific synthesis — it computes a roll-up that neither
the upstream KSI signal nor the SSP carry as a primitive. The math lives in
`tap_plugin.samsite.scoring`; this panel is just resolution + presentation.

Resolution uses the canonical multi-entity surface at
`tap_web.panels.entity_resolution` with roles `ssp` and `poam`; the panel
config carries `<role>_entity_id_var` keys at the top and a `fallback`
block with per-role `{query, description}` sub-blocks.

Spec: plugins/samsite/specs/spec-samsite-ksi-scoreboard-v0.md
Resolution contract: tap_web/specs/spec-web-panel-entity-resolution-v0.md
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from tap_plugin.roscale.panels._common import build_provenance, parse
from tap_plugin.samsite.scoring import (
    INDICATOR_ACCEPTED,
    INDICATOR_GAP,
    INDICATOR_IN_PROGRESS,
    INDICATOR_PASSING,
    group_by_theme,
    score,
)
from tap_web.panels.entity_resolution import resolve_entity

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel


logger = logging.getLogger(__name__)

DEFAULT_SSP_VAR = "oscal_ssp_artifact_entity_id"
DEFAULT_POAM_VAR = "oscal_poam_artifact_entity_id"

_SSP_FALLBACK_QUERY = (
    "MATCH (a:fedramp_20x_ksi__compliance_artifact) "
    'WHERE a.data.kind = "oscal_ssp" AND a.data.fetched_at IS NOT NULL '
    "ORDER BY a.data.fetched_at DESC LIMIT 1"
)
_SSP_FALLBACK_DESCRIPTION = "Latest oscal_ssp compliance artifact by fetched_at."

_POAM_FALLBACK_QUERY = (
    "MATCH (a:fedramp_20x_ksi__compliance_artifact) "
    'WHERE a.data.kind = "oscal_poam" AND a.data.fetched_at IS NOT NULL '
    "ORDER BY a.data.fetched_at DESC LIMIT 1"
)
_POAM_FALLBACK_DESCRIPTION = "Latest oscal_poam compliance artifact by fetched_at."


def _load_indicators() -> list[dict]:
    """Return all ksi_indicator node bodies via a single Gryphon query."""
    from tap_grid.models import Search
    from tap_grid.search import execute_search

    search = Search(
        search_type="gryphon",
        root="node",
        name="samsite-ksi-scoreboard-indicators",
        input_schema={"type": "object", "properties": {}, "required": []},
        definition={"query": ["MATCH (i:fedramp_20x_ksi__ksi_indicator)"]},
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
        definition={"query": ["MATCH (t:fedramp_20x_ksi__ksi_theme)"]},
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
    ssp_res = resolve_entity(panel, request, role="ssp", default_var_name=DEFAULT_SSP_VAR)
    poam_res = resolve_entity(panel, request, role="poam", default_var_name=DEFAULT_POAM_VAR)

    base: dict[str, Any] = {
        "panel_slug": "samsite-ksi-scoreboard",
        "ssp_var_name": ssp_res.var_name,
        "poam_var_name": poam_res.var_name,
        "ssp_used_fallback": ssp_res.used_fallback,
        "poam_used_fallback": poam_res.used_fallback,
        "ssp_fallback_description": ssp_res.fallback_description,
        "poam_fallback_description": poam_res.fallback_description,
        "ssp_fallback_count": ssp_res.fallback_count,
        "poam_fallback_count": poam_res.fallback_count,
        # req-web-panel-entity-resolution-empty-state: hard-stop scoring requires
        # the SSP. Distinguish "no SSP on grid yet" (informational) from
        # "SSP lookup broken" (error). POA&M missing is recoverable either way
        # (handled below via poam_warning).
        "is_empty_state": (not ssp_res.ok) and ssp_res.fallback_count == 0,
        "ssp_provenance": None,
        "poam_provenance": None,
        # Resolved artifact ids — let the template deep-link each control's SSP
        # status / POA&M refs to the exact artifacts the scoreboard scored
        # against (pin via the page's entity_id var + a #control-/#poam- anchor).
        "ssp_entity_id": None,
        "poam_entity_id": None,
        "ssp_var_name_page": DEFAULT_SSP_VAR,
        "poam_var_name_page": DEFAULT_POAM_VAR,
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

    if not ssp_res.ok and not poam_res.ok:
        base["error_phase"] = "load"
        base["error_message"] = f"SSP: {ssp_res.error}  ·  POA&M: {poam_res.error}"
        return base
    if not ssp_res.ok:
        # Hard fail — without the SSP there's no scoring possible.
        base["error_phase"] = "load"
        base["error_message"] = f"SSP not available: {ssp_res.error}"
        return base
    # POA&M missing is recoverable — we can score against the SSP alone (all
    # controls treated as not-in-POA&M). Continue but flag it.
    poam_warning = poam_res.error if not poam_res.ok else None
    ssp_node = ssp_res.node
    poam_node = poam_res.node

    if ssp_node:
        base["ssp_provenance"] = build_provenance(ssp_node)
        base["ssp_entity_id"] = ssp_node.get("entity_id") if isinstance(ssp_node, dict) else None
    if poam_node:
        base["poam_provenance"] = build_provenance(poam_node)
        base["poam_entity_id"] = poam_node.get("entity_id") if isinstance(poam_node, dict) else None

    ssp_doc = _doc_or_none(ssp_node)
    poam_doc = _doc_or_none(poam_node)

    try:
        indicators = _load_indicators()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[c2cf] indicator load failed")
        base["error_phase"] = "load"
        base["error_message"] = f"KSI indicator lookup failed: {exc}"
        return base

    base["raw_indicator_count"] = len(indicators)
    if not indicators:
        base["error_phase"] = "load"
        base["error_message"] = (
            "No ksi_indicator nodes on the grid. Import the fedramp_20x_ksi " "plugin's GRIFT seed first."
        )
        return base

    try:
        themes = _load_themes()
    except Exception:  # noqa: BLE001
        logger.exception("[2e0a] theme load failed; proceeding without theme labels")
        themes = {}

    result = score(indicators=indicators, ssp_doc=ssp_doc, poam_doc=poam_doc)
    base["system_class"] = result.system_class
    base["totals_strip"] = [{"status": s, "count": result.totals.get(s, 0)} for s in _STATUS_DISPLAY_ORDER]
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
        "ssp_entity_id_var": DEFAULT_SSP_VAR,
        "poam_entity_id_var": DEFAULT_POAM_VAR,
        "fallback": {
            "ssp": {
                "query": _SSP_FALLBACK_QUERY,
                "description": _SSP_FALLBACK_DESCRIPTION,
            },
            "poam": {
                "query": _POAM_FALLBACK_QUERY,
                "description": _POAM_FALLBACK_DESCRIPTION,
            },
        },
    }

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        return build_context(panel, request)
