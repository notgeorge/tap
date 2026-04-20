"""Character model — a being in Middle-earth."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel

_NAME_SCHEMA: dict[str, Any] = {"type": "string", "minLength": 1}


class Character(BaseModel):
    """A being in Middle-earth (Frodo, Gandalf, Sauron, etc.)."""

    ENTITY_TYPE: ClassVar[str] = "character"
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
                        "gryphon": "(parent:character)-[:WIELDS]->(child:artifact)",
                    }
                ],
                "child": [
                    {
                        "name": "character-inside-location",
                        "description": "A character may be visually nested inside its location.",
                        "gryphon": "(parent:location)<-[:LOCATED_IN]-(child:character)",
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
        {"nodes": [{"type": "artifact"}], "edges": [{"type": "WIELDS"}]},
        {"nodes": [{"type": "location"}], "edges": [{"type": "LOCATED_IN"}, {"type": "RULES"}]},
        {"nodes": [{"type": "race"}], "edges": [{"type": "BELONGS_TO"}]},
        {"nodes": [{"type": "faction"}], "edges": [{"type": "MEMBER_OF"}]},
        {"nodes": [{"type": "character"}], "edges": [{"type": "ALLIES_WITH"}, {"type": "ENEMIES_WITH"}]},
    ]

    INBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {"nodes": [{"type": "character"}], "edges": [{"type": "ALLIES_WITH"}, {"type": "ENEMIES_WITH"}]},
    ]

    name = models.CharField(max_length=255, blank=True, default="")
    bio = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr_character"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
