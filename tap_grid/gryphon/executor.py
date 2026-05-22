"""TAP gryphon executor — lowers a GryphonAST to ORM queries and returns a canonical envelope.

Supported patterns
------------------
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

Multi-hop chain with aggregation (advanced path):
    MATCH (e)-[:HAS_FINDING]->(f:finding)-[:REFERS_TO]->(i:indicator)
    WHERE f.status = "open"
    RETURN e.entity_id AS entity_id, COUNT(f) AS count

NOT EXISTS anti-join subquery:
    MATCH (e)-[:HAS_FINDING]->(f:finding)
    NOT EXISTS { MATCH (x:exception)-[:COVERS_FINDING]->(f) WHERE x.status = "active" }
    RETURN e.entity_id AS entity_id, COUNT(f) AS count

Multiple top-level MATCH clauses are executed independently (UNION semantics) with entity_id
deduplication — advanced-path queries (NOT EXISTS, COUNT, multi-hop) require a single MATCH.
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
    KeyStep,
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
from tap_grid.gryphon.capture import capture_sql, gryphon_stage
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

    return execute_gryphon_raw(query, inputs, db_alias=db_alias, layer=layer)


def execute_gryphon_raw(
    query: str,
    inputs: dict[str, Any],
    *,
    db_alias: str = "default",
    layer: SubgraphLayer = "full",
) -> dict[str, Any]:
    """Execute a raw gryphon query string and return the canonical graph envelope.

    Unlike execute_gryphon(), this does not require a stored Search entity.
    Used by the arrangement runtime and other consumers that hold inline
    gryphon query strings.

    Args:
        query: A gryphon query string.
        inputs: Runtime $var values; must supply all required params from the query.
        db_alias: Database alias for all queries (should be the read-only alias in production).
        layer: GRIFT subgraph return layer (lite, full, extended).

    Returns:
        ``{"nodes": [...], "edges": [...]}`` canonical envelope.

    Raises:
        SearchExecutionError: If the query is malformed, unsupported, or execution fails.
    """
    if not query:
        raise SearchExecutionError("Gryphon query string is empty.")

    ast = parse_gryphon(query)

    # Validate that all required $var names are present in inputs.
    required = ast.required_params()
    missing = required - set(inputs.keys())
    if missing:
        raise SearchExecutionError(f"Gryphon query requires inputs {sorted(missing)} but they were not provided.")

    if _has_advanced_features(ast):
        with gryphon_stage("advanced"):
            return _execute_advanced(ast, inputs, db_alias=db_alias, layer=layer)

    return _execute_ast(ast, inputs, db_alias=db_alias, layer=layer)


def explain_gryphon_raw(
    query: str,
    inputs: dict[str, Any],
    *,
    db_alias: str = "default",
    layer: SubgraphLayer = "full",
) -> dict[str, Any]:
    """Execute a raw gryphon query and return both the envelope and the SQL it ran.

    Returns ``{"envelope": <canonical envelope>, "sql": <SqlCapture>}``. The
    ``sql`` value is the ordered, stage-labelled sequence of SELECT statements
    the executor issued — the basis of the Gridkin expected-SQL snapshot
    (``spec-gridkin-v0.md``, ``req-gridkin-explain-snapshot``) and the future
    ``gryphon explain`` developer surface (Gryphon wishlist H3).

    The executor runs unchanged; the SQL is observed via a
    ``connection.execute_wrapper`` for the duration of the call. Because a
    multi-stage query feeds each stage from the prior stage's results, the
    capture happens during execution, not as a pure compile step.

    Args:
        query: A gryphon query string.
        inputs: Runtime $var values; must supply all required params.
        db_alias: Database alias for all queries.
        layer: GRIFT subgraph return layer (lite, full, extended).

    Returns:
        ``{"envelope": {...}, "sql": SqlCapture}``.

    Raises:
        SearchExecutionError: If the query is malformed, unsupported, or fails.
    """
    with capture_sql() as capture:
        envelope = execute_gryphon_raw(query, inputs, db_alias=db_alias, layer=layer)
    return {"envelope": envelope, "sql": capture}


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
    independently and results are merged with entity_id deduplication. A single
    global WHERE is applied to each MATCH, scoped to the variables that clause
    binds (per ``_filter_predicate_for_bindings``).
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
            where_clause=ast.where_clause,
            inputs=inputs,
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
    where_clause: Any = None,
    inputs: dict[str, Any] | None = None,
    db_alias: str,
    layer: SubgraphLayer,
) -> dict[str, Any]:
    """Route a single MATCH pattern to the appropriate execution mode."""
    # Type scan: node-only pattern (no edges).
    if len(pattern.edges) == 0:
        with gryphon_stage("type-scan"):
            return _execute_type_scan(
                pattern.nodes[0],
                return_clause,
                where_clause=where_clause,
                inputs=inputs or {},
                db_alias=db_alias,
                layer=layer,
            )

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
            with gryphon_stage("hub-and-spoke"):
                return _execute_hub_and_spoke(
                    entity_id=str(entity_id_value),
                    edge_pattern=edge_pat,
                    db_alias=db_alias,
                    layer=layer,
                )

    # Edge-type scan: edge pattern with no WHERE anchor (or anchor not in this pattern).
    if not edge_pat.edge_type:
        raise SearchExecutionError("Unsupported gryphon pattern: edge-type scan requires a typed edge.")
    with gryphon_stage("edge-type-scan"):
        return _execute_edge_type_scan(
            left_node=pattern.nodes[0],
            right_node=pattern.nodes[1],
            edge_pattern=edge_pat,
            db_alias=db_alias,
            layer=layer,
        )


def _node_key(node: dict[str, Any], layer: SubgraphLayer) -> str:
    """Extract a dedup key from a serialized node envelope.

    Under spec-grift-envelope, entity_id is always at the top level of
    the envelope across all layers.
    """
    return str(node["entity_id"])


def _edge_key(edge: dict[str, Any], layer: SubgraphLayer) -> str:
    """Extract a dedup key from a serialized edge envelope.

    Under spec-grift-envelope, entity_id is always at the top level of
    the envelope across all layers.
    """
    return str(edge["entity_id"])


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
_ENTITY_FIELDS: frozenset[str] = frozenset()  # populated lazily via _spine_field_names()


def _execute_type_scan(
    node: NodePattern,
    return_clause: ReturnClause,
    *,
    where_clause: Any = None,
    inputs: dict[str, Any] | None = None,
    db_alias: str,
    layer: SubgraphLayer,
) -> dict[str, Any]:
    """Execute a node-only MATCH pattern — scan all entities of the given type.

    Applies a global WHERE clause filtered to predicates that reference the
    type-scan's bound variable (per ``_filter_predicate_for_bindings``).
    Predicates referencing other variables (from other MATCH clauses in a
    UNION query) are skipped.

    Args:
        node: The single node pattern; must carry a label (entity type slug).
        return_clause: Controls output shape (projected fields vs. graph envelope).
        where_clause: Optional global WHERE clause; only variable-matching
            predicates are applied.
        inputs: Runtime parameter values for ``$param`` references in WHERE.
        db_alias: Database alias to query against.
        layer: GRIFT subgraph return layer.

    Returns:
        Canonical envelope with ``nodes`` list and empty ``edges`` list.
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
    inputs = inputs or {}

    # Apply WHERE comparisons scoped to this variable.
    if where_clause is not None:
        scoped_pred = _filter_predicate_for_bindings(
            where_clause.predicate, {var: {"role": "typescan", "label": node.label}}
        )
        if scoped_pred is not None:
            qs = _apply_typescan_predicate(qs, scoped_pred, var, inputs)

    # Graph envelope mode — RETURN omitted, or RETURN names only bare variables.
    # A bare `RETURN n` requests the node itself, which is the graph envelope;
    # projection mode (projected field dicts) is for RETURN clauses that name
    # field paths. This mirrors the advanced executor's _is_graph_envelope_return
    # — without it, `MATCH (n:type) RETURN n` returned a list of empty dicts.
    if _is_graph_envelope_return(return_clause):
        domain_objects = list(qs)
        nodes = _serialize_typed_nodes(domain_objects, layer, db_alias)
        return {"nodes": nodes, "edges": []}

    # Projection mode — RETURN names field paths; returns projected field dicts.
    items = return_clause.items
    assert items is not None  # _is_graph_envelope_return is True when items is None
    projected: list[dict[str, Any]] = [_project_node(domain_obj, items, var) for domain_obj in qs]
    return {"nodes": projected, "edges": []}


