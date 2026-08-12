"""EntityType endpoint — read-only. Types are managed by plugins, not the API."""

from django.http import HttpRequest
from ninja import Router

from tap_api.schemas import EntityTypeOut
from tap_auth import policy
from tap_grid.caller_context import require_caller_context
from tap_grid.models import EntityType

router = Router()


@router.get("/", response=list[EntityTypeOut])
def list_entity_types(request: HttpRequest) -> list[EntityType]:
    # Grid.read gate (finding cs-tap-api-typecat-003): the type catalog is graph
    # metadata, and every graph read requires grid.read (req-tap-auth-policy). This
    # mirrors the entities router. EntityType is not a BaseModel, so this explicit
    # gate — plus the Layer-2 SQL read backstop — is what covers it.
    policy.authorize(require_caller_context(), "grid.read", operation="list_entity_types")
    return list(EntityType.objects.all())
