"""Sequence-navigator panel — back/forward across an ordered emission sequence.

A standalone panel mounted *above* a content viewer panel on the same page.
Both panels read the same `entity_id_var` from the URL; this panel resolves
the full ordered sequence (a Gryphon query) and renders prev/next links that
flip that var, plus a position indicator ("3 of 17"). It does not render the
artifact — it only navigates. Composes with any viewer without editing the
content panel (the back/forward control is a sibling, not a modification).

Companion to `tap_web.panels.entity_resolution`: that helper answers *which*
entity is current (latest or deep-linked); this panel answers *where* in the
sequence it sits and *what* the neighbours are. Both key off the same ordering.

Spec: tap_web/specs/spec-web-panel-sequence-navigation-v0.md
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from django.http import HttpRequest

from tap_web.models import Panel
from tap_web.panels.entity_resolution import _run_fallback_query

logger = logging.getLogger(__name__)

# Fields tried, in order, when config does not name a `label_field` — the
# common per-emission timestamps across TAP artifact types.
_DEFAULT_LABEL_FIELDS = ("fetched_at", "emitted_at")


def _node_label(node: dict[str, Any], label_field: str | None) -> str:
    """Human label for one sequence member — a timestamp if available, else name."""
    data = node.get("data") or {}
    if label_field and data.get(label_field) is not None:
        return str(data[label_field])
    for field in _DEFAULT_LABEL_FIELDS:
        if data.get(field) is not None:
            return str(data[field])
    return str(node.get("name") or node.get("entity_id") or "")


class SequenceNavPanelType:
    """Panel type for the back/forward emission selector."""

    slug: ClassVar[str] = "sequence-nav"
    label: ClassVar[str] = "Sequence Navigator"
    view: ClassVar[str] = "tap_web/panels/sequence_nav.html"
    css: ClassVar[list[str]] = ["tap_web/css/sequence-nav.css"]
    js: ClassVar[list[str]] = []
    config_defaults: ClassVar[dict[str, Any]] = {
        "entity_id_var": "entity_id",
        "sequence": {"query": "", "label_field": None, "label": None},
    }

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        config = getattr(panel, "config", None) or {}
        var_name = config.get("entity_id_var", "entity_id")
        seq = config.get("sequence") or {}
        query = (seq.get("query") or "").strip()
        label_field = seq.get("label_field")

        ctx: dict[str, Any] = {
            "seq_var": var_name,
            "seq_label": seq.get("label"),
            "seq_error": None,
            "seq_total": 0,
            "seq_position": None,
            "seq_current_label": None,
            "seq_older_id": None,
            "seq_newer_id": None,
            "seq_latest_id": None,
            "seq_oldest_id": None,
            "seq_is_latest": False,
            "seq_unknown_position": False,
        }

        if not query:
            ctx["seq_error"] = "Sequence navigator misconfigured: `sequence.query` is required."
            return ctx

        try:
            nodes, total = _run_fallback_query(query)
        except Exception as exc:  # noqa: BLE001 — surface, don't crash the page
            logger.exception("[2a5b] sequence query failed: %s", query[:80])
            ctx["seq_error"] = f"Sequence query failed: {exc}"
            return ctx

        ctx["seq_total"] = total
        if total == 0:
            ctx["seq_error"] = "No emissions on the grid yet."
            return ctx

        # Query is newest-first (ORDER BY <ts> DESC): index 0 = latest.
        ids = [str(n.get("entity_id") or "") for n in nodes]
        ctx["seq_latest_id"] = ids[0]
        ctx["seq_oldest_id"] = ids[-1]

        current_id = (request.GET.get(var_name) or "").strip()
        if not current_id:
            idx = 0  # no deep link → the content panel resolved to latest
        else:
            try:
                idx = ids.index(current_id)
            except ValueError:
                # Deep-linked to something outside this sequence (e.g. a
                # different kind). Report total but not a position — never lie.
                ctx["seq_unknown_position"] = True
                return ctx

        ctx["seq_position"] = idx + 1
        ctx["seq_is_latest"] = idx == 0
        ctx["seq_current_label"] = _node_label(nodes[idx], label_field)
        # Newest-first ordering: "older" (back in time) is the next index,
        # "newer" (toward latest) is the previous index.
        if idx + 1 < total:
            ctx["seq_older_id"] = ids[idx + 1]
        if idx - 1 >= 0:
            ctx["seq_newer_id"] = ids[idx - 1]
        return ctx