def _apply_typescan_predicate(
    qs,
    predicate: Any,
    var: str,
    inputs: dict[str, Any],
):
    """Apply a WHERE predicate tree to a type-scan queryset.

    Supports AND-of-comparisons today (mirrors the aggregation executor's
    current scope per ``_flatten_conjunction``). OR/NOT inside type-scan
    WHEREs is rejected with a clear error; demand-tracked for later.
    """
    for comp in _flatten_conjunction(predicate):
        if comp.field_path.variable != var:
            continue
        orm_path = _typescan_orm_path(comp.field_path)
        value = _resolve_value(comp.value, inputs)
        if comp.op == "!=":
            qs = qs.exclude(**{orm_path: value})
        else:
            suffix = {"=": "", "<": "__lt", ">": "__gt", "<=": "__lte", ">=": "__gte"}[comp.op]
            qs = qs.filter(**{f"{orm_path}{suffix}": value})
    return qs


def _typescan_orm_path(field_path: FieldPath) -> str:
    """Translate a Gryphon FieldPath to a Django ORM lookup for a type-scan queryset.

    The queryset is on the per-model class (e.g. LambdaFunction), so:

    - ``n.entity_id`` → ``entity_id`` (FK column on the per-model row)
    - ``n.<spinefield>`` → ``entity__<field>`` (cross-table join via the FK)
    - ``n.dimensions.<key>...`` → ``entity__dimensions__<key>...`` (JSON nested
      via FK; only JSON-typed spine fields can be multi-step-walked)
    - ``n.data.<x>...`` → ``<x>...`` (direct attribute on the per-model row;
      multi-step `__`-joined for JSONField nested keys)
    - ``n.display.<...>`` → rejected; computed-not-stored.
    """
    steps = field_path.steps
    if not steps or not isinstance(steps[0], DotStep):
        raise SearchExecutionError("FieldPath must start with a dot-step.")

    first = steps[0].name
    spine_fields = _spine_field_names()

    # Single-step.
    if len(steps) == 1:
        if first == "entity_id":
            return "entity_id"
        if first in spine_fields:
            return f"entity__{first}"
        if first in {_DATA_LANE_PREFIX, _DISPLAY_LANE_PREFIX}:
            raise SearchExecutionError(
                f"Bare `{first}` is not a complete path. Use `{first}.<...>` to " f"address the {first} lane."
            )
        raise SearchExecutionError(
            f"Field {first!r} is not a spine field. If it lives on the per-model "
            f"row, address it as `<var>.data.{first}` per spec-grift-envelope."
        )

    # Multi-step.
    if first == _DISPLAY_LANE_PREFIX:
        raise SearchExecutionError(
            "Cannot use the `display` lane in WHERE/RETURN paths today — display "
            "values are computed for rendering, not stored."
        )

    rest_steps = steps[1:]
    for step in rest_steps:
        if not isinstance(step, DotStep) and not isinstance(step, KeyStep):
            raise SearchExecutionError("Multi-step paths support dot-steps and bracket-key steps only.")

    def _name(step):
        return step.name if isinstance(step, DotStep) else step.key

    rest = "__".join(_name(s) for s in rest_steps)

    if first == _DATA_LANE_PREFIX:
        return rest

    # Multi-step into a JSON-typed spine field (today: `dimensions`).
    if first in _JSON_TYPED_SPINE_FIELDS:
        return f"entity__{first}__{rest}"

    if first in spine_fields:
        raise SearchExecutionError(
            f"Spine field {first!r} is a scalar; cannot walk into it. For nested "
            f"access into JSON-typed columns, use `<var>.data.<field>...` or "
            f"`<var>.dimensions.<key>` for the dimensions spine field."
        )

    raise SearchExecutionError(
        f"Unknown field path prefix {first!r}. Use a spine field, the `data` "
        f"prefix for per-model fields, or `dimensions.<key>` for dimension "
        f"scoping."
    )


