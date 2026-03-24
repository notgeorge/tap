"""Lord of the Rings plugin API — character endpoints."""

from django.http import HttpRequest
from ninja import Router

from tap_api.schemas import EntityOut
from tap_grid.models import Entity

router = Router()


@router.get("/characters/", response=list[EntityOut])
def list_characters(request: HttpRequest) -> list[Entity]:
    """List all entities of type 'character'."""
    return list(Entity.objects.filter(entity_type="character"))
