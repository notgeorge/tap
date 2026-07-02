"""Artifact model — a significant object of power in Middle-earth."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel

_NAME_SCHEMA: dict[str, Any] = {"type": "string", "minLength": 1}


class Artifact(BaseModel):
    """A significant object (The One Ring, Sting, Andúril, etc.)."""

    ENTITY_TYPE: ClassVar[str] = "artifact"
    ENTITY_NAME: ClassVar[str] = "Artifact"
    ENTITY_DESCRIPTION: ClassVar[str] = "A significant object of power."
    ENTITY_ICON: ClassVar[str] = "artifact"

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": _NAME_SCHEMA,
        "power": {"type": "string"},
        "origin": {"type": "string"},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]
    REPLACE_REQUIRED: ClassVar[list[str]] = ["name", "power", "origin"]
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "nesting": {
                "child": [
                    {
                        "name": "artifact-inside-character",
                        "description": "An artifact may be visually nested inside a wielding character.",
                        "gryphon": "(parent:character)-[:WIELDS]->(child:artifact)",
                    }
                ]
            },
        }
    }

    OUTBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {"nodes": [{"type": "location"}], "edges": [{"type": "FORGED_IN"}]},
    ]

    INBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {"nodes": [{"type": "character"}], "edges": [{"type": "WIELDS"}]},
    ]

    name = models.CharField(max_length=255, blank=True, default="")
    power = models.TextField(blank=True, default="")
    origin = models.CharField(max_length=255, blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr_artifact"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
