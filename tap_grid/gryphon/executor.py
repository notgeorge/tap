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
        return _execute_advanced(ast, inputs, db_alias=db_alias, layer=layer)

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

    paths: list[dict[str, str]] = [{
        "edge_path": "",
        "from_path": "from_entity",
        "to_path": "to_entity",
    }]

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

        paths.append({
            "edge_path": edge_path,
            "from_path": from_path,
            "to_path": to_path,
        })

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
    """Build the Django ORM lookup string for ``var.field`` against the chained Edge queryset."""
    role = binding["role"]

    if role == "edge":
        ep = binding["edge_path"]
        prefix = f"{ep}__" if ep else ""
        if field == "entity_id":
            return f"{prefix}entity_id" if prefix else "entity_id"
        if field in _ENTITY_LEVEL_FIELDS:
            return f"{prefix}entity__{field}"
        # Custom edge fields like edge_type, properties.
        return f"{prefix}{field}" if prefix else field

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

    if field in _ENTITY_LEVEL_FIELDS:
        return f"{ep}__{field}"

    # Domain-model field: traverse {ep}__<reverse_name>__<field>.
    label = binding.get("label")
    reverse = _node_label_to_related(label)
    if reverse is None:
        raise SearchExecutionError(
            f"Cannot resolve '{field}' on variable without a node label; add a label like "
            f"`(var:entity_type)` so the executor knows which model to traverse."
        )
    return f"{ep}__{reverse}__{field}"


def _resolve_value(value: Any, inputs: dict[str, Any]) -> Any:
    """Resolve a gryphon value to a Python value (ParamRef → looked up in inputs)."""
    if isinstance(value, ParamRef):
        return inputs.get(value.name)
    return value


def _build_chain_queryset(
    pattern: PathPattern,
    db_alias: str,
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

    from django.db.models import F

    if len(nec.match_clause.patterns) != 1:
        raise SearchExecutionError("NOT EXISTS subqueries require exactly one pattern.")
    inner_pattern = nec.match_clause.patterns[0]
    if len(inner_pattern.edges) == 0:
        raise SearchExecutionError(
            "NOT EXISTS subqueries require at least one edge in the inner pattern."
        )

    inner_bindings = _build_var_bindings(inner_pattern)
    inner_qs = _build_chain_queryset(inner_pattern, db_alias)

    # Correlation: for every variable shared between outer and inner bindings,
    # constrain the inner's ORM path to equal OuterRef of the outer's path.
    shared = set(outer_bindings.keys()) & set(inner_bindings.keys())
    if not shared:
        raise SearchExecutionError(
            "NOT EXISTS subqueries must share at least one variable with the outer pattern."
        )

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
    entities = list(Entity.objects.using(db_alias).filter(pk__in=node_pks)) if node_pks else []
    edges = (
        list(
            Edge.objects.using(db_alias)
            .filter(entity_id__in=edge_entity_ids)
            .select_related("entity")
        )
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
        raise SearchExecutionError(
            "Advanced executor requires exactly one pattern per MATCH clause."
        )
    pattern = mc.patterns[0]
    if len(pattern.edges) == 0:
        raise SearchExecutionError(
            "Advanced executor requires at least one edge in the MATCH pattern."
        )

    bindings = _build_var_bindings(pattern)
    qs = _build_chain_queryset(pattern, db_alias)

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
                qs, pattern, ast.return_clause, bindings, layer="lite", db_alias=db_alias,
            )
            # Collect PKs from the lite-layer results for dedup before final serialize.
            for n in envelope["nodes"]:
                all_node_pks.add(str(n["entity_id"]))
            for e in envelope["edges"]:
                all_edge_entity_ids.add(str(e["entity_id"]))

        # Bulk-fetch and serialize at the requested layer.
        entities = list(Entity.objects.using(db_alias).filter(pk__in=all_node_pks)) if all_node_pks else []
        edges = (
            list(
                Edge.objects.using(db_alias)
                .filter(entity_id__in=all_edge_entity_ids)
                .select_related("entity")
            )
            if all_edge_entity_ids
            else []
        )

        nodes_out = _serialize_entity_nodes(entities, layer, db_alias)
        edges_out = _serialize_edge_list(edges, layer, db_alias)

        result: dict[str, Any] = {"nodes": nodes_out, "edges": edges_out, "rows": []}

        has_unanchored_multihop = any(
            len(mc.patterns[0].edges) > 1
            for mc in ast.match_clauses
            if len(mc.patterns) == 1
        ) and ast.where_clause is None
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
        if len(fp.steps) != 1 or not isinstance(fp.steps[0], DotStep):
            raise SearchExecutionError("RETURN field paths support single dot-step only in v1.")
        field_name = fp.steps[0].name
        orm_path = _orm_path_for_field(bindings[fp.variable], field_name)
        user_alias = fi.alias or field_name
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
            from_name=name_map.get(str(e.from_entity_id), ""),
            to_name=name_map.get(str(e.to_entity_id), ""),
        )
        for e in edges
    ]
