"""Race model — a race of beings in Middle-earth."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel

_NAME_SCHEMA: dict[str, Any] = {"type": "string", "minLength": 1}


class Race(BaseModel):
    """A race of beings (Hobbit, Elf, Dwarf, Human, Wizard, etc.)."""

    ENTITY_TYPE: ClassVar[str] = "lotr__race"
    ENTITY_NAME: ClassVar[str] = "Race"
    ENTITY_DESCRIPTION: ClassVar[str] = "A race of beings."
    ENTITY_ICON: ClassVar[str] = "lotr__race"

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": _NAME_SCHEMA,
        "homeland": {"type": "string"},
        "traits": {"type": "string"},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]
    REPLACE_REQUIRED: ClassVar[list[str]] = ["name", "homeland", "traits"]
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {"tap_viz": {"shape": "rectangle"}}

    # Races cannot create any outbound edges (empty list = block all)
    OUTBOUND_EDGES: ClassVar[list[dict[str, Any]]] = []

    INBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {"nodes": [{"type": "lotr__character"}], "edges": [{"type": "BELONGS_TO__lotr"}]},
    ]

    name = models.CharField(max_length=255, blank=True, default="")
    homeland = models.CharField(max_length=255, blank=True, default="")
    traits = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr__race"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
