"""Samsite VDR Ingestion Health — `samsite-vdr-ingestion-health`.

Consumer-side complement to the upstream VDR aggregator's disclose-shortcut
flags (`summary.kev_catalog_loaded` and `summary.dependabot_alerts_loaded`,
added in samsite repo commit 436ff9f). Reads the most-recently-emitted
on-grid `vdr_report` and renders two ✓/✗ pills so a glance at the compliance
landing tells you whether the latest deploy actually evaluated against the
CISA KEV catalog and Dependabot alerts — or whether either ingestion silently
regressed.

If the producer's disclosure flag is False, we DON'T silently let the user
infer "no findings" from absence; the pill flips red and the panel says so.

Spec: plugins/samsite/specs/spec-samsite-vdr-ingestion-health-v0.md (to land).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel


logger = logging.getLogger(__name__)


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


def _load_latest_vdr_report() -> dict | None:
    """Fetch the most-recently-emitted vdr_report node via Gryphon."""
    from tap_grid.models import Search
    from tap_grid.search import execute_search

    search = Search(
        search_type="gryphon",
        root="node",
        name="samsite-vdr-ingestion-health-latest",
        input_schema={"type": "object", "properties": {}, "required": []},
        definition={"query": ["MATCH (r:vdr_report)"]},
        default_limit=500,
        max_limit=2000,
    )
    result = execute_search(search, inputs={}, layer="extended")
    envelope = result.get("results", result)
    nodes = envelope.get("nodes", []) or []
    if not nodes:
        return None
    nodes_sorted = sorted(
        nodes,
        key=lambda n: (n.get("data") or {}).get("emitted_at") or "",
        reverse=True,
    )
    return nodes_sorted[0]


def build_context(panel: Any, request: Any) -> dict[str, Any]:
    """Pure function — build the panel context. Easy to test offline."""
    base: dict[str, Any] = {
        "panel_slug": "samsite-vdr-ingestion-health",
        "error_message": None,
        "report_emitted_at": None,
        "report_entity_id": None,
        "flags": [],
        "any_false": False,
    }

    try:
        node = _load_latest_vdr_report()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[vdrhealth] vdr_report lookup failed")
        base["error_message"] = f"Could not load latest vdr_report: {exc}"
        return base

    if node is None:
        base["error_message"] = (
            "No vdr_report on the grid yet. The samsite compliance collector "
            "lands one per nightly run."
        )
        return base

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
    config_defaults: ClassVar[dict[str, Any]] = {}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        return build_context(panel, request)
