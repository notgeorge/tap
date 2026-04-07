"""TAP gryphon executor — lowers a GryphonAST to ORM queries and returns a canonical envelope.

V1 supported patterns
---------------------
The v1 executor handles two patterns:

Type scan (node-only):
    MATCH (c:character) RETURN c.entity_id, c.name, c.bio

Hub-and-spoke (one hop):
    MATCH (a)-[e]-(b)     WHERE a.entity_id = $var   (undirected, one hop)
    MATCH (a)-[e:T]-(b)   WHERE a.entity_id = $var   (typed edge, undirected)
    MATCH (a)-[e]->(b)    WHERE a.entity_id = $var   (outbound only)
    MATCH (a)<-[e]-(b)    WHERE a.entity_id = $var   (inbound only)

For type scans:
- Exactly one MATCH clause with a single node-only (no-edge) pattern.
- Node must carry a label (entity type slug).
- RETURN with field projections → row-like node dicts; omitted RETURN → graph envelope.

For hub-and-spoke:
- Exactly one MATCH clause with a single two-node, one-edge pattern.
- WHERE must constrain one node variable on entity_id via an equality against a $var.
- RETURN may be omitted or include only bound variables → graph envelope result.

Patterns outside this set raise SearchExecutionError("Unsupported gryphon pattern").
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tap_grid.exceptions import SearchExecutionError
from tap_grid.grift.subgraph import (
    SubgraphLayer,
    batch_resolve_entity_names,
    batch_resolve_icon_urls,
    batch_resolve_shapes,
    batch_resolve_typed_models,
    serialize_edge_extended,
    serialize_edge_full,
    serialize_edge_lite,
    serialize_node_extended,
    serialize_node_full,
    serialize_node_lite,
)
from tap_grid.gryphon.ast_nodes import (
    AndPred,
    Comparison,
    DotStep,
    EdgePattern,
    GryphonAST,
    NodePattern,
    NotPred,
    OrPred,
    ParamRef,
    ReturnClause,
    WhereClause,
)
from tap_grid.gryphon.parser import parse_gryphon

if TYPE_CHECKING:
    from tap_grid.models import Search


def execute_gryphon(
    search: Search,
    inputs: dict[str, Any],
    *,
    db_alias: str = "default",
    layer: SubgraphLayer = "full",
) -> dict[str, Any]:
    """Execute a gryphon-type Search and return the canonical graph envelope.

    Args:
        search: A Search instance with search_type="gryphon" and definition["query"].
        inputs: Runtime $var values; must supply all required params from the query.
        db_alias: Database alias for all queries (should be the read-only alias in production).
        layer: GRIFT subgraph return layer (lite, full, extended).

    Returns:
        ``{"nodes": [...], "edges": [...]}`` canonical envelope.

    Raises:
        SearchExecutionError: If the query is malformed, unsupported, or execution fails.
    """
    query = search.definition.get("query", "")
    if not query:
        raise SearchExecutionError("Gryphon search definition is missing 'query'.")

    ast = parse_gryphon(query)

    # Validate that all required $var names are present in inputs.
    required = ast.required_params()
    missing = required - set(inputs.keys())
    if missing:
        raise SearchExecutionError(f"Gryphon query requires inputs {sorted(missing)} but they were not provided.")

    return _execute_ast(ast, inputs, db_alias=db_alias, layer=layer)


# ---------------------------------------------------------------------------
# AST execution
# ---------------------------------------------------------------------------


def _execute_ast(
    ast: GryphonAST,
    inputs: dict[str, Any],
    *,
    db_alias: str,
    layer: SubgraphLayer,
) -> dict[str, Any]:
    """Dispatch to the appropriate execution strategy based on AST shape."""
    # V1: exactly one MATCH clause with a single two-node one-edge pattern.
    if len(ast.match_clauses) != 1:
        raise SearchExecutionError("Unsupported gryphon pattern: v1 supports exactly one MATCH clause.")
    mc = ast.match_clauses[0]
    if len(mc.patterns) != 1:
        raise SearchExecutionError("Unsupported gryphon pattern: v1 supports exactly one pattern per MATCH.")
    pattern = mc.patterns[0]

    # Type scan: node-only pattern (no edges).
    if len(pattern.edges) == 0:
        return _execute_type_scan(pattern.nodes[0], ast.return_clause, db_alias=db_alias, layer=layer)

    if len(pattern.edges) != 1:
        raise SearchExecutionError("Unsupported gryphon pattern: v1 supports exactly one edge (one hop).")

    edge_pat = pattern.edges[0]
    if edge_pat.min_hops != 1 or edge_pat.max_hops != 1:
        raise SearchExecutionError("Unsupported gryphon pattern: v1 does not support bounded multi-hop traversal.")

    # Find the anchor node variable constrained by entity_id in WHERE.
    anchor_var, entity_id_value = _extract_entity_id_anchor(ast.where_clause, inputs)
    if anchor_var is None or entity_id_value is None:
        raise SearchExecutionError(
            "Unsupported gryphon pattern: v1 requires WHERE <var>.entity_id = $param " "to identify the hub entity."
        )

    # Determine which node in the pattern is the anchor.
    left_node, right_node = pattern.nodes[0], pattern.nodes[1]
    if left_node.variable == anchor_var:
        hub_node = left_node
    elif right_node.variable == anchor_var:
        hub_node = right_node
    else:
        raise SearchExecutionError(
            f"Unsupported gryphon pattern: anchor variable '{anchor_var}' " "not found in MATCH pattern."
        )

    return _execute_hub_and_spoke(
        entity_id=str(entity_id_value),
        edge_pattern=edge_pat,
        db_alias=db_alias,
        layer=layer,
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
# Type-scan ORM execution
# ---------------------------------------------------------------------------

# Fields that live on Entity rather than the domain model.
_ENTITY_FIELDS: frozenset[str] = frozenset({"entity_type", "name", "dimensions", "version", "created_at", "updated_at"})


def _execute_type_scan(
    node: NodePattern,
    return_clause: ReturnClause,
    *,
    db_alias: str,
    layer: SubgraphLayer,
) -> dict[str, Any]:
    """Execute a node-only MATCH pattern — scan all entities of the given type.

    Args:
        node: The single node pattern; must carry a label (entity type slug).
        return_clause: Controls output shape (projected fields vs. graph envelope).
        db_alias: Database alias to query against.
        layer: GRIFT subgraph return layer.

    Returns:
        Canonical envelope with ``nodes`` list and empty ``edges`` list.

    Raises:
        SearchExecutionError: If the node pattern carries no label.
    """
    if not node.label:
        raise SearchExecutionError("Unsupported gryphon pattern: type scan requires a node label, e.g. (c:character).")

    from tap_grid.registry import get_model_class

    try:
        model_cls = get_model_class(node.label)
    except KeyError:
        raise SearchExecutionError(f"Unsupported gryphon pattern: unknown entity type '{node.label}'.")

    qs = model_cls.objects.using(db_alias).select_related("entity").order_by("entity__name")

    var = node.variable or node.label
    items = return_clause.items  # None → graph envelope

    if items is not None:
        # Projection mode — keep existing behavior (returns projected dicts).
        nodes: list[dict[str, Any]] = [_project_node(domain_obj, items, var) for domain_obj in qs]
        return {"nodes": nodes, "edges": []}

    # Graph envelope mode — use grift serializers.
    domain_objects = list(qs)
    nodes = _serialize_typed_nodes(domain_objects, layer, db_alias)
    return {"nodes": nodes, "edges": []}


def _project_node(domain_obj: Any, items: tuple, var: str) -> dict[str, Any]:
    """Build a projected dict for a domain model instance using RETURN items.

    Only items whose field_path.variable matches ``var`` and that have a single
    DotStep are resolved; others are silently skipped.

    Args:
        domain_obj: A domain model instance with a ``entity`` FK (via select_related).
        items: Tuple of ReturnItem from the RETURN clause.
        var: The variable name bound to this node in the MATCH pattern.

    Returns:
        Dict of {output_key: value} for matched projection items.
    """
    result: dict[str, Any] = {}
    for item in items:
        fp = item.path
        if fp.variable != var:
            continue
        if len(fp.steps) != 1 or not isinstance(fp.steps[0], DotStep):
            continue
        field_name = fp.steps[0].name
        key = item.alias if item.alias is not None else field_name
        result[key] = _resolve_field(domain_obj, field_name)
    return result


def _resolve_field(domain_obj: Any, field_name: str) -> Any:
    """Resolve a single field name from a domain model instance.

    ``entity_id`` is the FK UUID on the domain model itself.
    Fields in ``_ENTITY_FIELDS`` are read from the related Entity.
    All other names are read directly from the domain model.

    Args:
        domain_obj: Domain model instance (with entity FK pre-fetched).
        field_name: The bare field name from the RETURN projection.

    Returns:
        The field value; entity_id is coerced to str.
    """
    if field_name == "entity_id":
        return str(domain_obj.entity_id)
    if field_name in _ENTITY_FIELDS:
        return getattr(domain_obj.entity, field_name)
    return getattr(domain_obj, field_name)


# ---------------------------------------------------------------------------
# Hub-and-spoke ORM execution
# ---------------------------------------------------------------------------


def _execute_hub_and_spoke(
    entity_id: str,
    edge_pattern: EdgePattern,
    *,
    db_alias: str,
    layer: SubgraphLayer,
) -> dict[str, Any]:
    """Execute a one-hop neighborhood query for a single hub entity.

    Executes a one-hop neighborhood query driven from the gryphon AST.
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

    # select_related("entity") needed for full/extended edge serialization.
    extra_related = ["entity"] if layer != "lite" else []

    if direction in ("out", "any"):
        outbound_qs = (
            Edge.objects.using(db_alias)
            .filter(from_entity=hub, **edge_filter)
            .select_related("to_entity", *extra_related)
            .order_by("entity__created_at")
        )
        outbound = list(outbound_qs)
    else:
        outbound = []

    if direction in ("in", "any"):
        inbound_qs = (
            Edge.objects.using(db_alias)
            .filter(to_entity=hub, **edge_filter)
            .select_related("from_entity", *extra_related)
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
        {str(e.pk): e for e in Entity.objects.using(db_alias).filter(pk__in=neighbor_ids)} if neighbor_ids else {}
    )

    # Collect all entities for serialization.
    all_entities = [hub] + list(neighbors.values())

    # Filter qualifying edges (both endpoints in node set).
    node_id_set = {str(hub.pk)} | neighbor_ids
    qualifying_edges: list[Edge] = []
    for edge in outbound:
        if str(edge.to_entity_id) in node_id_set:
            qualifying_edges.append(edge)
    for edge in inbound:
        if str(edge.from_entity_id) in node_id_set:
            qualifying_edges.append(edge)

    # Serialize using grift layer serializers.
    nodes = _serialize_entity_nodes(all_entities, layer, db_alias)
    edges = _serialize_edge_list(qualifying_edges, layer, db_alias)

    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize_entity_nodes(
    entities: list[Any],
    layer: SubgraphLayer,
    db_alias: str,
) -> list[dict[str, Any]]:
    """Serialize Entity objects to node dicts at the requested layer."""
    if layer == "lite":
        return [serialize_node_lite(e) for e in entities]

    typed_models = batch_resolve_typed_models(entities, db_alias)

    if layer == "full":
        return [serialize_node_full(e, typed_models.get(str(e.pk))) for e in entities]

    # extended
    slugs = {e.entity_type for e in entities if e.entity_type != "edge"}
    icon_map = batch_resolve_icon_urls(slugs)
    shape_map = batch_resolve_shapes(slugs)

    return [
        serialize_node_extended(
            e,
            typed_models.get(str(e.pk)),
            icon_url=icon_map.get(e.entity_type, ""),
            shape=shape_map.get(e.entity_type, "ellipse"),
        )
        for e in entities
    ]


