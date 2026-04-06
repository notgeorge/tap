"""Location model — a place in Middle-earth."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel

_NAME_SCHEMA: dict[str, Any] = {"type": "string", "minLength": 1}


class Location(BaseModel):
    """A place in Middle-earth (Shire, Mordor, Rivendell, etc.)."""

    ENTITY_TYPE: ClassVar[str] = "location"
    ENTITY_NAME: ClassVar[str] = "Location"
    ENTITY_DESCRIPTION: ClassVar[str] = "A place in Middle-earth."
    ENTITY_ICON: ClassVar[str] = "location"

    FIELD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": _NAME_SCHEMA,
        "description": {"type": "string"},
        "realm": {"type": "string"},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]
    REPLACE_REQUIRED: ClassVar[list[str]] = ["name", "description", "realm"]
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {"tap_viz": {"shape": "round-rectangle"}}

    OUTBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {"nodes": [{"type": "location"}], "edges": [{"type": "CONTAINS"}]},
    ]

    INBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {"nodes": [{"type": "character"}], "edges": [{"type": "LOCATED_IN"}, {"type": "RULES"}]},
        {"nodes": [{"type": "artifact"}], "edges": [{"type": "FORGED_IN"}]},
        {"nodes": [{"type": "location"}], "edges": [{"type": "CONTAINS"}]},
        {"nodes": [{"type": "citadel"}], "edges": [{"type": "PROTECTS"}]},
    ]

    name = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    realm = models.CharField(max_length=255, blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr_location"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
