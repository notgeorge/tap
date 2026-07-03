"""Samsite VDR Ingestion Health — `samsite-vdr-ingestion-health`.

Consumer-side complement to the upstream VDR aggregator's disclose-shortcut
flags (`summary.kev_catalog_loaded` and `summary.dependabot_alerts_loaded`,
added in samsite repo commit 436ff9f). Reads the most-recently-emitted
on-grid `vdr_report` and renders two check/cross pills so a glance at the
compliance landing tells you whether the latest deploy actually evaluated
against the CISA KEV catalog and Dependabot alerts — or whether either
ingestion silently regressed.

If the producer's disclosure flag is False, we DON'T silently let the user
infer "no findings" from absence; the pill flips red and the panel says so.

Resolution uses the canonical helper at `tap_web.panels.entity_resolution`:
URL deep link via `entity_id_var`; fallback Gryphon query selects the
latest emission by `emitted_at` (defensively filtered with `IS NOT NULL`).

Spec: plugins/samsite/specs/spec-samsite-vdr-ingestion-health-v0.md
Resolution contract: tap_web/specs/spec-web-panel-entity-resolution-v0.md
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from tap_web.panels.entity_resolution import resolve_entity

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel


logger = logging.getLogger(__name__)


DEFAULT_VAR_NAME = "vdr_report_entity_id"

_FALLBACK_QUERY = (
    "MATCH (r:fedramp_20x_ksi__vdr_report) WHERE r.data.emitted_at IS NOT NULL "
    "ORDER BY r.data.emitted_at DESC LIMIT 1"
)
_FALLBACK_DESCRIPTION = (
    "Latest vdr_report by emitted_at — the most recent VDR aggregator emission on the grid."
)


# Disclosure flag definitions — extend this list when new flags appear on
# vdr_report.summary. Each entry: (summary_key, display_label, help_text).
DISCLOSURE_FLAGS: list[tuple[str, str, str]] = [
    (
        "kev_catalog_loaded",
        "CISA KEV catalog",
        "True = the CISA Known Exploited Vulnerabilities JSON was successfully "
        "loaded at build time. False = the KEV check did not run; is_kev is "
        "unreliable for this report.",
    ),
    (
        "dependabot_alerts_loaded",
        "Dependabot alerts",
        "True = open Dependabot alerts were fetched from the GitHub API and "
        "ingested into findings. False = Dependabot-sourced findings are "
        "absent by omission, not by clean signal.",
    ),
]


def build_context(panel: Any, request: Any) -> dict[str, Any]:
    """Pure function — build the panel context. Easy to test offline."""
    resolution = resolve_entity(panel, request, default_var_name=DEFAULT_VAR_NAME)

    base: dict[str, Any] = {
        "panel_slug": "samsite-vdr-ingestion-health",
        "error_message": None,
        "report_emitted_at": None,
        "report_entity_id": resolution.entity_id,
        "var_name": resolution.var_name,
        "used_fallback": resolution.used_fallback,
        "fallback_description": resolution.fallback_description,
        "fallback_count": resolution.fallback_count,
        # req-web-panel-entity-resolution-empty-state: render the empty-grid
        # case as informational, not as a red error block — a freshly-stood-up
        # environment with no vdr_report yet is expected, not broken.
        "is_empty_state": (not resolution.ok) and resolution.fallback_count == 0,
        "flags": [],
        "any_false": False,
    }

    if not resolution.ok:
        base["error_message"] = resolution.error
        return base

    node = resolution.node
    data = node.get("data") or {}
    summary = data.get("summary") or {}
    base["report_emitted_at"] = data.get("emitted_at") or ""
    base["report_entity_id"] = node.get("entity_id") or ""

    flags = []
    any_false = False
    for key, label, help_text in DISCLOSURE_FLAGS:
        present = key in summary
        loaded = bool(summary.get(key))
        # State: True/loaded → "ok"; False AND present → "missing" (producer
        # explicitly disclosed); not present at all → "unknown" (older report
        # predates the disclosure flag).
        if not present:
            state = "unknown"
        elif loaded:
            state = "ok"
        else:
            state = "missing"
            any_false = True
        flags.append(
            {
                "key": key,
                "label": label,
                "help_text": help_text,
                "state": state,
            }
        )
    base["flags"] = flags
    base["any_false"] = any_false
    return base


class VdrIngestionHealthPanelType:
    slug: ClassVar[str] = "samsite-vdr-ingestion-health"
    label: ClassVar[str] = "Samsite VDR Ingestion Health"
    view: ClassVar[str] = "samsite/panels/vdr_ingestion_health.html"
    css: ClassVar[list[str]] = ["samsite/css/panel-vdr-ingestion-health.css"]
    js: ClassVar[list[str]] = []
    config_defaults: ClassVar[dict[str, Any]] = {
        "entity_id_var": DEFAULT_VAR_NAME,
        "fallback": {
            "query": _FALLBACK_QUERY,
            "description": _FALLBACK_DESCRIPTION,
        },
    }

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        return build_context(panel, request)
