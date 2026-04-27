"""Gryphon query execution endpoint for client-side consumers like arrangements."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from ninja import Router, Schema

from tap_grid.exceptions import SearchExecutionError
from tap_grid.grift.subgraph import SubgraphLayer
from tap_grid.gryphon import execute_gryphon_raw

router = Router()


class GryphonQueryIn(Schema):
    query: str
    inputs: dict[str, Any] | None = None
    layer: SubgraphLayer | None = None


@router.post("/execute", response={200: dict, 422: dict, 500: dict}, auth=None)
def execute_gryphon_endpoint(
    request: HttpRequest,
    payload: GryphonQueryIn,
) -> tuple[int, dict[str, Any]]:
    """Execute a raw gryphon query and return the canonical graph envelope.

    Used by the arrangement runtime to resolve anchor and member nodes
    without requiring a stored Search entity.
    """
    try:
        result = execute_gryphon_raw(
            query=payload.query,
            inputs=payload.inputs or {},
            layer=payload.layer or "lite",
        )
    except SearchExecutionError as exc:
        return 422, {"error": "gryphon_execution_failed", "detail": str(exc)}
    return 200, result
