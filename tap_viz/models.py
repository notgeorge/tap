"""tap_viz models — Viz layout entities."""

from typing import ClassVar

from django.db import models

from tap_grid.models import BaseModel


class Layout(BaseModel):
    """A reusable TAP viz layout definition.

    Layouts are Entities (via BaseModel). The definition JSONField stores
    the TAP-owned declarative layout payload: inputs, steps, presentation,
    and interactions. Search retrieval is backed by USES_SEARCH edges from
    this layout to Search entities.
    """

    ENTITY_TYPE: ClassVar[str] = "layout"

    SERVICE_SCHEMAS: ClassVar[dict[str, dict]] = {
        "create": {
            "type": "object",
            "required": ["name"],
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "description": {"type": "string"},
                "definition": {"type": "object"},
            },
        },
        "patch": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "description": {"type": "string"},
                "definition": {"type": "object"},
            },
        },
        "replace": {
            "type": "object",
            "required": ["name"],
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "description": {"type": "string"},
                "definition": {"type": "object"},
            },
        },
    }

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    definition = models.JSONField(
        default=dict,
        blank=True,
        help_text="TAP-owned declarative layout payload: inputs, steps, presentation, interactions.",
    )

    class Meta(BaseModel.Meta):
        db_table = "tap_layout"
        ordering = ["-entity__created_at"]

    def __str__(self) -> str:
        return self.name
