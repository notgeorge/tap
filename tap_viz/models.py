"""tap_viz models — Viz layout and projection entities."""

from typing import ClassVar

from django.core.exceptions import ValidationError
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

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, dict]] = {
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "definition": {"type": "object"},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

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


_PROJECTION_DEFINITION_SCHEMA: dict = {
    "type": "object",
    "required": ["default_elevation", "elevations"],
    "additionalProperties": True,
    "properties": {
        "node_style": {
            "type": "string",
            "enum": ["default", "icon-badge"],
        },
        "min_zoom": {
            "oneOf": [
                {"type": "string", "enum": ["fit"]},
                {"type": "number", "exclusiveMinimum": 0},
            ],
        },
        "lock_nodes": {"type": "boolean"},
        "default_elevation": {"type": "string", "minLength": 1},
        "elevations": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["name", "zoom", "tap_layouts"],
                "additionalProperties": True,
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "description": {"type": "string"},
                    "zoom": {"type": "number"},
                    "tap_layouts": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "required": ["name", "js_file"],
                            "additionalProperties": True,
                            "properties": {
                                "name": {"type": "string", "minLength": 1},
                                "description": {"type": "string"},
                                "js_file": {"type": "string", "minLength": 1},
                            },
                        },
                    },
                    "double_tap_targets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["entity_type", "target_elevation"],
                            "additionalProperties": False,
                            "properties": {
                                "entity_type": {"type": "string", "minLength": 1},
                                "target_elevation": {"type": "string", "minLength": 1},
                            },
                        },
                    },
                },
            },
        },
    },
}


class Projection(BaseModel):
    """A reusable TAP Viz projection — a coherent multi-elevation visual perspective.

    A projection orchestrates one or more tap layouts across named zoom-driven
    elevations. Graph panels reference a projection via `USES_PROJECTION`. The
    v0 shape is a monolithic `definition` payload containing `default_elevation`
    and an ordered `elevations` array; see `spec-viz-projection.md`.
    """

    ENTITY_TYPE: ClassVar[str] = "projection"

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, dict]] = {
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "definition": {"type": "object"},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name", "definition"]

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, dict]] = {
        "name": {
            "validation": "jsonschema",
            "schema": {"type": "string", "minLength": 1},
        },
        "definition": {
            "validation": "jsonschema",
            "schema": _PROJECTION_DEFINITION_SCHEMA,
        },
    }

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    definition = models.JSONField(
        default=dict,
        blank=True,
        help_text="Monolithic projection definition: default_elevation + ordered elevations.",
    )

    class Meta(BaseModel.Meta):
        db_table = "tap_projection"
        ordering = ["-entity__created_at"]

    def get_name(self) -> str:
        return self.name or ""

    def __str__(self) -> str:
        return self.name

    def validate(self) -> None:
        """Cross-field invariants: unique elevation names/zooms, valid default_elevation."""
        if not isinstance(self.definition, dict):
            return
        elevations = self.definition.get("elevations")
        if not isinstance(elevations, list) or not elevations:
            return

        names: list[str] = []
        zooms: list[float] = []
        for elev in elevations:
            if not isinstance(elev, dict):
                continue
            name = elev.get("name")
            if isinstance(name, str):
                names.append(name)
            zoom = elev.get("zoom")
            if isinstance(zoom, (int, float)):
                zooms.append(float(zoom))

        if len(names) != len(set(names)):
            raise ValidationError(
                {"definition": ["Elevation names must be unique within a projection."]}
            )
        if len(zooms) != len(set(zooms)):
            raise ValidationError(
                {"definition": ["Elevation zoom values must be unique within a projection."]}
            )

        default_elev = self.definition.get("default_elevation")
        if isinstance(default_elev, str) and default_elev not in names:
            raise ValidationError(
                {"definition": [f"default_elevation '{default_elev}' does not match any elevation name."]}
            )
