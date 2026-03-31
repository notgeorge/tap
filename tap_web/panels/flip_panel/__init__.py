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
    from tap_grid.models import Entity

    try:
        entity = Entity.objects.get(pk=entity_id)
    except Entity.DoesNotExist:
        return {
            "flip_subject": None,
            "flip_rows": [],
            "flip_error": f"Subject entity {entity_id!r} not found.",
        }

    try:
        from tap_grid.registry import get_model_class

        model_cls = get_model_class(entity.entity_type)
        instance = model_cls.objects.select_related("entity").get(entity_id=entity_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("FLIP panel: could not load subject %s: %s", entity_id, exc)
        return {
            "flip_subject": entity,
            "flip_rows": [],
            "flip_error": f"Could not load subject model: {exc}",
        }

    flip_map: dict[str, str] = instance.flip_map or {}
    if not flip_map:
        return {"flip_subject": entity, "flip_rows": [], "flip_error": None}

    # Batch-load Batch records to avoid N+1 queries.
    from tap_grid.batch_service import get_batch

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

    return {"flip_subject": entity, "flip_rows": rows, "flip_error": None}


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
