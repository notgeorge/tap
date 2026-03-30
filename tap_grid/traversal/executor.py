"""TAP traversal executor — lowers a TraversalAST to ORM queries and returns a canonical envelope.

V1 supported patterns
---------------------
The v1 executor handles the hub-and-spoke pattern and close variants:

    MATCH (a)-[e]-(b)     WHERE a.entity_id = $var   (undirected, one hop)
    MATCH (a)-[e:T]-(b)   WHERE a.entity_id = $var   (typed edge, undirected)
    MATCH (a)-[e]->(b)    WHERE a.entity_id = $var   (outbound only)
    MATCH (a)<-[e]-(b)    WHERE a.entity_id = $var   (inbound only)

In all cases:
- Exactly one MATCH clause with a single two-node, one-edge pattern.
- WHERE must constrain one node variable on entity_id via an equality against a $var.
- RETURN may be omitted or include only bound variables → graph envelope result.

Patterns outside this set raise SearchExecutionError("Unsupported traversal pattern").
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tap_grid.exceptions import SearchExecutionError
from tap_grid.traversal.ast_nodes import (
    AndPred,
    Comparison,
    EdgePattern,
    FieldPath,
    MatchClause,
    NodePattern,
    NotPred,
    OrPred,
    ParamRef,
    PathPattern,
    ReturnClause,
    TraversalAST,
    WhereClause,
    DotStep,
)
from tap_grid.traversal.parser import parse_traversal

if TYPE_CHECKING:
    from tap_grid.models import Search


def execute_traversal(
    search: "Search",
    inputs: dict[str, Any],
    *,
    db_alias: str = "default",
) -> dict[str, Any]:
    """Execute a traversal-type Search and return the canonical graph envelope.

    Args:
        search: A Search instance with search_type="traversal" and definition["query"].
        inputs: Runtime $var values; must supply all required params from the query.
        db_alias: Database alias for all queries (should be the read-only alias in production).

    Returns:
        ``{"nodes": [...], "edges": [...]}`` canonical envelope.

    Raises:
        SearchExecutionError: If the query is malformed, unsupported, or execution fails.
    """
    query = search.definition.get("query", "")
    if not query:
        raise SearchExecutionError("Traversal search definition is missing 'query'.")

    ast = parse_traversal(query)

    # Validate that all required $var names are present in inputs.
    required = ast.required_params()
    missing = required - set(inputs.keys())
    if missing:
        raise SearchExecutionError(
            f"Traversal query requires inputs {sorted(missing)} but they were not provided."
        )

    return _execute_ast(ast, inputs, db_alias=db_alias)


# ---------------------------------------------------------------------------
# AST execution
# ---------------------------------------------------------------------------


def _execute_ast(
    ast: TraversalAST,
    inputs: dict[str, Any],
    *,
    db_alias: str,
) -> dict[str, Any]:
    """Dispatch to the appropriate execution strategy based on AST shape."""
    # V1: exactly one MATCH clause with a single two-node one-edge pattern.
    if len(ast.match_clauses) != 1:
        raise SearchExecutionError(
            "Unsupported traversal pattern: v1 supports exactly one MATCH clause."
        )
    mc = ast.match_clauses[0]
    if len(mc.patterns) != 1:
        raise SearchExecutionError(
            "Unsupported traversal pattern: v1 supports exactly one pattern per MATCH."
        )
    pattern = mc.patterns[0]
    if len(pattern.edges) != 1:
        raise SearchExecutionError(
            "Unsupported traversal pattern: v1 supports exactly one edge (one hop)."
        )

    edge_pat = pattern.edges[0]
    if edge_pat.min_hops != 1 or edge_pat.max_hops != 1:
        raise SearchExecutionError(
            "Unsupported traversal pattern: v1 does not support bounded multi-hop traversal."
        )

    # Find the anchor node variable constrained by entity_id in WHERE.
    anchor_var, entity_id_value = _extract_entity_id_anchor(ast.where_clause, inputs)
    if anchor_var is None or entity_id_value is None:
        raise SearchExecutionError(
            "Unsupported traversal pattern: v1 requires WHERE <var>.entity_id = $param "
            "to identify the hub entity."
        )

    # Determine which node in the pattern is the anchor.
    left_node, right_node = pattern.nodes[0], pattern.nodes[1]
    if left_node.variable == anchor_var:
        hub_node = left_node
    elif right_node.variable == anchor_var:
        hub_node = right_node
    else:
        raise SearchExecutionError(
            f"Unsupported traversal pattern: anchor variable '{anchor_var}' "
            "not found in MATCH pattern."
        )

    return _execute_hub_and_spoke(
        entity_id=str(entity_id_value),
        edge_pattern=edge_pat,
        db_alias=db_alias,
    )


def _extract_entity_id_anchor(
    where: WhereClause | None,
    inputs: dict[str, Any],
) -> tuple[str | None, Any]:
    """Walk the WHERE predicate tree to find a `<var>.entity_id = $param` comparison.

    Returns (variable_name, resolved_value) or (None, None) if no such comparison exists.
    Handles AND predicates — the first matching leaf wins.
    """
    if where is None:
        return None, None
    return _find_entity_id_in_predicate(where.predicate, inputs)


def _find_entity_id_in_predicate(pred: Any, inputs: dict[str, Any]) -> tuple[str | None, Any]:
    if isinstance(pred, Comparison):
        fp = pred.field_path
        # Match pattern: <variable>.entity_id = $param  (single dot step named "entity_id")
        if (
            len(fp.steps) == 1
            and isinstance(fp.steps[0], DotStep)
            and fp.steps[0].name == "entity_id"
            and pred.op == "="
        ):
            value = pred.value
            if isinstance(value, ParamRef):
                resolved = inputs.get(value.name)
                return fp.variable, resolved
            else:
                return fp.variable, value
        return None, None
    elif isinstance(pred, AndPred):
        var, val = _find_entity_id_in_predicate(pred.left, inputs)
        if var is not None:
            return var, val
        return _find_entity_id_in_predicate(pred.right, inputs)
    elif isinstance(pred, (OrPred, NotPred)):
        # Not supported as the primary anchor lookup path in v1.
        return None, None
    return None, None


# ---------------------------------------------------------------------------
# Hub-and-spoke ORM execution
# ---------------------------------------------------------------------------


def _execute_hub_and_spoke(
    entity_id: str,
    edge_pattern: EdgePattern,
    *,
    db_alias: str,
) -> dict[str, Any]:
    """Execute a one-hop neighborhood query for a single hub entity.

    Mirrors the logic of hub_and_spoke_runner but driven from the traversal AST.
    """
    from tap_grid.models import Edge, Entity

    # Load hub.
    try:
        hub = Entity.objects.using(db_alias).get(pk=entity_id)
    except Entity.DoesNotExist:
        return {
            "nodes": [],
            "edges": [],
            "warnings": {"not_found": f"entity {entity_id} not found."},
        }

    # Build edge filter kwargs.
    edge_filter: dict[str, Any] = {}
    if edge_pattern.edge_type:
        edge_filter["edge_type"] = edge_pattern.edge_type

    direction = edge_pattern.direction

    if direction in ("out", "any"):
        outbound_qs = (
            Edge.objects.using(db_alias)
            .filter(from_entity=hub, **edge_filter)
            .select_related("to_entity")
            .order_by("entity__created_at")
        )
        outbound = list(outbound_qs)
    else:
        outbound = []

    if direction in ("in", "any"):
        inbound_qs = (
            Edge.objects.using(db_alias)
            .filter(to_entity=hub, **edge_filter)
            .select_related("from_entity")
            .order_by("entity__created_at")
        )
        inbound = list(inbound_qs)
    else:
        inbound = []

    # Collect neighbor entity IDs.
    neighbor_ids: set[str] = set()
    for edge in outbound:
        neighbor_ids.add(str(edge.to_entity_id))
    for edge in inbound:
        neighbor_ids.add(str(edge.from_entity_id))

    neighbors = (
        {str(e.pk): e for e in Entity.objects.using(db_alias).filter(pk__in=neighbor_ids)}
        if neighbor_ids
        else {}
    )

    # Serialize nodes.
    nodes: list[dict[str, Any]] = [_node_dict(hub)]
    for entity in neighbors.values():
        nodes.append(_node_dict(entity))

    # Serialize edges (only those whose both endpoints are in the node set).
    node_ids = {str(hub.pk)} | neighbor_ids
    edges: list[dict[str, Any]] = []
    for edge in outbound:
        if str(edge.to_entity_id) in node_ids:
            edges.append(_edge_dict(edge))
    for edge in inbound:
        if str(edge.from_entity_id) in node_ids:
            edges.append(_edge_dict(edge))

    return {"nodes": nodes, "edges": edges}


def _node_dict(entity: Any) -> dict[str, Any]:
    return {
        "entity_id": str(entity.pk),
        "entity_type": entity.entity_type,
        "name": entity.name,
    }


def _edge_dict(edge: Any) -> dict[str, Any]:
    return {
        "entity_id": str(edge.entity_id),
        "from_entity_id": str(edge.from_entity_id),
        "to_entity_id": str(edge.to_entity_id),
        "edge_type": edge.edge_type,
    }
