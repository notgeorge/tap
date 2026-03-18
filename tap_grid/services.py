"""
TAP Core Services — canonical mutation API for entities and edges.

All application code that creates, updates, or deletes domain data should
go through these functions. When FLIP is built, provenance recording
slots in here without changing call sites.
"""

from typing import Any

from tap_grid.constraints import validate_edge
from tap_grid.exceptions import InvalidEdgeError
from tap_grid.models import Edge, Entity


def create_entity(
    entity_type: str,
    name: str = "",
    **kwargs: Any,
) -> Entity:
    """Create a new Entity."""
    return Entity.objects.create(
        entity_type=entity_type,
        name=name,
        **kwargs,
    )


def update_entity(entity: Entity, **kwargs: Any) -> Entity:
    """Update an existing Entity's fields."""
    for field, value in kwargs.items():
        setattr(entity, field, value)
    entity.save(update_fields=list(kwargs.keys()) + ["updated_at"])
    return entity


def delete_entity(entity: Entity) -> None:
    """Delete an Entity. Cascades to edges and domain objects."""
    entity.delete()


def create_edge(
    from_entity: Entity,
    to_entity: Entity,
    edge_type: str,
    properties: dict[str, Any] | None = None,
    name: str = "",
) -> Edge:
    """Create an Edge between two entities.

    The backing Entity for the Edge is auto-created by Edge.save().
    An optional name overrides the auto-generated label on that Entity.

    Raises InvalidEdgeError if either endpoint is itself an edge, or if the
    edge violates topology constraints.
    Raises EdgePropertyValidationError (via Edge.save()) if properties fail
    the registered schema for this edge type.
    """
    # Edges cannot connect to other edges (req-grid-edge-nono)
    if from_entity.entity_type == "edge":
        raise InvalidEdgeError("Edges cannot have other edges as endpoints (from_entity is an edge).")
    if to_entity.entity_type == "edge":
        raise InvalidEdgeError("Edges cannot have other edges as endpoints (to_entity is an edge).")

    validate_edge(from_entity.entity_type, to_entity.entity_type, edge_type)

    edge = Edge.objects.create(
        from_entity=from_entity,
        to_entity=to_entity,
        edge_type=edge_type,
        properties=properties or {},
    )

    if name:
        edge.entity.name = name
        edge.entity.save(update_fields=["name", "updated_at"])

    return edge


def update_edge_properties(edge: Edge, properties: dict[str, Any]) -> Edge:
    """Update an Edge's properties payload.

    Validates the new properties against the registered schema for the edge
    type (via Edge.save()) before persisting. Raises EdgePropertyValidationError
    if the payload is invalid.

    Args:
        edge: The Edge instance to update.
        properties: The new properties dict to assign.

    Returns:
        The updated Edge instance.
    """
    edge.properties = properties
    edge.save(update_fields=["properties"])
    return edge


def delete_edge(edge: Edge) -> None:
    """Delete an Edge and its backing Entity."""
    # Deleting the backing Entity cascades to the Edge via OneToOne,
    # but we go through the Entity to keep the pattern consistent.
    edge.entity.delete()
