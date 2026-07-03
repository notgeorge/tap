"""Location model — a place in Middle-earth."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel

_NAME_SCHEMA: dict[str, Any] = {"type": "string", "minLength": 1}


class Location(BaseModel):
    """A place in Middle-earth (Shire, Mordor, Rivendell, etc.)."""

    ENTITY_TYPE: ClassVar[str] = "lotr__location"
    ENTITY_NAME: ClassVar[str] = "Location"
    ENTITY_DESCRIPTION: ClassVar[str] = "A place in Middle-earth."
    ENTITY_ICON: ClassVar[str] = "lotr__location"

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": _NAME_SCHEMA,
        "description": {"type": "string"},
        "realm": {"type": "string"},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]
    REPLACE_REQUIRED: ClassVar[list[str]] = ["name", "description", "lotr__realm"]
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "round-rectangle",
            "nesting": {
                "parent": [
                    {
                        "name": "location-contains-location",
                        "description": "A location may visually contain a child location.",
                        "gryphon": "(parent:lotr__location)-[:CONTAINS__lotr]->(child:lotr__location)",
                    },
                    {
                        "name": "location-contains-character",
                        "description": "A location visually contains characters located there.",
                        "gryphon": "(parent:lotr__location)<-[:LOCATED_IN__lotr]-(child:lotr__character)",
                    },
                ],
                "child": [
                    {
                        "name": "location-inside-realm",
                        "description": "A location may be visually nested inside a containing realm.",
                        "gryphon": "(parent:lotr__realm)-[:CONTAINS__lotr]->(child:lotr__location)",
                    },
                    {
                        "name": "location-inside-location",
                        "description": "A location may be visually nested inside a parent location.",
                        "gryphon": "(parent:lotr__location)-[:CONTAINS__lotr]->(child:lotr__location)",
                    },
                ],
                "parent_label": {
                    "horizontal_alignment": "center",
                    "vertical_alignment": "top",
                    "inside_or_outside": "outside",
                },
            },
        }
    }

    OUTBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {"nodes": [{"type": "lotr__location"}], "edges": [{"type": "CONTAINS__lotr"}]},
    ]

    INBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {"nodes": [{"type": "lotr__character"}], "edges": [{"type": "LOCATED_IN__lotr"}, {"type": "RULES__lotr"}]},
        {"nodes": [{"type": "lotr__artifact"}], "edges": [{"type": "FORGED_IN__lotr"}]},
        {"nodes": [{"type": "lotr__location"}, {"type": "lotr__realm"}], "edges": [{"type": "CONTAINS__lotr"}]},
        {"nodes": [{"type": "lotr__citadel"}], "edges": [{"type": "PROTECTS__lotr"}]},
    ]

    name = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    realm = models.CharField(max_length=255, blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr__location"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
