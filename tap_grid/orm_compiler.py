"""ORM DSL compiler for TAP search execution — req-grid-search-orm.

Compiles declarative JSON search definitions into read-only TAP ORM queries.
The v1 DSL supports: root selection, conjunctive filters, optional one-hop
graph traversal, and deterministic ordering.

Entry point: compile_orm_query(search, db_alias, limit, offset) -> dict
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tap_grid.exceptions import InvalidSearchDefinitionError

if TYPE_CHECKING:
    from tap_grid.models import Search


def compile_orm_query(
    search: Search,
    db_alias: str,
    limit: int | None = None,
    offset: int = 0,
) -> dict[str, Any]:
    """Compile and execute an ORM DSL search definition.

    Args:
        search:    The Search model instance (search_type must be "orm").
        db_alias:  DB alias to use for all queries (read-only alias in production).
        limit:     Maximum number of primary-side results to return.
        offset:    Zero-based offset into the primary-side results.

    Returns:
        Canonical 4-key envelope: {"nodes": [...], "edges": [...], "info": {...}, "warnings": {}}
        info contains "total_count" (count before pagination).

    Raises:
        InvalidSearchDefinitionError: definition is structurally invalid at execution time.
    """
    definition = search.definition
    filters: dict[str, Any] = definition.get("filters", {})
    hops: list[dict[str, Any]] = definition.get("hops") or []
    order_by: list[str] | None = definition.get("order_by")

    if len(hops) > 1:
        raise InvalidSearchDefinitionError("ORM search supports at most one hop.")

    if search.root == "node":
        return _execute_node_query(db_alias, filters, hops, order_by, limit, offset)
    else:
        return _execute_edge_query(db_alias, filters, hops, order_by, limit, offset)


# ---------------------------------------------------------------------------
# Node root
# ---------------------------------------------------------------------------


def _execute_node_query(
    db_alias: str,
    filters: dict[str, Any],
    hops: list[dict[str, Any]],
    order_by: list[str] | None,
    limit: int | None,
    offset: int,
) -> dict[str, Any]:
    from tap_grid.models import Edge, Entity

    root_qs = Entity.objects.using(db_alias).exclude(entity_type="edge")
    if filters:
        root_qs = root_qs.filter(**filters)
    root_qs = _apply_order(root_qs, order_by, default=["id"])

    total_count = root_qs.count()

    # Apply pagination to root
    if limit is not None:
        paginated_qs = root_qs[offset : offset + limit]
    else:
        paginated_qs = root_qs

    if not hops:
        nodes = [_serialize_entity(e) for e in paginated_qs]
        return {"nodes": nodes, "edges": [], "info": {"total_count": total_count}, "warnings": {}}

    hop = hops[0]
    direction = hop["direction"]
    edge_type = hop["edge_type"]
    root_ids = list(paginated_qs.values_list("id", flat=True))

    if direction == "out":
        hop_edge_qs = Edge.objects.using(db_alias).filter(
            from_entity_id__in=root_ids, edge_type=edge_type
        )
        endpoint_ids = list(hop_edge_qs.values_list("to_entity_id", flat=True))
        endpoint_filters = hop.get("target_filters", {})
    else:  # "in"
        hop_edge_qs = Edge.objects.using(db_alias).filter(
            to_entity_id__in=root_ids, edge_type=edge_type
        )
        endpoint_ids = list(hop_edge_qs.values_list("from_entity_id", flat=True))
        endpoint_filters = hop.get("source_filters", {})

    endpoint_qs = Entity.objects.using(db_alias).filter(id__in=endpoint_ids)
    if endpoint_filters:
        endpoint_qs = endpoint_qs.filter(**endpoint_filters)

    # Keep only edges where the endpoint survived filtering
    surviving_ids = set(endpoint_qs.values_list("id", flat=True))
    if direction == "out":
        hop_edge_qs = hop_edge_qs.filter(to_entity_id__in=surviving_ids)
    else:
        hop_edge_qs = hop_edge_qs.filter(from_entity_id__in=surviving_ids)

    nodes = [_serialize_entity(e) for e in paginated_qs] + [
        _serialize_entity(e) for e in endpoint_qs
    ]
    edges = [_serialize_edge(e) for e in hop_edge_qs]
    return {"nodes": nodes, "edges": edges, "info": {"total_count": total_count}, "warnings": {}}


# ---------------------------------------------------------------------------
# Edge root
# ---------------------------------------------------------------------------


def _execute_edge_query(
    db_alias: str,
    filters: dict[str, Any],
    hops: list[dict[str, Any]],
    order_by: list[str] | None,
    limit: int | None,
    offset: int,
) -> dict[str, Any]:
    from tap_grid.models import Edge, Entity

    edge_qs = Edge.objects.using(db_alias)
    if filters:
        edge_qs = edge_qs.filter(**filters)
    edge_qs = _apply_order(edge_qs, order_by, default=["entity_id"])

    total_count = edge_qs.count()

    if limit is not None:
        paginated_qs = edge_qs[offset : offset + limit]
    else:
        paginated_qs = edge_qs

    if not hops:
        edges = [_serialize_edge(e) for e in paginated_qs]
        return {"nodes": [], "edges": edges, "info": {"total_count": total_count}, "warnings": {}}

    hop = hops[0]
    direction = hop["direction"]
    edges_list = list(paginated_qs)

    if direction == "out":
        endpoint_ids = [e.to_entity_id for e in edges_list]
        endpoint_filters = hop.get("target_filters", {})
    else:  # "in"
        endpoint_ids = [e.from_entity_id for e in edges_list]
        endpoint_filters = hop.get("source_filters", {})

    endpoint_qs = Entity.objects.using(db_alias).filter(id__in=endpoint_ids)
    if endpoint_filters:
        endpoint_qs = endpoint_qs.filter(**endpoint_filters)

    nodes = [_serialize_entity(e) for e in endpoint_qs]
    edges = [_serialize_edge(e) for e in edges_list]
    return {"nodes": nodes, "edges": edges, "info": {"total_count": total_count}, "warnings": {}}


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------


def _apply_order(qs: Any, order_by: list[str] | None, default: list[str]) -> Any:
    """Apply order_by to a queryset; fall back to deterministic default."""
    return qs.order_by(*(order_by if order_by else default))


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _serialize_entity(entity: Any) -> dict[str, Any]:
    """Serialize an Entity spine row to a node dict."""
    return {
        "entity_id": str(entity.id),
        "entity_type": entity.entity_type,
        "display_name": entity.display_name,
        "dimensions": entity.dimensions,
        "created_at": entity.created_at.isoformat() if entity.created_at else None,
        "updated_at": entity.updated_at.isoformat() if entity.updated_at else None,
    }


def _serialize_edge(edge: Any) -> dict[str, Any]:
    """Serialize an Edge model row to an edge dict."""
    return {
        "entity_id": str(edge.entity_id),
        "from_entity_id": str(edge.from_entity_id),
        "to_entity_id": str(edge.to_entity_id),
        "edge_type": edge.edge_type,
        "properties": edge.properties,
    }