def _serialize_typed_nodes(
    domain_objects: list[Any],
    layer: SubgraphLayer,
    db_alias: str,
) -> list[dict[str, Any]]:
    """Serialize typed model instances (with pre-fetched entity) to node dicts."""
    if layer == "lite":
        return [serialize_node_lite(obj.entity) for obj in domain_objects]

    if layer == "full":
        return [serialize_node_full(obj.entity, obj) for obj in domain_objects]

    # extended
    slugs = {obj.entity.entity_type for obj in domain_objects}
    icon_map = batch_resolve_icon_urls(slugs)
    shape_map = batch_resolve_shapes(slugs)

    return [
        serialize_node_extended(
            obj.entity,
            obj,
            icon_url=icon_map.get(obj.entity.entity_type, ""),
            shape=shape_map.get(obj.entity.entity_type, "ellipse"),
        )
        for obj in domain_objects
    ]


def _serialize_edge_list(
    edges: list[Any],
    layer: SubgraphLayer,
    db_alias: str,
) -> list[dict[str, Any]]:
    """Serialize Edge objects to edge dicts at the requested layer."""
    if layer == "lite":
        return [serialize_edge_lite(e) for e in edges]

    if layer == "full":
        return [serialize_edge_full(e) for e in edges]

    # extended — resolve endpoint names.
    endpoint_ids: set[str] = set()
    for edge in edges:
        endpoint_ids.add(str(edge.from_entity_id))
        endpoint_ids.add(str(edge.to_entity_id))
    name_map = batch_resolve_entity_names(endpoint_ids, db_alias)

    return [
        serialize_edge_extended(
            e,
            from_name=name_map.get(str(e.from_entity_id), ""),
            to_name=name_map.get(str(e.to_entity_id), ""),
        )
        for e in edges
    ]
