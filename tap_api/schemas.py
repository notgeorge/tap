"""TAP API schemas — ModelSchema outputs (stay in sync with models), hand-written inputs."""

import uuid
from typing import Any

from ninja import ModelSchema, Schema

from tap_grid.models import Edge, Entity, EntityType

# --- Common ---


class ErrorOut(Schema):
    """Error response."""

    detail: str


# --- Entity ---


class EntityIn(Schema):
    """Create an entity."""

    entity_type: str
    name: str = ""


class EntityUpdate(Schema):
    """Partial update. All fields optional."""

    name: str | None = None
    entity_type: str | None = None


class EntityOut(ModelSchema):
    class Meta:
        model = Entity
        fields = ["id", "entity_type", "name", "originating_grid_id", "created_at", "updated_at"]


# --- Edge ---


class EdgeIn(Schema):
    """Create an edge."""

    from_entity_id: uuid.UUID
    to_entity_id: uuid.UUID
    edge_type: str
    name: str = ""
    properties: dict[str, Any] = {}


class EdgeOut(ModelSchema):
    entity_id: uuid.UUID

    class Meta:
        model = Edge
        fields = ["id", "from_entity", "to_entity", "edge_type", "properties"]


# --- EntityType ---


class EntityTypeOut(ModelSchema):
    class Meta:
        model = EntityType
        fields = ["id", "slug", "name", "icon", "description", "plugin_name"]
