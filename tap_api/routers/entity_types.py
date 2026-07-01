"""EntityType endpoint — read-only. Types are managed by plugins, not the API."""

from django.http import HttpRequest
from ninja import Router

from tap_api.schemas import EntityTypeOut
from tap_auth import policy
from tap_grid.caller_context import CallerContext
from tap_grid.models import EntityType

router = Router()


def _caller_ctx(request: HttpRequest) -> CallerContext:
    """Build a CallerContext from the current HTTP request."""
    user = request.user if hasattr(request.user, "pk") and request.user.pk else None
    return CallerContext(user=user, batch_id=None)


@router.get("/", response=list[EntityTypeOut])
def list_entity_types(request: HttpRequest) -> list[EntityType]:
    # Grid.read gate (finding cs-tap-api-typecat-003): the type catalog is graph
    # metadata, and every graph read requires grid.read (req-tap-auth-policy). This
    # mirrors the entities router. EntityType is not a BaseModel, so this explicit
    # gate — plus the Layer-2 SQL read backstop — is what covers it.
    policy.authorize(_caller_ctx(request), "grid.read", operation="list_entity_types")
    return list(EntityType.objects.all())
