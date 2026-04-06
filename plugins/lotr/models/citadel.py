"""Citadel model — inbound-block edge test case."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel

_NAME_SCHEMA: dict[str, Any] = {"type": "string", "minLength": 1}


class Citadel(BaseModel):
    """A fortified place that accepts no incoming edges (inbound block test)."""

    ENTITY_TYPE: ClassVar[str] = "citadel"
    ENTITY_NAME: ClassVar[str] = "Citadel"
    ENTITY_DESCRIPTION: ClassVar[str] = "A fortified place (inbound block test)."

    FIELD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": _NAME_SCHEMA,
        "fortification": {"type": "string"},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]
    REPLACE_REQUIRED: ClassVar[list[str]] = ["name", "fortification"]
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {"tap_viz": {"shape": "rectangle"}}

    OUTBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {"nodes": [{"type": "location"}], "edges": [{"type": "PROTECTS"}]},
    ]

    # Empty list = block ALL inbound edges
    INBOUND_EDGES: ClassVar[list[dict[str, Any]]] = []

    name = models.CharField(max_length=255, blank=True, default="")
    fortification = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr_citadel"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
