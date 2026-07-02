"""Wildcard-Referencer Fixture Node — Fixture node whose outbound edge declares an edge type with NO target-type restriction (wildcard target) plus a self-referential inbound (tests wildcard-target constraint entries)."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel

# Uniform scalar field surface across every grid_fixtures node type (see pg_node); the
# constraint types differ from each other ONLY by their edge-constraint declarations.
_FIELD_CRUD_SCHEMA: dict[str, Any] = {
    "name": {"type": "string", "minLength": 1},
    "description": {"type": "string"},
    "kind": {"type": "string"},
    "severity_score": {"type": "integer"},
    "is_open": {"type": "boolean"},
    "observed_at": {"type": ["string", "null"], "format": "date-time"},
    "tags": {"type": "object"},
}


class WildcardReferencer(BaseModel):
    """Wildcard-Referencer Fixture Node for exercising TAP grid edge-constraint behavior.

    See plugins/grid_fixtures/README.md. Fixture node whose outbound edge declares an edge type with NO target-type restriction (wildcard target) plus a self-referential inbound (tests wildcard-target constraint entries).
    """

    ENTITY_TYPE: ClassVar[str] = "grid_fixtures__wildcard_referencer"
    ENTITY_NAME: ClassVar[str] = "Wildcard-Referencer Fixture Node"
    ENTITY_DESCRIPTION: ClassVar[str] = (
        "Fixture node whose outbound edge declares an edge type with NO target-type restriction (wildcard target) plus a self-referential inbound (tests wildcard-target constraint entries)."
    )

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = _FIELD_CRUD_SCHEMA
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]
    REPLACE_REQUIRED: ClassVar[list[str]] = ["name"]
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {"tap_viz": {"shape": "ellipse"}}

    OUTBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [{"edges": [{"type": "WILDCARD_LINK__grid_fixtures"}]}]
    INBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {"nodes": [{"type": "grid_fixtures__wildcard_referencer"}], "edges": [{"type": "WILDCARD_LINK__grid_fixtures"}]}
    ]

    name = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    kind = models.CharField(max_length=255, blank=True, default="", db_index=True)
    severity_score = models.IntegerField(default=0, db_index=True)
    is_open = models.BooleanField(default=False)
    observed_at = models.DateTimeField(null=True, blank=True)
    tags = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "grid_fixtures__wildcard_referencer"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
