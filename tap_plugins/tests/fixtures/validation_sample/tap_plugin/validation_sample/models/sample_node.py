"""SampleNode — the single unconstrained node type of the validation_sample fixture.

Kept deliberately minimal: one required string field so validate_plugin's `runs`
level can auto-generate a valid create_node payload (from FIELD_CRUD_SCHEMA +
CREATE_REQUIRED) and land a node inside its rollback transaction. Declares no edge
constraints — the fixture's one edge is wildcard-endpoint.
"""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel

_FIELD_CRUD_SCHEMA: dict[str, Any] = {
    "name": {"type": "string", "minLength": 1},
    "description": {"type": "string"},
}


class SampleNode(BaseModel):
    """A generic, unconstrained fixture node for validate_plugin coverage."""

    ENTITY_TYPE: ClassVar[str] = "validation_sample__sample_node"
    ENTITY_NAME: ClassVar[str] = "Sample Node"
    ENTITY_DESCRIPTION: ClassVar[str] = "Minimal fixture node for the validate_plugin test suite."

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = _FIELD_CRUD_SCHEMA
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]
    REPLACE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "validation_sample__sample_node"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
