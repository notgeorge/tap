"""Viewer Panel — built-in read-only panel for entity field display.

Displays the fields of a single entity using its registered EditorDescriptor
to discover field names, labels, and current values.

Subject binding (from request query params):
  request.GET["entity_id"]    — UUID of the target entity.
  request.GET["entity_type"]  — entity type slug.

If neither is present the panel renders an empty/no-subject state.

Rendering:
  Server-side only. No editor in v1.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel

logger = logging.getLogger(__name__)


class ViewerPanelType:
    """Built-in viewer panel type — read-only entity field inspector."""

    slug = "viewer"
    label = "Viewer Panel"
    view = "tap_web/panels/viewer_panel.html"
    editor_view = ""
    config_defaults: dict[str, Any] = {}
    form_class = None

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        """Resolve the subject entity and return field display context.

        Subject resolution: reads entity_id and entity_type from request.GET.

        Returns context with viewer_obj, viewer_field_pairs, viewer_entity_type,
        viewer_edit_url, viewer_obj_name, and panel_render_url (for Panel entities).
        """
        entity_id = request.GET.get("entity_id", "")
        entity_type = request.GET.get("entity_type", "")

        if not entity_id or not entity_type:
            return {"viewer_obj": None, "viewer_field_pairs": [], "viewer_error": "No subject configured."}

        return _get_viewer_context(entity_id, entity_type)


def _get_viewer_context(entity_id: str, entity_type: str) -> dict[str, Any]:
    """Build viewer context for a single entity."""
    from tap_grid.registry import get_model_class
    from tap_web.registry import get_editor

    try:
        model_cls = get_model_class(entity_type)
    except KeyError:
        return {"viewer_obj": None, "viewer_field_pairs": [], "viewer_error": f"Unknown entity type '{entity_type}'."}

    try:
        obj = model_cls.objects.select_related("entity").get(entity__pk=entity_id)
    except model_cls.DoesNotExist:
        return {"viewer_obj": None, "viewer_field_pairs": [], "viewer_error": f"Entity '{entity_id}' not found."}

    descriptor = get_editor(entity_type)

    field_pairs: list[tuple[str, Any]] = []
    if descriptor is not None:
        initial = descriptor.get_editor_initial(obj)
        form_class = descriptor.get_form_class(obj)
        if form_class is not None:
            form = form_class(initial=initial)
            for name, field in form.fields.items():
                label = str(field.label or name.replace("_", " ").title())
                value = initial.get(name, "")
                field_pairs.append((label, value))

    extra = descriptor.get_extra_context(obj) if descriptor else {}

    # Build URL ID from object slug + entity_id.
    slug = getattr(obj, "slug", "") or obj.entity.name or ""
    object_url_id = f"{slug}--{entity_id}"
    edit_url = extra.pop("edit_url_override", f"/object/{entity_type}/{object_url_id}/edit/")

    # Panel preview URL for panel entities.
    panel_render_url = ""
    if entity_type == "panel":
        panel_slug = getattr(obj, "slug", "") or ""
        panel_render_url = f"/panel/{panel_slug}--{entity_id}/"

    return {
        "viewer_obj": obj,
        "viewer_obj_name": str(obj),
        "viewer_entity_type": entity_type,
        "viewer_field_pairs": field_pairs,
        "viewer_edit_url": edit_url,
        "viewer_panel_render_url": panel_render_url,
        "viewer_error": None,
        **extra,
    }
