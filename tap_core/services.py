"""
TAP Core Services — canonical mutation API for entities and edges.

All application code that creates, updates, or deletes domain data should
go through these functions. When FLIP is built, provenance recording
slots in here without changing call sites.
"""

from typing import Any

from tap_core.models import Edge, Entity


def create_entity(
    entity_type: str,
    display_name: str = "",
    **kwargs: Any,
) -> Entity:
    """Create a new Entity."""
    return Entity.objects.create(
        entity_type=entity_type,
        display_name=display_name,
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
    display_name: str = "",
) -> Edge:
    """Create an Edge with its backing Entity auto-created.

    Callers don't need to manually create the Entity for the edge —
    this function handles it.
    """
    # Edge inherits BaseModel, which requires a OneToOne to Entity.
    # We auto-create that backing Entity here.
    edge_entity = Entity.objects.create(
        entity_type="edge",
        display_name=display_name or f"{from_entity.id} --[{edge_type}]--> {to_entity.id}",
    )
    return Edge.objects.create(
        entity=edge_entity,
        from_entity=from_entity,
        to_entity=to_entity,
        edge_type=edge_type,
        properties=properties or {},
    )


def delete_edge(edge: Edge) -> None:
    """Delete an Edge and its backing Entity."""
    # Deleting the backing Entity cascades to the Edge via OneToOne,
    # but we go through the Entity to keep the pattern consistent.
    edge.entity.delete()
