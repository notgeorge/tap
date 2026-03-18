"""Entity CRUD. All mutations delegate to tap_grid.services."""

import uuid
from typing import Any

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router

from tap_api.schemas import EntityIn, EntityOut, EntityUpdate
from tap_grid.models import Entity
from tap_grid.services import create_entity, delete_entity, update_entity

router = Router()


@router.get("/", response=list[EntityOut])
def list_entities(
    request: HttpRequest,
    entity_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Entity]:
    qs = Entity.objects.all()
    if entity_type:
        qs = qs.filter(entity_type=entity_type)
    return list(qs[offset : offset + limit])


@router.get("/{entity_id}/", response=EntityOut)
def get_entity(request: HttpRequest, entity_id: uuid.UUID) -> Entity:
    return get_object_or_404(Entity, pk=entity_id)


@router.post("/", response={201: EntityOut})
def create_entity_endpoint(request: HttpRequest, payload: EntityIn) -> tuple[int, Entity]:
    entity = create_entity(entity_type=payload.entity_type, name=payload.name)
    return 201, entity


@router.patch("/{entity_id}/", response=EntityOut)
def update_entity_endpoint(request: HttpRequest, entity_id: uuid.UUID, payload: EntityUpdate) -> Entity:
    entity = get_object_or_404(Entity, pk=entity_id)
    updates: dict[str, Any] = payload.dict(exclude_unset=True)
    if updates:
        entity = update_entity(entity, **updates)
    return entity


@router.delete("/{entity_id}/", response={204: None})
def delete_entity_endpoint(request: HttpRequest, entity_id: uuid.UUID) -> tuple[int, None]:
    entity = get_object_or_404(Entity, pk=entity_id)
    delete_entity(entity)
    return 204, None
