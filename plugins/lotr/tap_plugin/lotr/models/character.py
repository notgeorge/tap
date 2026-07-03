"""Character model — a being in Middle-earth."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel

_NAME_SCHEMA: dict[str, Any] = {"type": "string", "minLength": 1}


class Character(BaseModel):
    """A being in Middle-earth (Frodo, Gandalf, Sauron, etc.)."""

    ENTITY_TYPE: ClassVar[str] = "lotr__character"
    ENTITY_NAME: ClassVar[str] = "Character"
    ENTITY_DESCRIPTION: ClassVar[str] = "A being in Middle-earth."
    ENTITY_ICON: ClassVar[str] = "character"

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": _NAME_SCHEMA,
        "bio": {"type": "string"},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]
    REPLACE_REQUIRED: ClassVar[list[str]] = ["name", "bio"]
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "round-rectangle",
            "nesting": {
                "parent": [
                    {
                        "name": "character-wields-artifact",
                        "description": "A character visually contains artifacts they wield.",
                        "gryphon": "(parent:lotr__character)-[:WIELDS__lotr]->(child:lotr__artifact)",
                    }
                ],
                "child": [
                    {
                        "name": "character-inside-location",
                        "description": "A character may be visually nested inside its location.",
                        "gryphon": "(parent:lotr__location)<-[:LOCATED_IN__lotr]-(child:lotr__character)",
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

    OUTBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {"nodes": [{"type": "lotr__artifact"}], "edges": [{"type": "WIELDS__lotr"}]},
        {"nodes": [{"type": "lotr__location"}], "edges": [{"type": "LOCATED_IN__lotr"}, {"type": "RULES__lotr"}]},
        {"nodes": [{"type": "lotr__race"}], "edges": [{"type": "BELONGS_TO__lotr"}]},
        {"nodes": [{"type": "lotr__faction"}], "edges": [{"type": "MEMBER_OF__lotr"}]},
        {"nodes": [{"type": "lotr__character"}], "edges": [{"type": "ALLIES_WITH__lotr"}, {"type": "ENEMIES_WITH__lotr"}]},
    ]

    INBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {"nodes": [{"type": "lotr__character"}], "edges": [{"type": "ALLIES_WITH__lotr"}, {"type": "ENEMIES_WITH__lotr"}]},
    ]

    name = models.CharField(max_length=255, blank=True, default="")
    bio = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr__character"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
