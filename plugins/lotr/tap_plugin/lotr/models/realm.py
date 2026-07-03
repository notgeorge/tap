"""Realm model — a major geographical and political domain in Middle-earth."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel

_NAME_SCHEMA: dict[str, Any] = {"type": "string", "minLength": 1}


class Realm(BaseModel):
    """A major geographical and political domain (Gondor, Rohan, Eriador, etc.)."""

    ENTITY_TYPE: ClassVar[str] = "lotr__realm"
    ENTITY_NAME: ClassVar[str] = "Realm"
    ENTITY_DESCRIPTION: ClassVar[str] = "A major geographical and political domain."
    ENTITY_ICON: ClassVar[str] = ""
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "nesting": {
                "parent": [
                    {
                        "name": "realm-contains-location",
                        "description": "A realm visually contains its locations.",
                        "gryphon": "(parent:lotr__realm)-[:CONTAINS__lotr]->(child:lotr__location)",
                    }
                ],
                "parent_label": {
                    "horizontal_alignment": "center",
                    "vertical_alignment": "top",
                    "inside_or_outside": "outside",
                },
            },
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": _NAME_SCHEMA,
        "description": {"type": "string"},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]
    REPLACE_REQUIRED: ClassVar[list[str]] = ["name", "description"]

    OUTBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {"nodes": [{"type": "lotr__location"}], "edges": [{"type": "CONTAINS__lotr"}]},
    ]

    INBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {"nodes": [{"type": "lotr__location"}], "edges": [{"type": "CONTAINS__lotr"}]},
    ]

    name = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr__realm"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
