"""Edge CRUD (no update in v0). All mutations delegate to tap_grid.services."""

import uuid

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router

from tap_api.schemas import EdgeIn, EdgeOut, ErrorOut
from tap_auth import policy
from tap_grid.caller_context import CallerContext
from tap_grid.exceptions import InvalidEdgeError
from tap_grid.models import Edge, Entity
from tap_grid.services import create_edge, delete_edge

router = Router()


def _caller_ctx(request: HttpRequest) -> CallerContext:
    """Build a CallerContext from the current HTTP request."""
    user = request.user if hasattr(request.user, "pk") and request.user.pk else None
    return CallerContext(user=user, batch_id=None)


@router.get("/", response=list[EdgeOut])
def list_edges(
    request: HttpRequest,
    from_entity_id: uuid.UUID | None = None,
    to_entity_id: uuid.UUID | None = None,
    edge_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Edge]:
    # Direct read bypasses Search; interim grid.read gate (req-tap-auth-policy).
    policy.authorize(_caller_ctx(request), "grid.read", operation="list_edges")
    qs = Edge.objects.select_related("entity").all()
    if from_entity_id:
        qs = qs.filter(from_entity_id=from_entity_id)
    if to_entity_id:
        qs = qs.filter(to_entity_id=to_entity_id)
    if edge_type:
        qs = qs.filter(edge_type=edge_type)
    return list(qs[offset : offset + limit])


@router.get("/{entity_id}/", response=EdgeOut)
def get_edge(request: HttpRequest, entity_id: uuid.UUID) -> Edge:
    policy.authorize(_caller_ctx(request), "grid.read", operation="get_edge")
    return get_object_or_404(Edge.objects.select_related("entity"), entity__pk=entity_id)


@router.post("/", response={201: EdgeOut, 400: ErrorOut})
def create_edge_endpoint(request: HttpRequest, payload: EdgeIn) -> tuple[int, Edge | dict[str, str]]:
    # Authorize before the endpoint lookups (req-tap-auth-policy): grid.write gates
    # up front, closing the 404-before-403 existence oracle on the two endpoint ids
    # (Entity is not covered by the ORM read backstop).
    policy.authorize(_caller_ctx(request), "grid.write", operation="create_edge")
    from_entity = get_object_or_404(Entity, pk=payload.from_entity_id)
    to_entity = get_object_or_404(Entity, pk=payload.to_entity_id)
    try:
        edge = create_edge(
            from_entity=from_entity,
            to_entity=to_entity,
            edge_type=payload.edge_type,
            properties=payload.properties,
            name=payload.name,
            caller_context=_caller_ctx(request),
        )
    except InvalidEdgeError as e:
        return 400, {"detail": str(e)}
    return 201, edge


@router.delete("/{entity_id}/", response={204: None})
def delete_edge_endpoint(request: HttpRequest, entity_id: uuid.UUID) -> tuple[int, None]:
    # Authorize before the lookup (req-tap-auth-policy): grid.delete gates up front.
    policy.authorize(_caller_ctx(request), "grid.delete", operation="delete_edge")
    edge = get_object_or_404(Edge.objects.select_related("entity"), entity__pk=entity_id)
    delete_edge(edge, caller_context=_caller_ctx(request))
    return 204, None
