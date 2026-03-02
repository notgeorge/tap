"""EntityType endpoint — read-only. Types are managed by plugins, not the API."""

from django.http import HttpRequest
from ninja import Router

from tap_api.schemas import EntityTypeOut
from tap_grid.models import EntityType

router = Router()


@router.get("/", response=list[EntityTypeOut])
def list_entity_types(request: HttpRequest) -> list[EntityType]:
    return list(EntityType.objects.all())
