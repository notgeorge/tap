"""Wanderer model — unconstrained entity test case."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel

_NAME_SCHEMA: dict[str, Any] = {"type": "string", "minLength": 1}


class Wanderer(BaseModel):
    """An unconstrained entity for testing (no OUTBOUND_EDGES or INBOUND_EDGES).

    Since neither constraint is defined, a Wanderer can form or receive
    any edge type to/from any node type.
    """

    ENTITY_TYPE: ClassVar[str] = "wanderer"
    ENTITY_NAME: ClassVar[str] = "Wanderer"
    ENTITY_DESCRIPTION: ClassVar[str] = "An unconstrained traveler."

    FIELD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": _NAME_SCHEMA,
        "journey": {"type": "string"},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]
    REPLACE_REQUIRED: ClassVar[list[str]] = ["name", "journey"]
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {"tap_viz": {"shape": "rectangle"}}

    # No OUTBOUND_EDGES defined = no restrictions
    # No INBOUND_EDGES defined = no restrictions

    name = models.CharField(max_length=255, blank=True, default="")
    journey = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr_wanderer"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
