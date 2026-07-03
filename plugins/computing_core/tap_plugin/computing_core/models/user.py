"""User — a human who interacts with computing systems."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class User(BaseModel):
    """A human actor in the graph.

    The User node is the generic person primitive: the human operating,
    owning, or otherwise related to the computing systems TAP models.
    Roles such as "admin" are expressed as assigned relationships rather
    than as distinct node types, so a single durable User type can carry
    any edge in or out.

    Spec: plugins/computing_core/specs/spec-computing-core-v0.md
    """

    ENTITY_TYPE: ClassVar[str] = "computing_core__user"
    ENTITY_NAME: ClassVar[str] = "User"
    ENTITY_DESCRIPTION: ClassVar[str] = "A human who interacts with computing systems."
    ENTITY_ICON: ClassVar[str] = "user"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.computing": "identity"}
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "ellipse",
            "colors": {"fill": "#B26B8E", "border": "#5C2B45", "label": "#FFFFFF"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "description": {"validation": "jsonschema", "schema": {"type": "string"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="", db_index=True)
    description = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "computing_core__user"

    def get_name(self) -> str:
        return self.name or ""

    def __str__(self) -> str:
        return self.get_name()
