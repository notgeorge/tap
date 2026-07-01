"""An independent reference oracle for Gryphon, authored from the language spec.

Gryphon is a compiler: it translates a parsed AST into SQL over a Postgres
schema TAP owns. Gridkin's existing oracles (envelope + SQL snapshot) are
hand-authored expected files — and a captured expected nobody read cannot catch
a bug the executor already has (`req-gridkin-oracle-assertion`). This module is
the mechanical, authoring-independent complement: a *second* Gryphon engine that
interprets the **same parsed AST** over plain Python objects loaded from the
**same GRIFT fixture**, and whose answer is diffed against the SQL-compiled
executor's. The model IS the oracle — no per-scenario expected to hand-review.

Load-bearing discipline (do not violate):

- **Authored from the spec, never from `tap_grid/gryphon/executor.py`.** Sharing
  the AST and parser is fine — they sit upstream of the AST→SQL translation, which
  is the bug surface. Sharing one line of ORM-lowering logic would reintroduce
  common-mode failure and turn the oracle into a mirror. The semantics here come
  from `tap_grid/specs/spec-grid-traversal-language.md`.
- **Right altitude: identities and projected values, not serialization.** The
  oracle asserts *which* nodes/edges (by `entity_id`) an envelope query returns,
  and *what* rows a projection returns — the correctness claim the envelope-WHERE
  silent-drop defect violates. It does not re-check spine serialization, edge-name
  format, or version numbers; the committed envelope snapshot already pins those.
- **No silent caps.** A query shape the oracle does not yet model raises
  `OracleUnmodeled`; the runner records the skip loudly rather than fake-greening.

NULL semantics (the subtle, load-bearing part — spec regex/type-strictness §§):
the executor lowers predicates to Django `Q` → **SQL three-valued logic** for a
null *field* value, but applies a deliberate **two-valued short-circuit for a
null *literal* operand** (`x = null` compiles to a genuine-FALSE contradiction,
not UNKNOWN). So this oracle evaluates predicates in Kleene 3VL (TRUE / FALSE /
NULL) with the null-literal operand short-circuited to FALSE, and includes a row
iff the top-level predicate is TRUE. A naive "null → False at the leaf" model
would disagree with the executor under `NOT` / `OR`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from tap_grid.gryphon.ast_nodes import (
    AggregateReturnItem,
    AndPred,
    Comparison,
    DotStep,
    FieldPath,
    GryphonAST,
    InComparison,
    IsNullComparison,
    KeyStep,
    NotPred,
    ObservationComparison,
    OrPred,
    ParamRef,
    PathPattern,
    Predicate,
    ReturnItem,
)

# ---------------------------------------------------------------------------
# Unmodeled-shape signal
# ---------------------------------------------------------------------------


class OracleUnmodeled(Exception):
    """Raised when a query uses a shape the reference oracle does not yet model.

    The runner catches this and records a loud per-scenario skip — the oracle
    asserts on what it models and names what it does not, never fake-greening an
    unmodeled path (`req-gridkin`-style no-silent-caps discipline).
    """


# ---------------------------------------------------------------------------
# The in-memory graph model (built from the same GRIFT fixture the runner seeds)
# ---------------------------------------------------------------------------

# Spine fields addressable as `n.<field>` (Entity row). `dimensions` is JSON and
# may be walked into (`n.dimensions.zone`); the scalar spine fields cannot.
_SPINE_FIELDS = frozenset(
    {
        "entity_id",
        "entity_type",
        "name",
        "dimensions",
        "version",
        "deleted_at",
        "originating_grid_id",
        "created_at",
        "updated_at",
    }
)


@dataclass(frozen=True)
class NodeRecord:
    """One node: its Entity spine surface plus its per-model `data` lane."""

    entity_id: str
    entity_type: str
    name: str | None
    dimensions: dict[str, Any]
    data: dict[str, Any]
    deleted: bool


@dataclass(frozen=True)
class EdgeRecord:
    """One edge: endpoints, type, inline properties, and liveness."""

    entity_id: str
    from_id: str
    to_id: str
    edge_type: str
    properties: dict[str, Any]
    deleted: bool


@dataclass
class Graph:
    """A tiny graph over plain Python objects — the oracle's substrate.

    Built from the identical GRIFT document the runner seeds into Postgres, so
    both engines answer over the same ground truth.
    """

    nodes: dict[str, NodeRecord] = field(default_factory=dict)
    edges: list[EdgeRecord] = field(default_factory=list)

    @classmethod
    def from_grift(cls, document: dict[str, Any], soft_deleted: frozenset[str] = frozenset()) -> Graph:
        """Load a graph from a GRIFT batch document.

        `soft_deleted` is the set of entity_ids the scenario tombstones after
        import (the runner's `soft_delete` directive); those nodes/edges are
        marked deleted and excluded from results, mirroring the executor's
        `deleted_at IS NULL` filter.
        """
        graph = cls()
        for batch in document.get("batches", []):
            # The batch itself is a registered node type, so a whole-population
            # labelless `MATCH (n)` scan includes it. Load it as a node.
            batch_entity = batch.get("batch_entity")
            if batch_entity is not None:
                beid = batch_entity["entity_id"]
                graph.nodes[beid] = NodeRecord(
                    entity_id=beid,
                    entity_type=batch_entity["entity_type"],
                    name=batch_entity.get("name"),
                    dimensions=batch_entity.get("dimensions", {}) or {},
                    data=batch.get("batch_node", {}) or {},
                    deleted=beid in soft_deleted,
                )
            for raw in batch.get("nodes", []):
                entity = raw["entity"]
                data = raw.get("node", {})
                eid = entity["entity_id"]
                graph.nodes[eid] = NodeRecord(
                    entity_id=eid,
                    entity_type=entity["entity_type"],
                    name=entity.get("name"),
                    dimensions=entity.get("dimensions", {}) or {},
                    data=data,
                    deleted=eid in soft_deleted,
                )
            for raw in batch.get("edges", []):
                entity = raw["entity"]
                edge = raw["edge"]
                eid = entity["entity_id"]
                graph.edges.append(
                    EdgeRecord(
                        entity_id=eid,
                        from_id=edge["from_entity_id"],
                        to_id=edge["to_entity_id"],
                        edge_type=edge["edge_type"],
                        properties=edge.get("properties", {}) or {},
                        deleted=(
                            eid in soft_deleted
                            or edge["from_entity_id"] in soft_deleted
                            or edge["to_entity_id"] in soft_deleted
                        ),
                    )
                )
        return graph

    def live_nodes(self) -> list[NodeRecord]:
        return [n for n in self.nodes.values() if not n.deleted]

    def live_edges(self) -> list[EdgeRecord]:
        return [e for e in self.edges if not e.deleted]


# ---------------------------------------------------------------------------
# Kleene three-valued logic: TRUE / FALSE / NULL(=None)
# ---------------------------------------------------------------------------
#
# A predicate evaluates to one of True / False / None. A row is included iff the
# top-level predicate is True (`is True`). Matches SQL: NULL is not TRUE, so it
# drops from a positive filter, and propagates through NOT/OR/AND per Kleene.

_MISSING = object()  # a field/key that is absent — distinct from a stored null


def _kleene_and(a: bool | None, b: bool | None) -> bool | None:
    if a is False or b is False:
        return False
    if a is None or b is None:
        return None
    return True


def _kleene_or(a: bool | None, b: bool | None) -> bool | None:
    if a is True or b is True:
        return True
    if a is None or b is None:
        return None
    return False


def _kleene_not(a: bool | None) -> bool | None:
    if a is None:
        return None
    return not a


# ---------------------------------------------------------------------------
# Field-path resolution (lanes: spine / data / dimensions)
# ---------------------------------------------------------------------------


def _resolve_value(value: Any, inputs: dict[str, Any]) -> Any:
    """Resolve a literal or `$param` reference to a concrete Python value."""
    if isinstance(value, ParamRef):
        if value.name not in inputs:
            raise OracleUnmodeled(f"unbound param ${value.name}")
        return inputs[value.name]
    return value


def _walk_json(container: Any, steps: tuple[Any, ...]) -> Any:
    """Walk DotStep/KeyStep into a JSON container. Missing key → NULL (None).

    IndexStep / WildcardStep (array access) are not modeled yet.
    """
    current = container
    for step in steps:
        if current is None:
            return None
        if isinstance(step, (DotStep, KeyStep)):
            key = step.name if isinstance(step, DotStep) else step.key
            if not isinstance(current, dict):
                return None
            current = current.get(key, None)
        else:
            raise OracleUnmodeled("array index/wildcard field path")
    return current


def _resolve_field(field_path: FieldPath, record: NodeRecord) -> Any:
    """Resolve a node field path to its value (None == NULL/unobserved).

    Lane rules (spec `req-grid-traversal-lang-envelope-paths`):
      - `n.<spinefield>`      → Entity spine
      - `n.data.<...>`        → per-model data lane (may walk into JSON)
      - `n.dimensions.<key>`  → JSON key inside the spine `dimensions`
    """
    steps = field_path.steps
    if not steps:
        # Bare variable reference in a predicate is not a scalar; unsupported.
        raise OracleUnmodeled("bare-variable predicate operand")
    first = steps[0]
    if not isinstance(first, DotStep):
        raise OracleUnmodeled("non-dot first field step")
    head = first.name
    rest = steps[1:]

    if head == "data":
        return _walk_json(record.data, rest)
    if head == "display":
        raise OracleUnmodeled("display-lane field path")
    if head in _SPINE_FIELDS:
        if head == "entity_id":
            base: Any = record.entity_id
        elif head == "entity_type":
            base = record.entity_type
        elif head == "name":
            base = record.name
        elif head == "dimensions":
            return _walk_json(record.dimensions, rest)
        elif head == "deleted_at":
            base = None  # live records only reach here; deleted are pre-filtered
        else:
            # version / originating_grid_id / timestamps — not used in result-set
            # predicates in the corpus; refuse rather than guess.
            raise OracleUnmodeled(f"spine field predicate on {head!r}")
        if rest:
            raise OracleUnmodeled(f"cannot walk into scalar spine field {head!r}")
        return base
    # An unprefixed non-spine field is a parse-time error in the real language;
    # it should never reach a valid result scenario.
    raise OracleUnmodeled(f"unrecognized field-path head {head!r}")


# ---------------------------------------------------------------------------
# Predicate evaluation (Kleene 3VL)
# ---------------------------------------------------------------------------

_COMPARATORS = {
    "=": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b,
    ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    ">=": lambda a, b: a >= b,
}


def _eval_comparison(pred: Comparison, record: NodeRecord, inputs: dict[str, Any]) -> bool | None:
    literal = _resolve_value(pred.value, inputs)
    # Null-literal short-circuit (two-valued): `x OP null` is genuine FALSE, not
    # UNKNOWN — the deliberate divergence owned by the null short-circuit.
    if literal is None:
        return False
    value = _resolve_field(pred.field_path, record)
    if value is None:
        return None  # null field vs non-null literal → UNKNOWN (SQL 3VL)

    op = pred.op
    if op in _COMPARATORS:
        try:
            return _COMPARATORS[op](value, literal)
        except TypeError as exc:
            # Mismatched Python types (e.g. int vs str). The executor would have
            # rejected this at the type-strictness gate before running, so a
            # result scenario should never reach here.
            raise OracleUnmodeled(f"cross-type comparison {value!r} {op} {literal!r}") from exc
    if op in ("starts_with", "ends_with", "contains"):
        if not isinstance(value, str) or not isinstance(literal, str):
            raise OracleUnmodeled("string op on non-string operand")
        if op == "starts_with":
            return value.startswith(literal)
        if op == "ends_with":
            return value.endswith(literal)
        return literal in value
    if op == "regex":
        if not isinstance(value, str) or not isinstance(literal, str):
            raise OracleUnmodeled("regex op on non-string operand")
        # Search semantics (substring), Postgres POSIX. Python `re` agrees with
        # POSIX on the corpus's patterns; a genuine divergence surfaces as a
        # disagreement to investigate rather than a silent pass.
        try:
            return re.search(literal, value) is not None
        except re.error as exc:
            raise OracleUnmodeled(f"regex not expressible in Python re: {literal!r}") from exc
    raise OracleUnmodeled(f"comparison op {op!r}")


def _eval_in(pred: InComparison, record: NodeRecord, inputs: dict[str, Any]) -> bool | None:
    value = _resolve_field(pred.field_path, record)
    if value is None:
        return None  # null field → UNKNOWN
    members = [_resolve_value(v, inputs) for v in pred.values]
    for m in members:
        if m is None:
            continue  # null members are stripped (two-valued): they never match
        try:
            if value == m:
                return True
        except TypeError:
            continue
    # Non-null value, no member matched. Gryphon strips null members before
    # lowering (`field__in=[non-null...]`), so this is a genuine FALSE, not SQL's
    # NULL — the deliberate two-valued divergence (`NOT (x IN [m, null])` keeps
    # non-members). Pinned by the `in_lists` not-over-in-null-member scenario.
    return False


def eval_predicate(pred: Predicate | None, record: NodeRecord, inputs: dict[str, Any]) -> bool | None:
    """Evaluate a WHERE predicate over one bound node in Kleene 3VL."""
    if pred is None:
        return True
    if isinstance(pred, Comparison):
        return _eval_comparison(pred, record, inputs)
    if isinstance(pred, InComparison):
        return _eval_in(pred, record, inputs)
    if isinstance(pred, IsNullComparison):
        is_null = _resolve_field(pred.field_path, record) is None
        return (not is_null) if pred.negated else is_null
    if isinstance(pred, ObservationComparison):
        is_null = _resolve_field(pred.field_path, record) is None
        return is_null if pred.kind == "unknown" else (not is_null)
    if isinstance(pred, AndPred):
        return _kleene_and(eval_predicate(pred.left, record, inputs), eval_predicate(pred.right, record, inputs))
    if isinstance(pred, OrPred):
        return _kleene_or(eval_predicate(pred.left, record, inputs), eval_predicate(pred.right, record, inputs))
    if isinstance(pred, NotPred):
        return _kleene_not(eval_predicate(pred.operand, record, inputs))
    raise OracleUnmodeled(f"predicate leaf {type(pred).__name__}")


# ---------------------------------------------------------------------------
# Predicate variable scoping (mirrors the executor's per-clause WHERE filter)
# ---------------------------------------------------------------------------


def _predicate_vars(pred: Predicate | None) -> set[str]:
    """Collect every variable a predicate references."""
    if pred is None:
        return set()
    if isinstance(pred, (Comparison, InComparison, IsNullComparison, ObservationComparison)):
        return {pred.field_path.variable}
    if isinstance(pred, (AndPred, OrPred)):
        return _predicate_vars(pred.left) | _predicate_vars(pred.right)
    if isinstance(pred, NotPred):
        return _predicate_vars(pred.operand)
    return set()


def _multi_var_predicate(pred: Predicate | None) -> bool:
    """True if the predicate spans more than one variable (needs a joint binding)."""
    return len(_predicate_vars(pred)) > 1


# ---------------------------------------------------------------------------
# Binding enumeration over a single PathPattern
# ---------------------------------------------------------------------------

Binding = dict[str, NodeRecord]  # node-variable → record (plus __edges__ side channel)


@dataclass
class PatternMatch:
    """One realized pattern instance: the node/edge records it touched."""

    node_vars: dict[str, NodeRecord]
    node_ids: list[str]
    edge_ids: list[str]
    edge_records: list[EdgeRecord]


def _node_matches(node_pat: Any, record: NodeRecord, inputs: dict[str, Any]) -> bool:
    if node_pat.label is not None and record.entity_type != node_pat.label:
        return False
    for key, raw in node_pat.inline_props.items():
        want = _resolve_value(raw, inputs)
        # Inline props filter spine `name` / `entity_type` or data-lane fields;
        # the corpus uses them rarely. Resolve against spine then data.
        if key in _SPINE_FIELDS:
            have = getattr(record, key, None) if key != "dimensions" else record.dimensions
        else:
            have = record.data.get(key, None)
        if have != want:
            return False
    return True


def _edge_matches(edge_pat: Any, edge: EdgeRecord, inputs: dict[str, Any]) -> bool:
    if edge_pat.edge_type is not None and edge.edge_type != edge_pat.edge_type:
        return False
    for key, raw in edge_pat.inline_props.items():
        if edge.properties.get(key, None) != _resolve_value(raw, inputs):
            return False
    return True


def _enumerate_pattern(pattern: PathPattern, graph: Graph, inputs: dict[str, Any]) -> list[PatternMatch]:
    """Enumerate every realized instance of a path pattern over the graph.

    Handles node-only patterns (type scan / bare labelless scan) and single- or
    multi-hop chains with directed / undirected edges. Bounded repetition
    (`*min..max`) is not modeled (v0 executor rejects it too).
    """
    for edge_pat in pattern.edges:
        if edge_pat.min_hops != 1 or edge_pat.max_hops != 1:
            raise OracleUnmodeled("bounded multi-hop traversal")

    nodes = pattern.nodes
    edges = pattern.edges

    # Seed: every live node matching nodes[0].
    matches: list[PatternMatch] = []
    for record in graph.live_nodes():
        if not _node_matches(nodes[0], record, inputs):
            continue
        node_vars = {nodes[0].variable: record} if nodes[0].variable else {}
        matches.append(
            PatternMatch(node_vars=dict(node_vars), node_ids=[record.entity_id], edge_ids=[], edge_records=[])
        )

    # Extend hop by hop.
    live_by_id = {n.entity_id: n for n in graph.live_nodes()}
    for hop, edge_pat in enumerate(edges):
        next_node_pat = nodes[hop + 1]
        extended: list[PatternMatch] = []
        for m in matches:
            cur_id = m.node_ids[-1]
            for edge in graph.live_edges():
                if not _edge_matches(edge_pat, edge, inputs):
                    continue
                direction = edge_pat.direction
                if direction == "out" and edge.from_id == cur_id:
                    other_id = edge.to_id
                elif direction == "in" and edge.to_id == cur_id:
                    other_id = edge.from_id
                elif direction == "any" and cur_id in (edge.from_id, edge.to_id):
                    other_id = edge.to_id if edge.from_id == cur_id else edge.from_id
                else:
                    continue
                other = live_by_id.get(other_id)
                if other is None or not _node_matches(next_node_pat, other, inputs):
                    continue
                new_vars = dict(m.node_vars)
                if next_node_pat.variable:
                    new_vars[next_node_pat.variable] = other
                extended.append(
                    PatternMatch(
                        node_vars=new_vars,
                        node_ids=[*m.node_ids, other_id],
                        edge_ids=[*m.edge_ids, edge.entity_id],
                        edge_records=[*m.edge_records, edge],
                    )
                )
        matches = extended
    return matches


# ---------------------------------------------------------------------------
# WHERE application over enumerated matches
# ---------------------------------------------------------------------------


def _passes_where(match: PatternMatch, predicate: Predicate | None, inputs: dict[str, Any]) -> bool:
    """Apply the WHERE (scoped to this match's bound vars) in 3VL; include iff TRUE.

    A predicate leaf whose variable is not bound by this match is not applied
    (mirrors the executor's `_filter_predicate_for_bindings`). A single-variable
    predicate is evaluated on that variable's record. A predicate that jointly
    spans multiple bound variables is evaluated by requiring TRUE on each of its
    single-variable projections' records — supported only for AND-composed
    per-variable leaves (the corpus's two-node-AND shape).
    """
    if predicate is None:
        return True
    result = _eval_scoped(predicate, match, inputs)
    return result is True


def _eval_scoped(pred: Predicate | None, match: PatternMatch, inputs: dict[str, Any]) -> bool | None:
    """Kleene-evaluate a predicate against a multi-variable match.

    Each leaf resolves against the record of the variable it references. A leaf
    referencing an unbound variable is treated as TRUE (not applied, per
    per-clause scoping).
    """
    if pred is None:
        return True
    if isinstance(pred, (Comparison, InComparison, IsNullComparison, ObservationComparison)):
        var = pred.field_path.variable
        record = match.node_vars.get(var)
        if record is None:
            return True  # variable not bound here → leaf not applied
        return eval_predicate(pred, record, inputs)
    if isinstance(pred, AndPred):
        return _kleene_and(_eval_scoped(pred.left, match, inputs), _eval_scoped(pred.right, match, inputs))
    if isinstance(pred, OrPred):
        return _kleene_or(_eval_scoped(pred.left, match, inputs), _eval_scoped(pred.right, match, inputs))
    if isinstance(pred, NotPred):
        return _kleene_not(_eval_scoped(pred.operand, match, inputs))
    raise OracleUnmodeled(f"predicate leaf {type(pred).__name__}")


# ---------------------------------------------------------------------------
# Top-level evaluation
# ---------------------------------------------------------------------------


@dataclass
class OracleResult:
    """The oracle's answer: either an envelope identity set or projected rows."""

    kind: str  # "envelope" | "rows"
    node_ids: frozenset[str] = frozenset()
    edge_ids: frozenset[str] = frozenset()
    rows: tuple[dict[str, Any], ...] = ()


def evaluate(ast: GryphonAST, graph: Graph, inputs: dict[str, Any]) -> OracleResult:
    """Evaluate a parsed Gryphon query over the in-memory graph.

    Raises `OracleUnmodeled` for any shape not yet modeled (OPTIONAL MATCH,
    NOT EXISTS, bounded multi-hop, display lane, array field paths, multi-MATCH
    composition, bare-variable RETURN, aggregates other than COUNT).
    """
    if ast.optional_match_clauses:
        raise OracleUnmodeled("OPTIONAL MATCH")
    if ast.not_exists_clauses:
        raise OracleUnmodeled("NOT EXISTS")
    if len(ast.match_clauses) != 1:
        raise OracleUnmodeled("multiple MATCH clauses")
    match_clause = ast.match_clauses[0]
    if len(match_clause.patterns) != 1:
        raise OracleUnmodeled("multiple patterns in one MATCH")

    # LIMIT with a positive cap but no ORDER BY: the specific subset returned is
    # the executor's arbitrary-but-deterministic default order — an
    # implementation detail, not a spec-defined result. Refuse to guess it (a
    # LIMIT 0 is always the empty set, which IS deterministic — model that).
    if ast.limit is not None and ast.limit.count > 0 and ast.order_by is None:
        raise OracleUnmodeled("LIMIT without ORDER BY (executor-order-dependent subset)")

    pattern = match_clause.patterns[0]
    predicate = ast.where_clause.predicate if ast.where_clause else None

    matches = _enumerate_pattern(pattern, graph, inputs)
    matches = [m for m in matches if _passes_where(m, predicate, inputs)]

    if ast.return_clause.items is None:
        return _build_envelope(ast, pattern, matches)
    return _build_rows(ast, matches, inputs)


def _build_envelope(ast: GryphonAST, pattern: PathPattern, matches: list[PatternMatch]) -> OracleResult:
    # ORDER BY / LIMIT on an envelope apply only to a node-only (type-scan)
    # pattern; the executor rejects them on single-hop graph-traversal patterns.
    if (ast.order_by is not None or ast.limit is not None) and len(pattern.edges) == 0:
        ordered = _order_limit_envelope(ast, matches)
        return OracleResult(
            kind="envelope",
            node_ids=frozenset(m.node_ids[0] for m in ordered),
            edge_ids=frozenset(),
        )

    node_ids: set[str] = set()
    edge_ids: set[str] = set()
    for m in matches:
        node_ids.update(m.node_ids)
        edge_ids.update(m.edge_ids)
    return OracleResult(kind="envelope", node_ids=frozenset(node_ids), edge_ids=frozenset(edge_ids))


def _order_limit_envelope(ast: GryphonAST, matches: list[PatternMatch]) -> list[PatternMatch]:
    """Order + limit a node-only envelope's matched nodes.

    ORDER BY terms carry full field paths in envelope mode; resolve each against
    the matched node. NULL ordering mirrors Postgres native (NULLS LAST under
    ASC, FIRST under DESC — `_sort_key`). Ties break by entity_id ascending, the
    executor's deterministic default.
    """
    result = sorted(matches, key=lambda m: m.node_ids[0])  # deterministic tiebreak
    if ast.order_by is not None:
        for term in reversed(ast.order_by.items):
            result = sorted(
                result,
                key=lambda m, t=term: _sort_key(_resolve_field(t.path, _only_node(m))),
                reverse=term.descending,
            )
    if ast.limit is not None:
        result = result[: ast.limit.count]
    return result


def _only_node(match: PatternMatch) -> NodeRecord:
    """The single node record of a node-only match (for envelope ordering)."""
    return next(iter(match.node_vars.values()))


def _return_key(item: ReturnItem) -> str:
    if item.alias:
        return item.alias
    steps = item.path.steps
    if steps and isinstance(steps[-1], DotStep):
        return steps[-1].name
    return item.path.variable


def _build_rows(ast: GryphonAST, matches: list[PatternMatch], inputs: dict[str, Any]) -> OracleResult:
    items = ast.return_clause.items
    assert items is not None
    has_aggregate = any(isinstance(it, AggregateReturnItem) for it in items)

    if has_aggregate:
        rows = _build_aggregate_rows(items, matches)
    else:
        rows = []
        for m in matches:
            row: dict[str, Any] = {}
            for it in items:
                if isinstance(it, AggregateReturnItem):
                    raise OracleUnmodeled("mixed aggregate/non-aggregate without grouping")
                row[_return_key(it)] = _project_field(it, m)
            rows.append(row)

    rows = _apply_order_and_limit(ast, rows)
    return OracleResult(kind="rows", rows=tuple(rows))


def _project_field(item: ReturnItem, match: PatternMatch) -> Any:
    steps = item.path.steps
    var = item.path.variable
    record = match.node_vars.get(var)
    if record is None:
        raise OracleUnmodeled(f"RETURN references unbound/edge variable {var!r}")
    if not steps:
        raise OracleUnmodeled("bare-variable RETURN projection")
    return _resolve_field(item.path, record)


def _build_aggregate_rows(items: tuple[Any, ...], matches: list[PatternMatch]) -> list[dict[str, Any]]:
    group_items = [it for it in items if isinstance(it, ReturnItem)]
    agg_items = [it for it in items if isinstance(it, AggregateReturnItem)]
    for agg in agg_items:
        if agg.aggregate.function != "count":
            raise OracleUnmodeled(f"aggregate function {agg.aggregate.function!r}")

    groups: dict[tuple, dict[str, Any]] = {}
    counts: dict[tuple, int] = {}
    order: list[tuple] = []
    for m in matches:
        key_parts = tuple(_project_field(gi, m) for gi in group_items)
        if key_parts not in groups:
            groups[key_parts] = {_return_key(gi): _project_field(gi, m) for gi in group_items}
            counts[key_parts] = 0
            order.append(key_parts)
        # COUNT counts bindings in the group (inner-join chain: the counted
        # variable is always bound). Zero-degree groups never appear — they
        # produce no binding — which matches the executor's INNER JOIN.
        counts[key_parts] += 1

    rows: list[dict[str, Any]] = []
    for key in order:
        row = dict(groups[key])
        for agg in agg_items:
            row[agg.alias] = counts[key]
        rows.append(row)
    return rows


def _apply_order_and_limit(ast: GryphonAST, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if ast.order_by is not None:
        for term in reversed(ast.order_by.items):
            key = term.key
            rows = sorted(rows, key=lambda r, k=key: _sort_key(r.get(k)), reverse=term.descending)
    if ast.limit is not None:
        rows = rows[: ast.limit.count]
    return rows


def _sort_key(value: Any) -> tuple[int, Any]:
    """Sort helper: NULLs last under ASC (tuple ordering puts them after values)."""
    if value is None:
        return (1, "")
    return (0, value)
