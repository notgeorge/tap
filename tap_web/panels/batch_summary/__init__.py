"""Batch Summary Panel Type — `batch-summary`.

An embeddable, compact view of ONE batch: its metadata + light counts + a link
to the full batch detail page. Drop it on any page whose URL carries a batch
entity_id (the `entity_id_var`, default `batch_entity_id`), or give it a
`fallback` query to resolve a batch when no id is in the URL.

This is the lightweight counterpart to the `batch-viewer` panel: `batch-viewer`
renders the heavyweight node/edge/delete/purge tables ("what the batch did");
`batch-summary` is the "what is this batch" card. Both share one data source
(`tap_grid.batch.batch_summary`) and this panel renders the shared
`tap_web/partials/batch_card.html` so the representation is identical everywhere.

The detail-page link is generic: the mounting page supplies its route via
`config["detail_page_slug"]` (e.g. an administrivia page sets
"/administrivia/batch"); core ships no plugin route as a default. When unset,
the card renders without a link.

Resolution contract: tap_web/specs/spec-web-panel-entity-resolution-v0.md
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.http import HttpRequest

from tap_grid.batch import batch_summary
from tap_web.models import Panel
from tap_web.panels.entity_resolution import resolve_entity

DEFAULT_VAR_NAME = "batch_entity_id"


def detail_url(slug: str, entity_id: str, var_name: str = DEFAULT_VAR_NAME) -> str:
    """Build a batch detail-page deep link, or "" when no route is configured."""
    if not slug or not entity_id:
        return ""
    return f"{slug}?{var_name}={entity_id}"


def build_context(panel: Any, request: Any) -> dict[str, Any]:
    """Pure function — separated from the classmethod so tests can call it directly."""
    resolution = resolve_entity(panel, request, default_var_name=DEFAULT_VAR_NAME)
    config = getattr(panel, "config", None) or {}
    base: dict[str, Any] = {
        "panel_slug": "batch-summary",
        "entity_id": resolution.entity_id,
        "var_name": resolution.var_name,
        "used_fallback": resolution.used_fallback,
        "fallback_description": resolution.fallback_description,
        "fallback_count": resolution.fallback_count,
        "error_message": None,
        "card": None,
    }

    if not resolution.ok:
        base["error_message"] = resolution.error
        return base

    summary = batch_summary(resolution.entity_id, with_counts=True)
    if summary is None:
        base["error_message"] = f"Entity {resolution.entity_id} is not a batch."
        return base

    summary["url"] = detail_url(config.get("detail_page_slug", ""), summary["entity_id"], resolution.var_name)
    base["card"] = summary
    return base


class BatchSummaryPanelType:
    """Panel type for the embeddable batch summary card."""

    slug: ClassVar[str] = "batch-summary"
    label: ClassVar[str] = "Batch Summary"
    view: ClassVar[str] = "tap_web/panels/batch_summary.html"
    css: ClassVar[list[str]] = ["tap_web/css/batch-card.css"]
    js: ClassVar[list[str]] = []
    config_defaults: ClassVar[dict[str, Any]] = {"entity_id_var": DEFAULT_VAR_NAME, "detail_page_slug": ""}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        return build_context(panel, request)
