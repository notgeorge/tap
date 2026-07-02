"""FLIP Panel — built-in read-only panel for current field-level provenance.

Displays the flip_map of a single canonical target object: which batch last
wrote each tracked field, with batch source, actor, and timing context.

Subject binding (two modes, checked in order):
  1. panel.config["subject_entity_id"] — explicit UUID string in panel config.
  2. request.GET["subject_entity_id"]  — context subject passed as a URL
     parameter; used when placing a FLIP panel on a page without hardcoding
     a specific subject (e.g. the panel tracks the page's current object).

If neither is present the panel renders an empty/no-subject state.

Rendering:
  Server-side only. No editor in v1 (req-web-stdpanel-flip-edit).

Shared helper:
  get_flip_context_for_entity(entity_id) is the canonical lookup function and
  can be imported directly by the viewer shell to power the inspection region
  (req-web-viewer-inspect) without going through the panel system.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel

logger = logging.getLogger(__name__)


def get_flip_context_for_entity(entity_id: str) -> dict[str, Any]:
    """Resolve FLIP provenance rows for a single canonical entity.

    Looks up the entity, finds its model instance, reads flip_map, and
    enriches each entry with the corresponding Batch record.

    Args:
        entity_id: UUID string of the canonical target entity.

    Returns:
        Dict with keys:
          flip_subject  - the Entity, or None if not resolvable
          flip_rows     - list of dicts: field, batch_id, source, actor,
                          started_at, status
          flip_error    - error string or None
    """
    from tap_grid import services
    from tap_grid.exceptions import (
        ServiceConstraintError,
        ServiceNotFoundError,
        ServiceValidationError,
    )

    # Route the spine read through the gated service layer (grid.read) instead of
    # a raw Entity.objects lookup: get_node resolves the entity, its type, and the
    # typed instance in one gated call (req-tap-auth-policy). An authorization
    # denial propagates (fail closed); only genuine "not resolvable" outcomes
    # degrade gracefully so the panel can still render the subject.
    try:
        instance = services.get_node(entity_id)
    except (ServiceNotFoundError, ServiceConstraintError, ServiceValidationError) as exc:
        try:
            flip_subject = services.resolve_entity(entity_id)
        except ServiceNotFoundError, ServiceValidationError:
            return {
                "flip_subject": None,
                "flip_rows": [],
                "flip_error": f"Subject entity {entity_id!r} not found.",
            }
        logger.warning("[7f38] FLIP panel: could not load subject model %s: %s", entity_id, exc)
        return {
            "flip_subject": flip_subject,
            "flip_rows": [],
            "flip_error": f"Could not load subject model: {exc}",
        }

    flip_subject = instance.entity
    flip_map: dict[str, str] = instance.flip_map or {}
    if not flip_map:
        return {"flip_subject": flip_subject, "flip_rows": [], "flip_error": None}

    # Batch-load Batch records to avoid N+1 queries.
    from tap_grid.batch import get_batch

    unique_batch_ids = set(flip_map.values())
    batches: dict[str, Any] = {}
    for bid in unique_batch_ids:
        b = get_batch(bid)
        if b:
            batches[bid] = b

    rows = []
    for field, batch_id in sorted(flip_map.items()):
        batch = batches.get(batch_id)
        rows.append(
            {
                "field": field,
                "batch_id": batch_id,
                "source": batch.source if batch else "",
                "actor": str(batch.actor) if batch and batch.actor else "—",
                "started_at": batch.started_at if batch else None,
                "status": batch.status if batch else "",
            }
        )

    return {"flip_subject": flip_subject, "flip_rows": rows, "flip_error": None}


class FlipPanelType:
    """Built-in FLIP panel type — read-only provenance inspector.

    Implements get_view_context only; no editor_view in v1.
    """

    slug = "flip"
    label = "FLIP Panel"
    view = "tap_web/panels/flip_panel.html"
    editor_view = ""
    config_defaults: dict[str, Any] = {}
    form_class = None

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        """Resolve the subject entity and return FLIP provenance context.

        Subject resolution order:
          1. panel.config["subject_entity_id"] — explicit per-panel binding.
          2. request.GET["subject_entity_id"]  — context subject (e.g. viewer
             page passes the currently-viewed entity to a general-purpose panel).

        Returns the dict produced by get_flip_context_for_entity, or an
        empty-subject state if no subject can be resolved.
        """
        config = panel.config or {}
        subject_id: str = config.get("subject_entity_id") or request.GET.get("subject_entity_id", "")

        if not subject_id:
            return {"flip_subject": None, "flip_rows": [], "flip_error": "No subject configured."}

        return get_flip_context_for_entity(subject_id)
