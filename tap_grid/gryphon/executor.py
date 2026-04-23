"""TAP gryphon executor — lowers a GryphonAST to ORM queries and returns a canonical envelope.

V2 supported patterns
---------------------
The v2 executor handles three pattern types, with UNION merge across multiple MATCH clauses:

Type scan (node-only):
    MATCH (c:character) RETURN c.entity_id, c.name, c.bio

Hub-and-spoke (one hop, WHERE anchor):
    MATCH (a)-[e]-(b)     WHERE a.entity_id = $var   (undirected, one hop)
    MATCH (a)-[e:T]-(b)   WHERE a.entity_id = $var   (typed edge, undirected)
    MATCH (a)-[e]->(b)    WHERE a.entity_id = $var   (outbound only)
    MATCH (a)<-[e]-(b)    WHERE a.entity_id = $var   (inbound only)

Edge-type scan (one hop, no WHERE anchor):
    MATCH (r:realm)-[e:CONTAINS]->(l:location)
    MATCH (a:character)-[e:WIELDS]->(b:artifact)

Multiple MATCH clauses are executed independently (UNION semantics) and results are merged
with entity_id deduplication.

Patterns outside this set raise SearchExecutionError("Unsupported gryphon pattern").
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tap_grid.exceptions import SearchExecutionError
from tap_grid.grift.subgraph import (
    SubgraphLayer,
    batch_resolve_display,
    batch_resolve_entity_names,
    batch_resolve_icon_urls,
    batch_resolve_typed_models,
    serialize_edge_extended,
    serialize_edge_full,
    serialize_edge_lite,
    serialize_node_extended,
    serialize_node_full,
    serialize_node_lite,
)
from tap_grid.gryphon.ast_nodes import (
    AggregateCall,
    AggregateReturnItem,
    AndPred,
    Comparison,
    DotStep,
    EdgePattern,
    FieldPath,
    GryphonAST,
    MatchClause,
    NodePattern,
    NotExistsClause,
    NotPred,
    OrPred,
    ParamRef,
    PathPattern,
    Predicate,
    ReturnClause,
    ReturnItem,
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

    if _has_advanced_features(ast):
        return _execute_advanced(ast, inputs, db_alias=db_alias)

    return _execute_ast(ast, inputs, db_alias=db_alias, layer=layer)


def _has_advanced_features(ast: GryphonAST) -> bool:
    """True if the query uses NOT EXISTS, COUNT aggregation, or multi-hop patterns."""
    if ast.not_exists_clauses:
        return True
    if ast.return_clause.items is not None:
        for item in ast.return_clause.items:
            if isinstance(item, AggregateReturnItem):
                return True
    for mc in ast.match_clauses:
        for pattern in mc.patterns:
            if len(pattern.edges) > 1:
                return True
    return False


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
    """Dispatch to the appropriate execution strategy based on AST shape.

    Supports multiple MATCH clauses (UNION semantics): each clause is executed
    independently and results are merged with entity_id deduplication.
    """
    anchor_var, entity_id_value = _extract_entity_id_anchor(ast.where_clause, inputs)

    all_nodes: dict[str, dict[str, Any]] = {}
    all_edges: dict[str, dict[str, Any]] = {}

    for mc in ast.match_clauses:
        if len(mc.patterns) != 1:
            raise SearchExecutionError("Unsupported gryphon pattern: each MATCH clause must have exactly one pattern.")
        pattern = mc.patterns[0]

        result = _dispatch_pattern(
            pattern,
            anchor_var=anchor_var,
            entity_id_value=entity_id_value,
            return_clause=ast.return_clause,
            db_alias=db_alias,
            layer=layer,
        )

        for node in result.get("nodes", []):
            key = _node_key(node, layer)
            all_nodes.setdefault(key, node)
        for edge in result.get("edges", []):
            key = _edge_key(edge, layer)
            all_edges.setdefault(key, edge)

    return {"nodes": list(all_nodes.values()), "edges": list(all_edges.values())}


def _dispatch_pattern(
    pattern: PathPattern,
    *,
    anchor_var: str | None,
    entity_id_value: Any,
    return_clause: ReturnClause,
    db_alias: str,
    layer: SubgraphLayer,
) -> dict[str, Any]:
    """Route a single MATCH pattern to the appropriate execution mode."""
    # Type scan: node-only pattern (no edges).
    if len(pattern.edges) == 0:
        return _execute_type_scan(pattern.nodes[0], return_clause, db_alias=db_alias, layer=layer)

    if len(pattern.edges) != 1:
        raise SearchExecutionError("Unsupported gryphon pattern: only single-hop patterns are supported.")

    edge_pat = pattern.edges[0]
    if edge_pat.min_hops != 1 or edge_pat.max_hops != 1:
        raise SearchExecutionError("Unsupported gryphon pattern: bounded multi-hop traversal is not supported.")

    # Hub-and-spoke: has WHERE anchor.
    if anchor_var is not None and entity_id_value is not None:
        left_node, right_node = pattern.nodes[0], pattern.nodes[1]
        if left_node.variable != anchor_var and right_node.variable != anchor_var:
            # Anchor variable doesn't match this pattern — fall through to edge-type scan.
            pass
        else:
            return _execute_hub_and_spoke(
                entity_id=str(entity_id_value),
                edge_pattern=edge_pat,
                db_alias=db_alias,
                layer=layer,
            )

    # Edge-type scan: edge pattern with no WHERE anchor (or anchor not in this pattern).
    if not edge_pat.edge_type:
        raise SearchExecutionError("Unsupported gryphon pattern: edge-type scan requires a typed edge.")
    return _execute_edge_type_scan(
        left_node=pattern.nodes[0],
        right_node=pattern.nodes[1],
        edge_pattern=edge_pat,
        db_alias=db_alias,
        layer=layer,
    )


def _node_key(node: dict[str, Any], layer: SubgraphLayer) -> str:
    """Extract a dedup key from a serialized node dict."""
    if layer == "lite":
        return str(node["entity_id"])
    # Projected type-scan results are flat dicts with entity_id at top level.
    if "entity" in node:
        return str(node["entity"]["entity_id"])
    return str(node.get("entity_id", id(node)))


def _edge_key(edge: dict[str, Any], layer: SubgraphLayer) -> str:
    """Extract a dedup key from a serialized edge dict."""
    if layer == "lite":
        return str(edge["entity_id"])
    return str(edge["entity"]["entity_id"])


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
# Edge-type scan ORM execution
# ---------------------------------------------------------------------------


def _execute_edge_type_scan(
    left_node: NodePattern,
    right_node: NodePattern,
    edge_pattern: EdgePattern,
    *,
    db_alias: str,
    layer: SubgraphLayer,
) -> dict[str, Any]:
    """Execute an edge-type scan — all edges of a given type, filtered by endpoint labels.

    Used for patterns like ``MATCH (r:realm)-[e:CONTAINS]->(l:location)`` where there is
    no WHERE anchor. Scans all matching edges, filters by direction and endpoint types,
    and returns a graph envelope.
    """
    from tap_grid.models import Edge, Entity

    direction = edge_pattern.direction
    edge_type = edge_pattern.edge_type
    extra_related = ["entity"] if layer != "lite" else []

    qualifying_edges: list[Edge] = []

    if direction in ("out", "any"):
        filters: dict[str, Any] = {"edge_type": edge_type}
        if left_node.label:
            filters["from_entity__entity_type"] = left_node.label
        if right_node.label:
            filters["to_entity__entity_type"] = right_node.label
        qs = (
            Edge.objects.using(db_alias)
            .filter(**filters)
            .select_related("from_entity", "to_entity", *extra_related)
            .order_by("entity__created_at")
        )
        qualifying_edges.extend(qs)

    if direction in ("in", "any"):
        filters = {"edge_type": edge_type}
        if left_node.label:
            filters["to_entity__entity_type"] = left_node.label
        if right_node.label:
            filters["from_entity__entity_type"] = right_node.label
        qs = (
            Edge.objects.using(db_alias)
            .filter(**filters)
            .select_related("from_entity", "to_entity", *extra_related)
            .order_by("entity__created_at")
        )
        qualifying_edges.extend(qs)

    # Collect all endpoint entities.
    entity_map: dict[str, Entity] = {}
    for edge in qualifying_edges:
        entity_map.setdefault(str(edge.from_entity_id), edge.from_entity)
        entity_map.setdefault(str(edge.to_entity_id), edge.to_entity)

    all_entities = list(entity_map.values())

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
    display_map = batch_resolve_display(slugs)

    return [
        serialize_node_extended(
            e,
            typed_models.get(str(e.pk)),
            icon_url=icon_map.get(e.entity_type, ""),
            display=display_map.get(e.entity_type, {}),
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
    display_map = batch_resolve_display(slugs)

    return [
        serialize_node_extended(
            obj.entity,
            obj,
            icon_url=icon_map.get(obj.entity.entity_type, ""),
            display=display_map.get(obj.entity.entity_type, {}),
        )
        for obj in domain_objects
    ]


# ---------------------------------------------------------------------------
# v2: advanced executor (aggregation, NOT EXISTS, multi-hop)
# ---------------------------------------------------------------------------
#
# Routed to when the AST has any of:
#   - NOT EXISTS clause
#   - aggregate call in RETURN
#   - multi-hop MATCH pattern
#
# Builds a single Django queryset against Edge, applies WHERE and NOT EXISTS
# filters, and optionally performs GROUP BY + COUNT. Returns the canonical
# envelope with a `rows` field populated for aggregating queries.

# Whether a variable binds to the left, right, or edge of a hop.
# "from" = left endpoint of hop N, "to" = right endpoint, "edge" = the edge itself.


def _node_label_to_related(label: str | None) -> str | None:
    """Translate a gryphon node label (entity_type slug) to the Django reverse-relation name.

    Uses the class-name lowercase convention (BaseModel's `related_name="%(class)s"`):
    `finding` → `finding`, `exception` → `complianceexception`, etc.
    Returns None if the label is not registered.
    """
    if not label:
        return None
    from tap_grid.registry import get_model_class

    try:
        model_cls = get_model_class(label)
    except KeyError:
        return None
    return model_cls.__name__.lower()


# Entity-level fields that live on the Entity table rather than the domain model.
_ENTITY_LEVEL_FIELDS: frozenset[str] = frozenset({"entity_type", "name", "dimensions", "version", "created_at", "updated_at"})


def _build_var_bindings(pattern: PathPattern) -> dict[str, dict[str, Any]]:
    """Map each variable in a pattern to how it's addressed in the composed Edge queryset.

    For a single-hop pattern (a)-[e]->(b), the composed queryset starts from Edge
    and the bindings are:
      - a → {"role": "node", "side": "from", "hop": 0, "label": a.label}
      - e → {"role": "edge", "hop": 0}
      - b → {"role": "node", "side": "to",   "hop": 0, "label": b.label}

    Multi-hop patterns (a)-[e1]->(b)-[e2]->(c) reuse the "to" of hop N as the "from"
    of hop N+1; serial fetch in `_execute_advanced` joins the hops explicitly.
    """
    bindings: dict[str, dict[str, Any]] = {}
    for hop_idx, edge in enumerate(pattern.edges):
        left = pattern.nodes[hop_idx]
        right = pattern.nodes[hop_idx + 1]
        if left.variable and left.variable not in bindings:
            bindings[left.variable] = {"role": "node", "side": "from", "hop": hop_idx, "label": left.label}
        if right.variable and right.variable not in bindings:
            bindings[right.variable] = {"role": "node", "side": "to", "hop": hop_idx, "label": right.label}
        if edge.variable and edge.variable not in bindings:
            bindings[edge.variable] = {"role": "edge", "hop": hop_idx}
    # Node-only patterns (no edges) still want the lone node bound.
    if not pattern.edges and pattern.nodes:
        n = pattern.nodes[0]
        if n.variable:
            bindings[n.variable] = {"role": "node", "side": "lone", "hop": 0, "label": n.label}
    return bindings


def _orm_path_for_field(binding: dict[str, Any], field: str) -> str:
    """Build the Django ORM lookup string for `var.field` against the single-hop Edge queryset.

    Only meaningful for hop=0; multi-hop callers use intermediate querysets.
    """
    role = binding["role"]
    if role == "edge":
        if field == "entity_id":
            return "entity_id"
        if field in _ENTITY_LEVEL_FIELDS:
            return f"entity__{field}"
        # Edge custom fields like edge_type, properties:
        return field
    # role == "node"
    side = binding["side"]  # "from" | "to" | "lone"
    # entity_id is the FK on Edge.
    if field == "entity_id":
        return f"{side}_entity_id"
    if field in _ENTITY_LEVEL_FIELDS:
        return f"{side}_entity__{field}"
    # Domain-model field: traverse {side}_entity__<reverse_name>__<field>.
    label = binding.get("label")
    reverse = _node_label_to_related(label)
    if reverse is None:
        raise SearchExecutionError(
            f"Cannot resolve '{field}' on variable without a node label; add a label like "
            f"`(var:entity_type)` so the executor knows which model to traverse."
        )
    return f"{side}_entity__{reverse}__{field}"


def _resolve_value(value: Any, inputs: dict[str, Any]) -> Any:
    """Resolve a gryphon value to a Python value (ParamRef → looked up in inputs)."""
    if isinstance(value, ParamRef):
        return inputs.get(value.name)
    return value


def _build_hop_queryset(
    pattern: PathPattern,
    hop_idx: int,
    db_alias: str,
):
    """Build an Edge queryset for a single hop, filtered by edge_type and endpoint labels."""
    from tap_grid.models import Edge

    edge_pat = pattern.edges[hop_idx]
    left = pattern.nodes[hop_idx]
    right = pattern.nodes[hop_idx + 1]

    qs = Edge.objects.using(db_alias)
    if edge_pat.edge_type:
        qs = qs.filter(edge_type=edge_pat.edge_type)

    # Endpoint-label filters apply based on direction.
    if edge_pat.direction == "out":
        if left.label:
            qs = qs.filter(from_entity__entity_type=left.label)
        if right.label:
            qs = qs.filter(to_entity__entity_type=right.label)
    elif edge_pat.direction == "in":
        if left.label:
            qs = qs.filter(to_entity__entity_type=left.label)
        if right.label:
            qs = qs.filter(from_entity__entity_type=right.label)
    else:
        # undirected: permissive — any direction, labels apply on whichever side matches.
        # In practice most queries use explicit direction; the undirected case is unusual
        # and we defer supporting it in combination with aggregation to a future iteration.
        raise SearchExecutionError(
            "Undirected edge patterns are not supported by the aggregation executor; use -> or <-."
        )

    return qs


def _apply_predicate_to_qs(
    qs,
    predicate: Predicate | None,
    bindings: dict[str, dict[str, Any]],
    inputs: dict[str, Any],
):
    """Apply a WHERE predicate tree to a queryset. Currently supports conjunctions of
    simple comparisons; OR/NOT predicates are rejected at parse-to-query time.
    """
    if predicate is None:
        return qs
    for comp in _flatten_conjunction(predicate):
        qs = _apply_comparison(qs, comp, bindings, inputs)
    return qs


def _flatten_conjunction(predicate: Predicate) -> list[Comparison]:
    """Flatten an AND tree into a list of Comparisons. Reject OR/NOT (not yet supported in v2)."""
    if isinstance(predicate, Comparison):
        return [predicate]
    if isinstance(predicate, AndPred):
        return _flatten_conjunction(predicate.left) + _flatten_conjunction(predicate.right)
    raise SearchExecutionError(
        "Aggregation executor currently supports only AND-joined comparisons in WHERE; "
        "OR and NOT predicates are not yet implemented in this path."
    )


def _apply_comparison(
    qs,
    comp: Comparison,
    bindings: dict[str, dict[str, Any]],
    inputs: dict[str, Any],
):
    fp = comp.field_path
    var = fp.variable
    if var not in bindings:
        raise SearchExecutionError(f"Unknown variable '{var}' in WHERE predicate.")
    if len(fp.steps) != 1 or not isinstance(fp.steps[0], DotStep):
        raise SearchExecutionError("WHERE predicates support single dot-step field paths only.")
    field_name = fp.steps[0].name

    orm_path = _orm_path_for_field(bindings[var], field_name)
    value = _resolve_value(comp.value, inputs)

    lookup_suffix = {"=": "", "!=": "", "<": "__lt", ">": "__gt", "<=": "__lte", ">=": "__gte"}[comp.op]
    if comp.op == "!=":
        return qs.exclude(**{orm_path: value})
    return qs.filter(**{f"{orm_path}{lookup_suffix}": value})


def _apply_not_exists(
    outer_qs,
    nec: NotExistsClause,
    outer_bindings: dict[str, dict[str, Any]],
    inputs: dict[str, Any],
    db_alias: str,
):
    """Apply a NOT EXISTS clause to the outer queryset via a correlated Exists subquery."""
    from django.db.models import Exists, OuterRef

    if len(nec.match_clause.patterns) != 1:
        raise SearchExecutionError("NOT EXISTS subqueries require exactly one pattern.")
    inner_pattern = nec.match_clause.patterns[0]
    if len(inner_pattern.edges) != 1:
        raise SearchExecutionError(
            "NOT EXISTS subqueries currently support single-hop inner patterns only."
        )

    inner_bindings = _build_var_bindings(inner_pattern)
    inner_qs = _build_hop_queryset(inner_pattern, 0, db_alias)

    # Correlation: for every variable shared between outer and inner bindings,
    # constrain the inner's ORM path to equal OuterRef of the outer's path.
    shared = set(outer_bindings.keys()) & set(inner_bindings.keys())
    if not shared:
        raise SearchExecutionError(
            "NOT EXISTS subqueries must share at least one variable with the outer pattern."
        )
    for var in shared:
        inner_bind = inner_bindings[var]
        outer_bind = outer_bindings[var]
        # Correlate on entity_id (the FK column); both sides use the FK lookup.
        inner_path = _orm_path_for_field(inner_bind, "entity_id")
        outer_path = _orm_path_for_field(outer_bind, "entity_id")
        inner_qs = inner_qs.filter(**{inner_path: OuterRef(outer_path)})

    # Apply the inner WHERE predicates.
    inner_qs = _apply_predicate_to_qs(
        inner_qs,
        nec.where_clause.predicate if nec.where_clause else None,
        inner_bindings,
        inputs,
    )

    return outer_qs.filter(~Exists(inner_qs))


def _execute_advanced(
    ast: GryphonAST,
    inputs: dict[str, Any],
    *,
    db_alias: str,
) -> dict[str, Any]:
    """Route through the v2 aggregation/anti-join/multi-hop path."""
    if len(ast.match_clauses) != 1:
        raise SearchExecutionError(
            "Aggregation executor currently supports exactly one top-level MATCH clause."
        )
    mc = ast.match_clauses[0]
    if len(mc.patterns) != 1:
        raise SearchExecutionError(
            "Aggregation executor currently supports exactly one pattern per MATCH clause."
        )
    pattern = mc.patterns[0]
    if len(pattern.edges) == 0:
        raise SearchExecutionError(
            "Aggregation executor requires at least one edge in the MATCH pattern."
        )
    if len(pattern.edges) > 1:
        raise SearchExecutionError(
            "Multi-hop aggregation patterns are grammar-accepted but not yet implemented in the "
            "executor. File a follow-up spec extension."
        )

    bindings = _build_var_bindings(pattern)
    qs = _build_hop_queryset(pattern, 0, db_alias)

    # Outer WHERE predicates.
    qs = _apply_predicate_to_qs(
        qs,
        ast.where_clause.predicate if ast.where_clause else None,
        bindings,
        inputs,
    )

    # NOT EXISTS clauses.
    for nec in ast.not_exists_clauses:
        qs = _apply_not_exists(qs, nec, bindings, inputs, db_alias)

    # Compute rows.
    rows = _compute_rows(qs, ast.return_clause, bindings)

    return {"nodes": [], "edges": [], "rows": rows}


def _compute_rows(
    qs,
    return_clause: ReturnClause,
    bindings: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Execute the queryset and produce row dicts honoring RETURN aliases and aggregates."""
    from django.db.models import Count

    items = return_clause.items
    if items is None:
        raise SearchExecutionError(
            "Aggregation executor requires an explicit RETURN clause."
        )

    # Partition into field projections and aggregates.
    field_items: list[ReturnItem] = []
    aggregate_items: list[AggregateReturnItem] = []
    for item in items:
        if isinstance(item, AggregateReturnItem):
            aggregate_items.append(item)
        elif isinstance(item, ReturnItem):
            field_items.append(item)
        else:
            raise SearchExecutionError(f"Unexpected RETURN item type: {type(item).__name__}")

    # Resolve field items to ORM column paths.
    group_by_cols: list[tuple[str, str]] = []  # (orm_path, alias)
    for fi in field_items:
        fp: FieldPath = fi.path
        if fp.variable not in bindings:
            raise SearchExecutionError(f"Unknown variable '{fp.variable}' in RETURN.")
        if len(fp.steps) != 1 or not isinstance(fp.steps[0], DotStep):
            raise SearchExecutionError("RETURN field paths support single dot-step only in v1.")
        field_name = fp.steps[0].name
        orm_path = _orm_path_for_field(bindings[fp.variable], field_name)
        alias = fi.alias or field_name
        group_by_cols.append((orm_path, alias))

    # Resolve aggregate items.
    aggregate_annotations: dict[str, Any] = {}
    for ai in aggregate_items:
        agg: AggregateCall = ai.aggregate
        if agg.function != "count":
            raise SearchExecutionError(f"Unsupported aggregate function: {agg.function}")
        arg: FieldPath = agg.argument
        if arg.variable not in bindings:
            raise SearchExecutionError(f"Unknown variable '{arg.variable}' in COUNT().")
        # For COUNT(var), count by the variable's entity_id; for COUNT(var.field), count that field.
        if len(arg.steps) == 0:
            count_col = _orm_path_for_field(bindings[arg.variable], "entity_id")
        elif len(arg.steps) == 1 and isinstance(arg.steps[0], DotStep):
            count_col = _orm_path_for_field(bindings[arg.variable], arg.steps[0].name)
        else:
            raise SearchExecutionError("COUNT argument must be a bare variable or single dot-step.")
        aggregate_annotations[ai.alias] = Count(count_col)

    if aggregate_annotations:
        # GROUP BY: the .values() columns become the group keys.
        value_names = [orm for orm, _ in group_by_cols]
        qs = qs.values(*value_names).annotate(**aggregate_annotations).order_by(*value_names)
        raw_rows = list(qs)
        # Map ORM column names back to RETURN aliases.
        rows: list[dict[str, Any]] = []
        for raw in raw_rows:
            row: dict[str, Any] = {}
            for orm, alias in group_by_cols:
                val = raw.get(orm)
                row[alias] = str(val) if hasattr(val, "hex") else val
            for ai in aggregate_items:
                row[ai.alias] = raw.get(ai.alias)
            rows.append(row)
        return rows

    # No aggregation — just project fields per row.
    value_names = [orm for orm, _ in group_by_cols]
    raw_rows = list(qs.values(*value_names))
    rows = []
    for raw in raw_rows:
        row = {}
        for orm, alias in group_by_cols:
            val = raw.get(orm)
            row[alias] = str(val) if hasattr(val, "hex") else val
        rows.append(row)
    return rows


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
