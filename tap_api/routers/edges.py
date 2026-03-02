"""Edge CRUD (no update in v0). All mutations delegate to tap_grid.services."""

import uuid

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router

from tap_api.schemas import EdgeIn, EdgeOut, ErrorOut
from tap_grid.exceptions import InvalidEdgeError
from tap_grid.models import Edge, Entity
from tap_grid.services import create_edge, delete_edge

router = Router()


@router.get("/", response=list[EdgeOut])
def list_edges(
    request: HttpRequest,
    from_entity_id: uuid.UUID | None = None,
    to_entity_id: uuid.UUID | None = None,
    edge_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Edge]:
    qs = Edge.objects.select_related("entity").all()
    if from_entity_id:
        qs = qs.filter(from_entity_id=from_entity_id)
    if to_entity_id:
        qs = qs.filter(to_entity_id=to_entity_id)
    if edge_type:
        qs = qs.filter(edge_type=edge_type)
    return list(qs[offset : offset + limit])


@router.get("/{edge_id}/", response=EdgeOut)
def get_edge(request: HttpRequest, edge_id: int) -> Edge:
    return get_object_or_404(Edge.objects.select_related("entity"), pk=edge_id)


@router.post("/", response={201: EdgeOut, 400: ErrorOut})
def create_edge_endpoint(request: HttpRequest, payload: EdgeIn) -> tuple[int, Edge | dict[str, str]]:
    from_entity = get_object_or_404(Entity, pk=payload.from_entity_id)
    to_entity = get_object_or_404(Entity, pk=payload.to_entity_id)
    try:
        edge = create_edge(
            from_entity=from_entity,
            to_entity=to_entity,
            edge_type=payload.edge_type,
            properties=payload.properties,
            display_name=payload.display_name,
        )
    except InvalidEdgeError as e:
        return 400, {"detail": str(e)}
    return 201, edge


@router.delete("/{edge_id}/", response={204: None})
def delete_edge_endpoint(request: HttpRequest, edge_id: int) -> tuple[int, None]:
    edge = get_object_or_404(Edge, pk=edge_id)
    delete_edge(edge)
    return 204, None
