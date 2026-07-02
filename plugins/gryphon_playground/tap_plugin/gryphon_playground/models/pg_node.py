"""PgNode — generic playground node for Gryphon query-pattern testing."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel

# Identical across the four pg_* models so the predicate surface is uniform
# regardless of which playground type a scenario targets.
_FIELD_CRUD_SCHEMA: dict[str, Any] = {
    "name": {"type": "string", "minLength": 1},
    "description": {"type": "string"},
    "kind": {"type": "string"},
    "severity_score": {"type": "integer"},
    "is_open": {"type": "boolean"},
    "observed_at": {"type": ["string", "null"], "format": "date-time"},
    "tags": {"type": "object"},
}


class PgNode(BaseModel):
    """Generic playground node — the default building block for Gridkin fixtures.

    Carries the playground typed-field set (string / int / bool / datetime / JSON)
    so scenarios can exercise every scalar predicate type the executor supports.
    Declares no edge constraints — fixtures must be free to build any topology.
    See plugins/gryphon_playground/specs/spec-gryphon-playground-v0.md.
    """

    ENTITY_TYPE: ClassVar[str] = "gryphon_playground__pg_node"
    ENTITY_NAME: ClassVar[str] = "Playground Node"
    ENTITY_DESCRIPTION: ClassVar[str] = "Generic playground node for Gryphon query-pattern testing."
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.playground": "gridkin"}

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = _FIELD_CRUD_SCHEMA
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]
    REPLACE_REQUIRED: ClassVar[list[str]] = ["name"]
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {"tap_viz": {"shape": "ellipse"}}

    # No OUTBOUND_EDGES / INBOUND_EDGES — playground nodes are unconstrained so
    # fixtures can construct any graph shape (cycles, self-loops, multi-edges).

    name = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    kind = models.CharField(max_length=255, blank=True, default="", db_index=True)
    severity_score = models.IntegerField(default=0, db_index=True)
    is_open = models.BooleanField(default=False)
    observed_at = models.DateTimeField(null=True, blank=True)
    tags = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "gryphon_playground__pg_node"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