# Spine fields that are JSON-typed and therefore support multi-step walking
# into nested keys. Today only `dimensions`; future JSON-typed spine fields
# slot in here.
_JSON_TYPED_SPINE_FIELDS: frozenset[str] = frozenset({"dimensions"})


def _project_node(domain_obj: Any, items: tuple, var: str) -> dict[str, Any]:
    """Build a projected dict for a domain model instance using RETURN items.

    Per spec-grid-traversal-language § Envelope-Aware Field Paths
    (req-grid-traversal-lang-envelope-paths):

    - ``var.<spinefield>`` resolves against the Entity row.
    - ``var.data.<...>`` resolves against the per-model row, walking
      remaining dot-steps as attribute access (single step) or nested
      dict keys (multi-step inside JSON-typed fields like ``tags``).
    - ``var.display.<...>`` is rejected for now — display values are
      computed for rendering and not available in the projection
      pipeline. Use the ``extended`` return layer for display data.

    Items whose field_path.variable doesn't match ``var`` are silently
    skipped (they apply to a different variable's projection).
    """
    result: dict[str, Any] = {}
    for item in items:
        fp = item.path
        if fp.variable != var:
            continue
        if not fp.steps or not isinstance(fp.steps[0], DotStep):
            continue
        first = fp.steps[0].name
        key, value = _resolve_envelope_path(domain_obj, fp, item.alias)
        result[key] = value
    return result


