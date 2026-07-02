"""PgCycleNode — playground node for constructing cycles and self-loops."""

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


class PgCycleNode(BaseModel):
    """Playground node for constructing cycles, self-loops, and multi-cycles.

    Identical in fields to PgNode; the cycle semantics are convention carried by
    the `pg_cycle_node` entity_type slug, so a scenario can target the type to
    set up cyclic topologies. The executor does not treat it specially.
    See plugins/grid_fixtures/README.md.
    """

    ENTITY_TYPE: ClassVar[str] = "grid_fixtures__cycle_node"
    ENTITY_NAME: ClassVar[str] = "Playground Cycle Node"
    ENTITY_DESCRIPTION: ClassVar[str] = "Playground node for constructing cycles, self-loops, and multi-cycles."
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
        db_table = "grid_fixtures__cycle_node"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
