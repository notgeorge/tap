"""Core examples plugin API — sample endpoints proving plugin router registration."""

from django.http import HttpRequest
from ninja import Router

from tap_api.schemas import EntityOut
from tap_grid.models import Entity

router = Router()


@router.get("/concepts/", response=list[EntityOut])
def list_concepts(request: HttpRequest) -> list[Entity]:
    """List all entities of type 'concept'."""
    return list(Entity.objects.filter(entity_type="concept"))