def _resolve_envelope_path(domain_obj: Any, field_path: FieldPath, explicit_alias: str | None) -> tuple[str, Any]:
    """Resolve a single envelope-aware path against a domain model instance.

    Returns ``(user_alias, value)``. The user alias is the explicit AS
    alias if supplied, otherwise the last dot-step in the path.
    """
    steps = field_path.steps
    first = steps[0].name
    spine_fields = _spine_field_names()

    if first == _DISPLAY_LANE_PREFIX:
        raise SearchExecutionError(
            "Cannot use the `display` lane in RETURN paths today — display "
            "values are computed for rendering, not stored. For display data "
            "use the `extended` return layer."
        )

    if first == _DATA_LANE_PREFIX:
        rest = steps[1:]
        if not rest:
            raise SearchExecutionError(
                "Path `<var>.data` requires at least one further step " "(e.g. `<var>.data.<field>`)."
            )
        for step in rest:
            if not isinstance(step, DotStep):
                raise SearchExecutionError("Inside the `data` lane only dot-steps are supported in v1.")
        value: Any = domain_obj
        for step in rest:
            if value is None:
                break
            value = value.get(step.name) if isinstance(value, dict) else getattr(value, step.name, None)
        last = rest[-1].name
        user_alias = explicit_alias if explicit_alias is not None else last
        return user_alias, value

    # Single-step spine field.
    if len(steps) > 1:
        raise SearchExecutionError(
            f"Spine field {first!r} cannot be walked into. For nested access "
            f"use `<var>.data.<field>...` per spec-grift-envelope."
        )
    if first == "entity_id":
        value = str(domain_obj.entity_id)
    elif first in spine_fields:
        value = getattr(domain_obj.entity, first)
    else:
        raise SearchExecutionError(
            f"Field {first!r} is not a spine field. If it lives on the per-model "
            f"row, address it as `<var>.data.{first}` per spec-grift-envelope."
        )
    user_alias = explicit_alias if explicit_alias is not None else first
    return user_alias, value


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

    # Inline edge-property map filter (req-grid-traversal-lang-filters-1).
    for key, raw_value in edge_pattern.inline_props.items():
        edge_filter[f"properties__{key}"] = _resolve_value(raw_value, {})

    direction = edge_pattern.direction

    # select_related("entity") needed for full/extended edge serialization.
    # The edge's own Entity is needed by every layer's serializer for the spine
    # surface — select_related it always (skipping it at "lite" caused an N+1).
    extra_related = ["entity"]

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

    # sorted() so the IN-list is deterministic — keeps the captured SQL stable
    # for Gridkin snapshots (set iteration order is hash-randomized per process).
    neighbors = (
        {str(e.pk): e for e in Entity.objects.using(db_alias).filter(pk__in=sorted(neighbor_ids))}
        if neighbor_ids
        else {}
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
    # The edge's own Entity is needed by every layer's serializer for the spine
    # surface — select_related it always (skipping it at "lite" caused an N+1).
    extra_related = ["entity"]

    # Inline edge-property map filter (req-grid-traversal-lang-filters-1).
    inline_prop_filters: dict[str, Any] = {
        f"properties__{k}": _resolve_value(v, {}) for k, v in edge_pattern.inline_props.items()
    }

    qualifying_edges: list[Edge] = []

    if direction in ("out", "any"):
        filters: dict[str, Any] = {"edge_type": edge_type, **inline_prop_filters}
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
        filters = {"edge_type": edge_type, **inline_prop_filters}
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
            tap_viz_hints=display_map.get(e.entity_type, {}),
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
            tap_viz_hints=display_map.get(obj.entity.entity_type, {}),
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


# Entity-level (spine) field names — sourced from Entity.SPINE_FIELD_NAMES,
# the canonical surface defined by spec-grid-entity (req-grid-entity-spine-surface).
# Computed lazily because importing Entity at module top would create a circular
# import.
def _spine_field_names() -> frozenset[str]:
    from tap_grid.models import Entity

    # Exclude `entity_id` from the spine-traversal set: it's a spine field for
    # the envelope but the path resolver handles it specially via the FK column
    # (`_orm_path_for_field`'s entity_id branch) rather than through a generic
    # `__entity__<field>` JOIN.
    return frozenset(Entity.SPINE_FIELD_NAMES) - {"entity_id"}


# Envelope-aware path prefixes — see spec-grid-traversal-language
# (req-grid-traversal-lang-envelope-paths). Reserved names that must not
# collide with spine field names.
_DATA_LANE_PREFIX = "data"
_DISPLAY_LANE_PREFIX = "display"


def _compute_hop_paths(pattern: PathPattern) -> list[dict[str, str]]:
    """Compute per-hop ORM path prefixes for a chain rooted at `Edge` (hop 0).

    For a chain ``(a)-[e0:R1]->(b)-[e1:R2]->(c)``:
      - hop 0: edge_path="", from_path="from_entity", to_path="to_entity"
      - hop 1: edge_path="to_entity__edges_out",
               from_path="to_entity",
               to_path="to_entity__edges_out__to_entity"

    Each subsequent hop extends the previous hop's shared-node path by one of:
      - ``__edges_out`` when the next hop is ``->``
      - ``__edges_in``  when the next hop is ``<-``

    The shared node between hop N and hop N+1 is the variable that appears on
    the right of hop N's edge — which is hop N's ``to_entity`` for ``->`` and
    ``from_entity`` for ``<-``.
    """
    if not pattern.edges:
        return []

    paths: list[dict[str, str]] = [
        {
            "edge_path": "",
            "from_path": "from_entity",
            "to_path": "to_entity",
        }
    ]

    for k in range(1, len(pattern.edges)):
        prev = paths[k - 1]
        prev_dir = pattern.edges[k - 1].direction
        cur_dir = pattern.edges[k].direction

        # Previous hop's right side — which holds the shared node between hops.
        if prev_dir == "out":
            shared = prev["to_path"]
        else:  # "in"
            shared = prev["from_path"]

        if cur_dir == "out":
            edge_path = f"{shared}__edges_out"
            from_path = shared
            to_path = f"{edge_path}__to_entity"
        else:  # "in"
            edge_path = f"{shared}__edges_in"
            to_path = shared
            from_path = f"{edge_path}__from_entity"

        paths.append(
            {
                "edge_path": edge_path,
                "from_path": from_path,
                "to_path": to_path,
            }
        )

    return paths


def _build_var_bindings(pattern: PathPattern) -> dict[str, dict[str, Any]]:
    """Map each variable in a pattern to ORM paths from the base Edge queryset.

    Each binding carries either:
      - ``role="node"`` with ``entity_path`` (path to the Edge FK that points at
        the node's Entity — e.g. ``"from_entity"``, ``"to_entity__edges_out__to_entity"``)
      - ``role="edge"`` with ``edge_path`` (path from the Edge root to the hop's
        Edge record — ``""`` for hop 0, ``"to_entity__edges_out"`` for hop 1, etc.)

    Node-only patterns (no edges) bind the lone node with ``side="lone"`` — the
    caller handles this via a domain-model scan rather than the chained Edge qs.
    """
    bindings: dict[str, dict[str, Any]] = {}

    if not pattern.edges:
        if pattern.nodes:
            n = pattern.nodes[0]
            if n.variable:
                bindings[n.variable] = {
                    "role": "node",
                    "side": "lone",
                    "label": n.label,
                }
        return bindings

    hop_paths = _compute_hop_paths(pattern)

    for hop_idx, edge in enumerate(pattern.edges):
        left = pattern.nodes[hop_idx]
        right = pattern.nodes[hop_idx + 1]
        hp = hop_paths[hop_idx]

        if edge.direction == "out":
            left_path = hp["from_path"]
            right_path = hp["to_path"]
        else:  # "in"
            left_path = hp["to_path"]
            right_path = hp["from_path"]

        if left.variable and left.variable not in bindings:
            bindings[left.variable] = {
                "role": "node",
                "entity_path": left_path,
                "label": left.label,
            }
        if right.variable and right.variable not in bindings:
            bindings[right.variable] = {
                "role": "node",
                "entity_path": right_path,
                "label": right.label,
            }
        if edge.variable and edge.variable not in bindings:
            bindings[edge.variable] = {
                "role": "edge",
                "edge_path": hp["edge_path"],
            }

    return bindings


def _orm_path_for_field(binding: dict[str, Any], field: str) -> str:
    """Build a Django ORM lookup string for a single-step ``var.field`` access.

    Handles spine-only single-step paths. Multi-step paths (the
    `data.<...>` / `display.<...>` envelope lanes) go through
    :func:`_orm_path_for_envelope_path` instead.
    """
    spine_fields = _spine_field_names()
    role = binding["role"]

    if role == "edge":
        ep = binding["edge_path"]
        prefix = f"{ep}__" if ep else ""
        if field == "entity_id":
            return f"{prefix}entity_id" if prefix else "entity_id"
        if field in spine_fields:
            return f"{prefix}entity__{field}"
        # Reserved lane-prefix names: never resolve as a spine field.
        if field in {_DATA_LANE_PREFIX, _DISPLAY_LANE_PREFIX}:
            raise SearchExecutionError(
                f"Bare `{field}` is not a complete path. Use `{field}.<...>` to " f"address the {field} lane."
            )
        # Edge model fields (edge_type, properties, batch_id, flip_map, description)
        # live in the `data` lane and require the explicit prefix.
        raise SearchExecutionError(
            f"Field {field!r} is not a spine field. If it lives on the per-edge "
            f"row (e.g. `edge_type`, `properties`), address it as "
            f"`<var>.data.{field}` per spec-grift-envelope."
        )

    # role == "node"
    # Node-only patterns bind with side="lone" and don't participate in Edge chains.
    if binding.get("side") == "lone":
        raise SearchExecutionError(
            "Node-only patterns cannot be used in predicates or RETURN paths in the advanced executor."
        )

    ep = binding["entity_path"]

    # entity_path always terminates in `from_entity` or `to_entity` (an FK on Edge).
    # Resolve entity_id via the `_id` FK column so we avoid a redundant JOIN to
    # the Entity table and sidestep the fact that Entity's primary key is `id`,
    # not `entity_id`.
    if field == "entity_id":
        return f"{ep}_id"

    if field in spine_fields:
        return f"{ep}__{field}"

    if field in {_DATA_LANE_PREFIX, _DISPLAY_LANE_PREFIX}:
        raise SearchExecutionError(
            f"Bare `{field}` is not a complete path. Use `{field}.<...>` to " f"address the {field} lane."
        )

    raise SearchExecutionError(
        f"Field {field!r} is not a spine field. If it lives on the per-model "
        f"row, address it as `<var>.data.{field}` per spec-grift-envelope."
    )


def _orm_path_for_envelope_path(binding: dict[str, Any], steps: list[Any]) -> str:
    """Build a Django ORM lookup string for an envelope-aware multi-step path.

    Per spec-grid-traversal-language § Envelope-Aware Field Paths
    (req-grid-traversal-lang-envelope-paths):

    - ``n.data.<x>...`` → join through to the per-model row and walk
      remaining steps as Django ``__``-joined lookups. Multi-step access
      into JSONField columns (e.g. ``n.data.tags.Project``) maps to
      Django's native nested JSONField lookup syntax
      (``tags__Project``).
    - ``n.display.<x>...`` → rejected; display values are computed for
      rendering, not stored. Filter via the underlying per-model fields
      instead, or use the ``extended`` return layer for display data.
    - Any other multi-step path → rejected with a message naming the
      expected envelope-lane prefix.

    The compiler only generates dot-step components when assembling the
    Django path (key-step bracket notation and wildcards stay reserved
    for the JSONPath compiler in
    ``req-grid-traversal-lang-filters-jsonpath``).
    """
    if not steps or not isinstance(steps[0], DotStep):
        raise SearchExecutionError("Multi-step field paths must start with a dot-step.")
    head = steps[0].name

    if head == _DISPLAY_LANE_PREFIX:
        raise SearchExecutionError(
            "Cannot use the `display` lane in WHERE/RETURN paths today — "
            "display values are computed for rendering, not stored. Filter on "
            "the per-model fields under `<var>.data.<x>` instead, or use the "
            "`extended` return layer when serializing for display."
        )

    # Multi-step walking into a JSON-typed spine field — today only
    # `dimensions`. Compiles to a JSONField nested-key lookup rooted on the
    # spine.
    if head in _JSON_TYPED_SPINE_FIELDS:
        rest = steps[1:]
        for step in rest:
            if not isinstance(step, DotStep) and not isinstance(step, KeyStep):
                raise SearchExecutionError("Spine JSON access supports dot-steps and bracket-key " "steps only.")
        inner_path = "__".join(s.name if isinstance(s, DotStep) else s.key for s in rest)
        role = binding["role"]
        if role == "edge":
            ep = binding["edge_path"]
            prefix = f"{ep}__" if ep else ""
            return f"{prefix}entity__{head}__{inner_path}"
        ep = binding["entity_path"]
        return f"{ep}__{head}__{inner_path}"

    if head != _DATA_LANE_PREFIX:
        raise SearchExecutionError(
            f"Unknown envelope-lane prefix {head!r}. Use a spine field "
            f"({sorted(_spine_field_names() | {'entity_id'})}), the `data` "
            f"prefix for per-model fields, `dimensions.<key>` for dimension "
            f"scoping, or `display` for computed render values (read-only)."
        )

    rest = steps[1:]
    if not rest:
        raise SearchExecutionError(
            "Path `<var>.data` requires at least one further step " "(e.g. `<var>.data.<field>`)."
        )
    for step in rest:
        if not isinstance(step, DotStep) and not isinstance(step, KeyStep):
            raise SearchExecutionError(
                "Inside the `data` lane only dot-steps and bracket-key steps "
                "are supported in v1; indexed and wildcard access via JSONPath "
                "is tracked separately (req-grid-traversal-lang-filters-jsonpath)."
            )
    inner_path = "__".join(s.name if isinstance(s, DotStep) else s.key for s in rest)

    role = binding["role"]
    if role == "edge":
        # Edges' "data" lane is the Edge model row itself — fields are
        # already on the chained Edge queryset.
        ep = binding["edge_path"]
        prefix = f"{ep}__" if ep else ""
        return f"{prefix}{inner_path}"

    # role == "node"
    if binding.get("side") == "lone":
        raise SearchExecutionError(
            "Node-only patterns cannot be used in predicates or RETURN paths in the advanced executor."
        )

    ep = binding["entity_path"]
    label = binding.get("label")
    reverse = _node_label_to_related(label)
    if reverse is None:
        raise SearchExecutionError(
            f"Cannot resolve `data.{rest[0].name}` on a variable without a "
            f"node label; add a label like `(var:entity_type)` so the "
            f"executor knows which model to traverse."
        )
    return f"{ep}__{reverse}__{inner_path}"


def _resolve_orm_path(binding: dict[str, Any], field_path: FieldPath) -> str:
    """Single entry point: translate a Gryphon FieldPath to an ORM path.

    Dispatches to :func:`_orm_path_for_field` for single-step spine paths
    or :func:`_orm_path_for_envelope_path` for multi-step envelope-lane
    paths. Per spec-grid-traversal-language § Envelope-Aware Field Paths.
    """
    steps = field_path.steps
    if not steps:
        raise SearchExecutionError("FieldPath must have at least one step.")
    if len(steps) == 1 and isinstance(steps[0], DotStep):
        return _orm_path_for_field(binding, steps[0].name)
    return _orm_path_for_envelope_path(binding, list(steps))


def _resolve_value(value: Any, inputs: dict[str, Any]) -> Any:
    """Resolve a gryphon value to a Python value (ParamRef → looked up in inputs)."""
    if isinstance(value, ParamRef):
        return inputs.get(value.name)
    return value


def _build_chain_queryset(
    pattern: PathPattern,
    db_alias: str,
    inputs: dict[str, Any] | None = None,
):
    """Build an Edge queryset that joins all hops of a (potentially multi-hop) pattern.

    The queryset is rooted at hop 0's Edge and each subsequent hop is reached
    via the shared-node reverse-FK relation (``edges_out`` / ``edges_in``). Edge
    types and endpoint labels are applied as filter conditions on their
    respective hop paths.

    All hop filters are collapsed into a single ``.filter(**kwargs)`` call so
    Django composes one JOIN per unique reverse-FK path — the standard trick
    for avoiding the "multi-filter spawns separate joins" behavior.

    Variable-length edges and undirected edges are rejected up front.
    """
    from tap_grid.models import Edge

    for edge in pattern.edges:
        if edge.min_hops != 1 or edge.max_hops != 1:
            raise SearchExecutionError(
                "Variable-length edge patterns (-[:E*m..n]->) are grammar-accepted but not "
                "supported by the executor; defer to a future iteration."
            )
        if edge.direction == "any":
            raise SearchExecutionError(
                "Undirected edge patterns are not supported by the aggregation executor; use -> or <-."
            )

    hop_paths = _compute_hop_paths(pattern)
    qs = Edge.objects.using(db_alias)

    filters: dict[str, Any] = {}

    for hop_idx, edge in enumerate(pattern.edges):
        hp = hop_paths[hop_idx]
        ep = hp["edge_path"]
        prefix = f"{ep}__" if ep else ""

        if edge.edge_type:
            filters[f"{prefix}edge_type"] = edge.edge_type

        # Inline edge-property map filter: `-[:T {key: "value"}]->` narrows the
        # queryset by JSON-key equality on Edge.properties. Per
        # req-grid-traversal-lang-filters-1; closes the silent-drop bug where
        # the parser accepted the map but the executor ignored it.
        for key, raw_value in edge.inline_props.items():
            value = _resolve_value(raw_value, inputs or {})
            filters[f"{prefix}properties__{key}"] = value

        left = pattern.nodes[hop_idx]
        right = pattern.nodes[hop_idx + 1]
        if edge.direction == "out":
            left_path, right_path = hp["from_path"], hp["to_path"]
        else:  # "in"
            left_path, right_path = hp["to_path"], hp["from_path"]

        if left.label:
            filters[f"{left_path}__entity_type"] = left.label
        if right.label:
            filters[f"{right_path}__entity_type"] = right.label

    if filters:
        qs = qs.filter(**filters)

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

    orm_path = _resolve_orm_path(bindings[var], fp)
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

    from django.db.models import F

    if len(nec.match_clause.patterns) != 1:
        raise SearchExecutionError("NOT EXISTS subqueries require exactly one pattern.")
    inner_pattern = nec.match_clause.patterns[0]
    if len(inner_pattern.edges) == 0:
        raise SearchExecutionError("NOT EXISTS subqueries require at least one edge in the inner pattern.")

    inner_bindings = _build_var_bindings(inner_pattern)
    inner_qs = _build_chain_queryset(inner_pattern, db_alias, inputs)

    # Correlation: for every variable shared between outer and inner bindings,
    # constrain the inner's ORM path to equal OuterRef of the outer's path.
    shared = set(outer_bindings.keys()) & set(inner_bindings.keys())
    if not shared:
        raise SearchExecutionError("NOT EXISTS subqueries must share at least one variable with the outer pattern.")

    # Pre-annotate outer qs with F-aliases for each shared variable's entity_id.
    # Without this, OuterRef on a multi-hop reverse-FK path (e.g. "to_entity__
    # edges_out__to_entity_id") causes Django to add a *second* JOIN rather than
    # reuse the chain's existing one — duplicating rows in the outer count.
    outer_alias_map: dict[str, str] = {}
    outer_annotations: dict[str, Any] = {}
    for var in shared:
        outer_bind = outer_bindings[var]
        outer_path = _orm_path_for_field(outer_bind, "entity_id")
        alias = f"_corr_{var}_id"
        outer_annotations[alias] = F(outer_path)
        outer_alias_map[var] = alias
    if outer_annotations:
        outer_qs = outer_qs.annotate(**outer_annotations)

    for var in shared:
        inner_bind = inner_bindings[var]
        inner_path = _orm_path_for_field(inner_bind, "entity_id")
        inner_qs = inner_qs.filter(**{inner_path: OuterRef(outer_alias_map[var])})

    # Apply the inner WHERE predicates.
    inner_qs = _apply_predicate_to_qs(
        inner_qs,
        nec.where_clause.predicate if nec.where_clause else None,
        inner_bindings,
        inputs,
    )

    return outer_qs.filter(~Exists(inner_qs))


def _is_graph_envelope_return(return_clause: ReturnClause) -> bool:
    """True when the RETURN clause requests a graph envelope rather than row projection.

    Graph envelope is requested when:
    - RETURN is omitted (items is None) — return all bound variables, or
    - all RETURN items are bare variables (ReturnItem with no field steps or aggregates).
    """
    if return_clause.items is None:
        return True
    for item in return_clause.items:
        if isinstance(item, AggregateReturnItem):
            return False
        if not isinstance(item, ReturnItem):
            return False
        if len(item.path.steps) > 0:
            return False
    return True


def _collect_graph_envelope(
    qs,
    pattern: PathPattern,
    return_clause: ReturnClause,
    bindings: dict[str, dict[str, Any]],
    *,
    layer: SubgraphLayer,
    db_alias: str,
) -> dict[str, Any]:
    """Collect a graph envelope (nodes + edges) from a multi-hop chain queryset.

    When RETURN is omitted, all bound node and edge variables are collected.
    When RETURN names bare variables, only those are collected.
    """
    # Determine which variables to collect.
    if return_clause.items is None:
        requested_vars = set(bindings.keys())
    else:
        requested_vars = {item.path.variable for item in return_clause.items if isinstance(item, ReturnItem)}

    # Partition into node and edge variables and build values_list columns.
    node_columns: list[tuple[str, str]] = []  # (var_name, orm_path)
    edge_columns: list[tuple[str, str]] = []  # (var_name, orm_path)

    for var in requested_vars:
        if var not in bindings:
            raise SearchExecutionError(f"Unknown variable '{var}' in RETURN.")
        binding = bindings[var]
        if binding["role"] == "node":
            orm_path = _orm_path_for_field(binding, "entity_id")
            node_columns.append((var, orm_path))
        elif binding["role"] == "edge":
            orm_path = _orm_path_for_field(binding, "entity_id")
            edge_columns.append((var, orm_path))

    # Also collect edges that aren't explicitly requested but connect requested
    # nodes — when RETURN is omitted, this is already covered since all variables
    # are requested. When bare-variable RETURN names only nodes, we still want
    # the connecting edges for a useful graph envelope.
    if return_clause.items is not None and not edge_columns:
        for var, binding in bindings.items():
            if binding["role"] == "edge":
                orm_path = _orm_path_for_field(binding, "entity_id")
                edge_columns.append((var, orm_path))

    all_columns = node_columns + edge_columns
    if not all_columns:
        return {"nodes": [], "edges": [], "rows": []}

    orm_paths = [path for _, path in all_columns]
    rows = qs.values_list(*orm_paths, named=False)

    # Collect distinct PKs.
    node_pks: set[str] = set()
    edge_entity_ids: set[str] = set()
    node_count = len(node_columns)

    for row in rows:
        for i, val in enumerate(row):
            if val is None:
                continue
            pk = str(val)
            if i < node_count:
                node_pks.add(pk)
            else:
                edge_entity_ids.add(pk)

    from tap_grid.models import Edge, Entity

    # Bulk-fetch entities and edges.
    # sorted() on the PK sets so the IN-list SQL is deterministic (Gridkin snapshots).
    entities = list(Entity.objects.using(db_alias).filter(pk__in=sorted(node_pks))) if node_pks else []
    edges = (
        list(Edge.objects.using(db_alias).filter(entity_id__in=sorted(edge_entity_ids)).select_related("entity"))
        if edge_entity_ids
        else []
    )

    nodes_out = _serialize_entity_nodes(entities, layer, db_alias)
    edges_out = _serialize_edge_list(edges, layer, db_alias)

    return {"nodes": nodes_out, "edges": edges_out, "rows": []}


def _filter_predicate_for_bindings(
    predicate: Predicate | None,
    bindings: dict[str, dict[str, Any]],
) -> Predicate | None:
    """Return only the parts of a predicate tree whose variables exist in bindings.

    Comparisons referencing unknown variables are dropped. AND nodes are
    reconstructed from surviving children; if both children are dropped the
    AND itself is dropped. OR and NOT predicates with unknown variables are
    dropped entirely (conservative — avoids incorrect disjunction scoping).
    """
    if predicate is None:
        return None
    if isinstance(predicate, Comparison):
        if predicate.field_path.variable in bindings:
            return predicate
        return None
    if isinstance(predicate, AndPred):
        left = _filter_predicate_for_bindings(predicate.left, bindings)
        right = _filter_predicate_for_bindings(predicate.right, bindings)
        if left is not None and right is not None:
            return AndPred(left, right)
        return left or right
    # OR / NOT with unknown variables: drop to avoid incorrect semantics.
    if isinstance(predicate, OrPred):
        left = _filter_predicate_for_bindings(predicate.left, bindings)
        right = _filter_predicate_for_bindings(predicate.right, bindings)
        if left is not None and right is not None:
            return OrPred(left, right)
        return None
    if isinstance(predicate, NotPred):
        inner = _filter_predicate_for_bindings(predicate.operand, bindings)
        if inner is not None:
            return NotPred(inner)
        return None
    return None


def _build_clause_queryset(
    mc: MatchClause,
    ast: GryphonAST,
    inputs: dict[str, Any],
    db_alias: str,
) -> tuple[Any, PathPattern, dict[str, dict[str, Any]]]:
    """Build a filtered queryset for a single advanced MATCH clause.

    WHERE predicates are filtered to include only comparisons whose variables
    exist in this clause's bindings, allowing a shared WHERE to work across
    UNION multi-hop clauses with different variable sets.

    Returns (queryset, pattern, bindings).
    """
    if len(mc.patterns) != 1:
        raise SearchExecutionError("Advanced executor requires exactly one pattern per MATCH clause.")
    pattern = mc.patterns[0]
    if len(pattern.edges) == 0:
        raise SearchExecutionError("Advanced executor requires at least one edge in the MATCH pattern.")

    bindings = _build_var_bindings(pattern)
    qs = _build_chain_queryset(pattern, db_alias, inputs)

    # Filter WHERE predicate to only include comparisons on variables bound
    # in this clause. This allows UNION queries where each MATCH clause
    # declares different variables but shares a global WHERE.
    applicable_pred = _filter_predicate_for_bindings(
        ast.where_clause.predicate if ast.where_clause else None,
        bindings,
    )
    qs = _apply_predicate_to_qs(qs, applicable_pred, bindings, inputs)

    for nec in ast.not_exists_clauses:
        qs = _apply_not_exists(qs, nec, bindings, inputs, db_alias)

    return qs, pattern, bindings


def _execute_advanced(
    ast: GryphonAST,
    inputs: dict[str, Any],
    *,
    db_alias: str,
    layer: SubgraphLayer = "full",
) -> dict[str, Any]:
    """Route through the v2 aggregation/anti-join/multi-hop path.

    Supports multiple MATCH clauses with UNION semantics in graph envelope
    mode. Row projection (field paths / aggregates) requires a single clause.
    """
    is_envelope = _is_graph_envelope_return(ast.return_clause)

    # Row projection mode requires a single MATCH clause (bindings are clause-specific).
    if not is_envelope and len(ast.match_clauses) != 1:
        raise SearchExecutionError(
            "Row projection with field paths or aggregates requires exactly one "
            "top-level MATCH clause in the advanced executor."
        )

    # --- Graph envelope with UNION across multiple MATCH clauses ---
    if is_envelope:
        from tap_grid.models import Edge, Entity

        all_node_pks: set[str] = set()
        all_edge_entity_ids: set[str] = set()

        for mc in ast.match_clauses:
            qs, pattern, bindings = _build_clause_queryset(mc, ast, inputs, db_alias)
            envelope = _collect_graph_envelope(
                qs,
                pattern,
                ast.return_clause,
                bindings,
                layer="lite",
                db_alias=db_alias,
            )
            # Collect PKs from the lite-layer results for dedup before final serialize.
            for n in envelope["nodes"]:
                all_node_pks.add(str(n["entity_id"]))
            for e in envelope["edges"]:
                all_edge_entity_ids.add(str(e["entity_id"]))

        # Bulk-fetch and serialize at the requested layer.
        # sorted() on the PK sets so the IN-list SQL is deterministic (Gridkin snapshots).
        entities = list(Entity.objects.using(db_alias).filter(pk__in=sorted(all_node_pks))) if all_node_pks else []
        edges = (
            list(
                Edge.objects.using(db_alias).filter(entity_id__in=sorted(all_edge_entity_ids)).select_related("entity")
            )
            if all_edge_entity_ids
            else []
        )

        nodes_out = _serialize_entity_nodes(entities, layer, db_alias)
        edges_out = _serialize_edge_list(edges, layer, db_alias)

        result: dict[str, Any] = {"nodes": nodes_out, "edges": edges_out, "rows": []}

        has_unanchored_multihop = (
            any(len(mc.patterns[0].edges) > 1 for mc in ast.match_clauses if len(mc.patterns) == 1)
            and ast.where_clause is None
        )
        if has_unanchored_multihop:
            result["warnings"] = {
                "multi_hop_no_anchor": (
                    "Multi-hop MATCH has no WHERE anchor; this may scan the full graph. "
                    "Add a WHERE predicate or a LIMIT for better performance."
                )
            }
        return result

    # --- Single-clause row projection / aggregation ---
    mc = ast.match_clauses[0]
    qs, pattern, bindings = _build_clause_queryset(mc, ast, inputs, db_alias)

    rows = _compute_rows(qs, ast.return_clause, bindings)

    envelope: dict[str, Any] = {"nodes": [], "edges": [], "rows": rows}

    if len(pattern.edges) > 1 and ast.where_clause is None:
        envelope["warnings"] = {
            "multi_hop_no_anchor": (
                "Multi-hop MATCH has no WHERE anchor; this may scan the full graph. "
                "Add a WHERE predicate or a LIMIT for better performance."
            )
        }

    return envelope


def _compute_rows(
    qs,
    return_clause: ReturnClause,
    bindings: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Execute the queryset and produce row dicts honoring RETURN aliases and aggregates.

    All RETURN columns are first annotated as F-aliases on the queryset, then
    referenced by alias in ``.values()`` / ``Count(...)``. This forces Django to
    reuse the JOIN aliases established by ``_build_chain_queryset`` rather than
    adding duplicate JOINs for each references — the fix for multi-hop COUNT
    inflation.
    """
    from django.db.models import Count, F

    items = return_clause.items
    if items is None:
        raise SearchExecutionError("Aggregation executor requires an explicit RETURN clause.")

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

    # Annotations are namespaced under internal aliases so user-facing RETURN
    # aliases (which may be any NAME including model-field names like `id`)
    # cannot collide with Django-internal annotation slots or model columns.
    group_by_pairs: list[tuple[str, str]] = []  # (internal_alias, user_alias)
    aggregate_pairs: list[tuple[str, str]] = []  # (internal_agg_alias, user_alias)
    annotations: dict[str, Any] = {}

    for idx, fi in enumerate(field_items):
        fp: FieldPath = fi.path
        if fp.variable not in bindings:
            raise SearchExecutionError(f"Unknown variable '{fp.variable}' in RETURN.")
        if not fp.steps or not isinstance(fp.steps[0], DotStep):
            raise SearchExecutionError("RETURN field paths must start with a dot-step.")
        orm_path = _resolve_orm_path(bindings[fp.variable], fp)
        # Last dot-step name becomes the default user-facing alias when the
        # author didn't supply an explicit AS alias.
        last_dot_step_name = fp.steps[-1].name if isinstance(fp.steps[-1], DotStep) else fp.steps[0].name
        user_alias = fi.alias or last_dot_step_name
        internal = f"_g_col_{idx}"
        annotations[internal] = F(orm_path)
        group_by_pairs.append((internal, user_alias))

    aggregate_annotations: dict[str, Any] = {}
    for idx, ai in enumerate(aggregate_items):
        agg: AggregateCall = ai.aggregate
        if agg.function != "count":
            raise SearchExecutionError(f"Unsupported aggregate function: {agg.function}")
        arg: FieldPath = agg.argument
        if arg.variable not in bindings:
            raise SearchExecutionError(f"Unknown variable '{arg.variable}' in COUNT().")
        if len(arg.steps) == 0:
            count_col = _orm_path_for_field(bindings[arg.variable], "entity_id")
        elif len(arg.steps) == 1 and isinstance(arg.steps[0], DotStep):
            count_col = _orm_path_for_field(bindings[arg.variable], arg.steps[0].name)
        else:
            raise SearchExecutionError("COUNT argument must be a bare variable or single dot-step.")
        src_alias = f"_g_count_src_{idx}"
        agg_alias = f"_g_agg_{idx}"
        annotations[src_alias] = F(count_col)
        aggregate_annotations[agg_alias] = Count(src_alias)
        aggregate_pairs.append((agg_alias, ai.alias))

    if annotations:
        qs = qs.annotate(**annotations)

    group_by_internals = [i for i, _ in group_by_pairs]

    if aggregate_annotations:
        qs = qs.values(*group_by_internals).annotate(**aggregate_annotations).order_by(*group_by_internals)
        raw_rows = list(qs)
        rows: list[dict[str, Any]] = []
        for raw in raw_rows:
            row: dict[str, Any] = {}
            for internal, user in group_by_pairs:
                val = raw.get(internal)
                row[user] = str(val) if hasattr(val, "hex") else val
            for internal, user in aggregate_pairs:
                row[user] = raw.get(internal)
            rows.append(row)
        return rows

    # No aggregation — project group-by aliases as rows.
    raw_rows = list(qs.values(*group_by_internals))
    rows = []
    for raw in raw_rows:
        row = {}
        for internal, user in group_by_pairs:
            val = raw.get(internal)
            row[user] = str(val) if hasattr(val, "hex") else val
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
            from_label=name_map.get(str(e.from_entity_id), ""),
            to_label=name_map.get(str(e.to_entity_id), ""),
        )
        for e in edges
    ]
