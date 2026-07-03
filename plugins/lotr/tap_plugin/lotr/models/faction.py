"""Faction model — a group or alliance in Middle-earth."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel

_NAME_SCHEMA: dict[str, Any] = {"type": "string", "minLength": 1}


class Faction(BaseModel):
    """A group or alliance (Fellowship, Mordor, Rohan, etc.)."""

    ENTITY_TYPE: ClassVar[str] = "lotr__faction"
    ENTITY_NAME: ClassVar[str] = "Faction"
    ENTITY_DESCRIPTION: ClassVar[str] = "A group or alliance."

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": _NAME_SCHEMA,
        "purpose": {"type": "string"},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]
    REPLACE_REQUIRED: ClassVar[list[str]] = ["name", "purpose"]
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {"tap_viz": {"shape": "rectangle"}}

    OUTBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {"nodes": [{"type": "lotr__faction"}], "edges": [{"type": "ALLIES_WITH__lotr"}, {"type": "ENEMIES_WITH__lotr"}]},
    ]

    INBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {"nodes": [{"type": "lotr__character"}], "edges": [{"type": "MEMBER_OF__lotr"}]},
        {"nodes": [{"type": "lotr__faction"}], "edges": [{"type": "ALLIES_WITH__lotr"}, {"type": "ENEMIES_WITH__lotr"}]},
    ]

    name = models.CharField(max_length=255, blank=True, default="")
    purpose = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr__faction"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
