"""
Entity model registry — maps entity_type slugs to their concrete ORM model classes.

Populated automatically at class definition time via BaseModel.__init_subclass__.
Used by Entity.resolve() and resolve_entity() to traverse from an Entity row back
to its typed domain object without knowing the type in advance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from django.core.exceptions import ImproperlyConfigured

if TYPE_CHECKING:
    from tap_grid.models import BaseModel, Entity

_ENTITY_MODEL_REGISTRY: dict[str, type] = {}


def register_entity_type(entity_type: str, model_cls: type) -> None:
    """Register a model class for the given entity_type slug.

    Called from BaseModel.__init_subclass__ for every concrete subclass that
    declares ENTITY_TYPE. Raises ImproperlyConfigured if the slug is already
    registered to a different class.
    """
    existing = _ENTITY_MODEL_REGISTRY.get(entity_type)
    if existing is not None and existing is not model_cls:
        raise ImproperlyConfigured(
            f"Entity type '{entity_type}' is already registered to {existing.__name__}. "
            f"Cannot also register {model_cls.__name__}."
        )
    _ENTITY_MODEL_REGISTRY[entity_type] = model_cls


def get_model_class(entity_type: str) -> type:
    """Return the model class registered for the given entity_type slug.

    Raises KeyError with a descriptive message if the type is unknown.
    """
    try:
        return _ENTITY_MODEL_REGISTRY[entity_type]
    except KeyError:
        registered = sorted(_ENTITY_MODEL_REGISTRY.keys())
        raise KeyError(
            f"No model registered for entity type '{entity_type}'. "
            f"Registered types: {registered}"
        ) from None


def resolve_entity(entity_id: UUID) -> "BaseModel":
    """Resolve an entity_id to its concrete typed model instance.

    Performs two DB queries: one to fetch the Entity (to get entity_type),
    one to fetch the concrete domain object. If you already have the Entity
    instance, call entity.resolve() directly to save the first query.
    """
    from tap_grid.models import Entity

    entity: Entity = Entity.objects.get(pk=entity_id)
    return entity.resolve()
