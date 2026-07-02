"""Differential property fuzzer for Gryphon — the capstone rung of the ladder.

The model oracle (`req-gridkin-oracle-assertion`, `model_oracle.py`) is a second
Gryphon engine that recomputes a query's answer over plain Python objects with
**zero lowering shared** with the SQL-compiling executor. Gridkin wires it as a
per-scenario differential over the *authored* corpus. This module removes the
"authored" restriction: it is a **seedable generator** that emits a random small
GRIFT graph over the playground types and a random VALID query over the oracle's
modeled surface, runs both engines, and asserts they agree. The oracle IS the
differential harness — only the generator was missing, and this is it.

Load-bearing discipline (the whole guarantee rests on it):

- **Zero shared lowering, still.** The generator and the oracle are authored from
  the language spec / grammar; neither imports a line of `executor.py` ORM
  lowering. Two independent implementations grinding on random input is the
  entire source of the differential signal.
- **Generate WITHIN the modeled surface, skip the rest loudly.** Every query the
  generator emits is well-typed (severity_score/int, is_open/bool,
  kind·name·description/string, observed_at/null-predicates only — matching
  `_declared_data_types` so the type-strictness gate never rejects a generated
  query) and stays inside the shapes the oracle models. If a case still hits
  `OracleUnmodeled` it is recorded as an honest skip, never a fake green. The one
  permanent oracle skip — `LIMIT` without `ORDER BY` — is never generated (LIMIT
  is only emitted alongside an ORDER BY, or as the always-empty `LIMIT 0`).
- **Bind to real data.** Literals are sampled from the values actually present in
  the seeded graph, so filters partition the graph (meaningful differentials)
  rather than trivially returning empty. Nulls are produced deliberately — both
  the 2VL null *literal* operand (`field OP null`, genuine FALSE) and the 3VL
  null *field* (an unobserved `observed_at`, SQL three-valued logic) — because the
  2VL/3VL boundary is where Gryphon's null risk concentrates.
- **Replayable from the seed alone.** All randomness (graph shape, field values,
  entity UUIDs, query shape) flows from one `random.Random(graph_seed)` stream, so
  a divergence prints the seed + the emitted GRIFT + the query + both results and
  is reproducible with nothing but the seed. UUIDs are drawn from the seeded RNG
  (never `uuid4()`), so replay is bit-exact.
- **Production seeding.** The graph is imported through the real `grift_import`
  path with the same error discipline `gridkin/runner.py::_seed_fixture` uses, so
  the fuzzer exercises production seeding, not a test-only shortcut.

See `plugins/gryphon_playground/specs/spec-gridkin-v0.md`
(`req-gridkin-property-fuzz`) and `docs/misc/doc-gryphon-testing-philosophy.md`
("The frontier").
"""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import dataclass
from typing import Any

from plugins.gryphon_playground.gridkin.model_oracle import Graph, OracleUnmodeled, evaluate
from plugins.gryphon_playground.gridkin.runner import _oracle_agrees
from tap_grid.exceptions import SearchExecutionError
from tap_grid.grift import grift_import
from tap_grid.gryphon import explain_gryphon_raw
from tap_grid.gryphon.parser import parse_gryphon

# ---------------------------------------------------------------------------
# The generator's alphabet — the registered playground surface
# ---------------------------------------------------------------------------
#
# All four pg_* types carry the identical FIELD_CRUD_SCHEMA, so any of them is a
# valid, type-uniform target; drawing from several exercises type-scan
# selectivity (a scan of one type must exclude the others). Edges are the two
# wildcard-endpoint playground edge types, so any topology is importable.
_LABELS = (
    "gryphon_playground__pg_node",
    "gryphon_playground__pg_hub",
    "gryphon_playground__pg_leaf",
)
_EDGE_TYPES = (
    "PG_LINKS__gryphon_playground",
    "PG_OPTIONAL__gryphon_playground",
)

# Small, low-cardinality value pools so a random equality/`IN`/comparison filter
# actually partitions the graph instead of matching all-or-nothing. `kind` and
# `description` include "" (the observed-empty value) alongside real values.
_NAMES = ("Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta")
_KINDS = ("root", "mid", "tail", "iso", "")
_DESCRIPTIONS = ("primary", "secondary", "edge-case", "")
_SEVERITIES = (0, 5, 10, 15, 20, 30)
# ISO-8601 UTC timestamps: their lexicographic order equals their chronological
# order, so the oracle's string sort and Postgres's datetime sort agree — which
# is what makes ORDER BY over `observed_at` a safe (still null-exercising) shape.
_TIMES = ("2026-05-21T08:00:00Z", "2026-05-22T09:00:00Z", "2026-05-23T10:00:00Z")


def _uuid(rng: random.Random) -> str:
    """A valid UUID string drawn deterministically from the seeded RNG.

    `grift_import` accepts any RFC-4122 UUID (any version); using the RNG rather
    than `uuid.uuid4()` keeps every generated fixture bit-exactly replayable from
    the graph seed alone.
    """
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


# ---------------------------------------------------------------------------
# Graph generation — a random small GRIFT batch over the playground types
# ---------------------------------------------------------------------------


def _gen_node(rng: random.Random) -> dict[str, Any]:
    """One random node envelope. All data-lane fields are written explicitly.

    Every field is emitted (never omitted) so the executor's column value and the
    oracle's `data` dict never disagree via a model default — the ONLY field that
    is ever null is `observed_at` (the sole nullable column), and it is set to a
    genuine JSON `null` roughly a third of the time to exercise 3VL null-field
    logic.
    """
    name = rng.choice(_NAMES)
    observed = rng.choice((*_TIMES, None, None))  # ~1/3 null → 3VL field-null
    return {
        "entity": {
            "entity_id": _uuid(rng),
            "entity_type": rng.choice(_LABELS),
            "name": name,
            "dimensions": {"tap.playground": "gridkin"},
        },
        "node": {
            "name": name,
            "description": rng.choice(_DESCRIPTIONS),
            "kind": rng.choice(_KINDS),
            "severity_score": rng.choice(_SEVERITIES),
            "is_open": rng.choice((True, False)),
            "observed_at": observed,
            "tags": {},
        },
    }


def _gen_edge(rng: random.Random, node_ids: list[str]) -> dict[str, Any]:
    """One random directed edge between two (possibly identical) node ids."""
    return {
        "entity": {
            "entity_id": _uuid(rng),
            "entity_type": "edge",
            "name": "fuzz edge",
            "dimensions": {"tap.playground": "gridkin"},
        },
        "edge": {
            "from_entity_id": rng.choice(node_ids),
            "to_entity_id": rng.choice(node_ids),
            "edge_type": rng.choice(_EDGE_TYPES),
            "properties": {},
        },
    }


def _gen_graph(rng: random.Random) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Generate a random GRIFT document plus its node envelopes.

    3–8 nodes, 0–(n+2) edges (allowing self-loops and multi-edges, the topology
    the playground types are unconstrained to permit). Returns the document and
    the node list (the latter feeds value sampling for the query generator).
    """
    n = rng.randint(3, 8)
    nodes = [_gen_node(rng) for _ in range(n)]
    node_ids = [nd["entity"]["entity_id"] for nd in nodes]
    m = rng.randint(0, n + 2)
    edges = [_gen_edge(rng, node_ids) for _ in range(m)]
    document = {
        "metadata": {"grift_version": "0"},
        "_reserved": {},
        "batches": [
            {
                "batch_entity": {
                    "entity_id": _uuid(rng),
                    "entity_type": "batch",
                    "name": "Gryphon fuzz batch",
                    "dimensions": {},
                },
                "batch_node": {
                    "name": "Gryphon fuzz batch",
                    "description": "Generated by the differential property fuzzer.",
                    "source": "plugin:gryphon_playground",
                },
                "nodes": nodes,
                "edges": edges,
            }
        ],
    }
    return document, nodes


# ---------------------------------------------------------------------------
# Value sampling — literals drawn from the graph so filters bind to real rows
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Values:
    """Real values present in the seeded graph, for binding query literals."""

    kinds: tuple[str, ...]
    descriptions: tuple[str, ...]
    names: tuple[str, ...]
    severities: tuple[int, ...]


def _sample_values(nodes: list[dict[str, Any]]) -> _Values:
    def _col(key: str) -> tuple[Any, ...]:
        seen = {nd["node"][key] for nd in nodes}
        return tuple(sorted(seen, key=lambda v: (v is None, v)))

    return _Values(
        kinds=_col("kind") or _KINDS,
        descriptions=_col("description") or _DESCRIPTIONS,
        names=_col("name") or _NAMES,
        severities=_col("severity_score") or _SEVERITIES,
    )


def _q(text: str) -> str:
    """Render a Python string as a Gryphon double-quoted string literal."""
    return json.dumps(text)


# ---------------------------------------------------------------------------
# Predicate generation — the WHERE surface, well-typed by construction
# ---------------------------------------------------------------------------
#
# Each leaf targets a data-lane field with an operator/literal its declared type
# admits, so `_enforce_type_strictness` never rejects a generated query:
#   severity_score (integer)  → =,!=,<,>,<=,>= with an int literal (or null=2VL); IN of ints
#   is_open        (boolean)  → =,!= with true/false (or null=2VL)
#   kind/description/name (string) → =,!= (NOT <,> — string collation would
#                              diverge from Python codepoint order), text ops
#                              STARTS_WITH/ENDS_WITH/CONTAINS, =~ regex; IN of strings
#   observed_at    (date-time, nullable) → IS NULL / IS NOT NULL / IS KNOWN /
#                              IS UNKNOWN only (value comparisons would risk
#                              datetime/string coercion + collation surprises)

_NUMERIC_OPS = ("=", "!=", "<", ">", "<=", ">=")
_TEXT_OPS = ("STARTS_WITH", "ENDS_WITH", "CONTAINS")


# A far node (beyond the root edge) bans `!=`: it lowers to `~Q` over the
# reverse-FK path, an executor-rejected shape (`_guard_negated_far_predicate`).
_NUMERIC_OPS_POSITIVE = ("=", "<", ">", "<=", ">=")


def _leaf_severity(rng: random.Random, var: str, vals: _Values, *, far: bool = False) -> str:
    op = rng.choice(_NUMERIC_OPS_POSITIVE if far else _NUMERIC_OPS)
    if rng.random() < 0.12:
        return f"{var}.data.severity_score {op} null"  # 2VL null-literal operand
    lit = rng.choice(vals.severities)
    if rng.random() < 0.4:  # nudge off a real value to probe the boundary
        lit += rng.choice((-1, 1))
    return f"{var}.data.severity_score {op} {lit}"


def _leaf_string(rng: random.Random, var: str, vals: _Values, *, far: bool = False) -> str:
    fieldname, pool = rng.choice((("kind", vals.kinds), ("description", vals.descriptions), ("name", vals.names)))
    path = f"{var}.data.{fieldname}"
    roll = rng.random()
    if roll < 0.1:
        return f"{path} = null"  # 2VL null-literal operand
    if roll < 0.55:
        op = "=" if far else rng.choice(("=", "!="))
        return f"{path} {op} {_q(rng.choice(pool))}"
    if roll < 0.85:
        op = rng.choice(_TEXT_OPS)
        sample = rng.choice(pool)
        # A prefix/suffix/substring of a real value (or the whole value) so the
        # match can succeed; an empty needle (from "") matches every string.
        needle = sample[: rng.randint(0, len(sample))] if sample else ""
        return f"{path} {op} {_q(needle)}"
    # regex search: a literal fragment of a real value (metacharacter-free), so
    # Python `re` and Postgres POSIX agree.
    sample = rng.choice(pool) or ""
    frag = sample[: rng.randint(1, len(sample))] if sample else ""
    return f"{path} =~ {_q(frag)}"


def _leaf_bool(rng: random.Random, var: str, _vals: _Values, *, far: bool = False) -> str:
    if rng.random() < 0.1:
        return f"{var}.data.is_open = null"  # 2VL null-literal operand
    return f"{var}.data.is_open = {rng.choice(('true', 'false'))}"


def _leaf_in(rng: random.Random, var: str, vals: _Values, *, far: bool = False) -> str:
    if rng.random() < 0.5:
        members = [str(m) for m in rng.sample(vals.severities, rng.randint(1, min(3, len(vals.severities))))]
        path = f"{var}.data.severity_score"
    else:
        members = [_q(m) for m in rng.sample(vals.kinds, rng.randint(1, min(3, len(vals.kinds))))]
        path = f"{var}.data.kind"
    if rng.random() < 0.25:
        members.append("null")  # a null member never matches (two-valued strip)
    rng.shuffle(members)
    return f"{path} IN [{', '.join(members)}]"


def _leaf_observation(rng: random.Random, var: str, _vals: _Values, *, far: bool = False) -> str:
    return f"{var}.data.observed_at " + rng.choice(("IS NULL", "IS NOT NULL", "IS KNOWN", "IS UNKNOWN"))


_LEAF_GENERATORS = (
    _leaf_severity,
    _leaf_string,
    _leaf_bool,
    _leaf_in,
    _leaf_observation,
)


def _gen_predicate(rng: random.Random, var: str, vals: _Values, depth: int = 0, *, far: bool = False) -> str:
    """A random single-variable predicate tree (AND / OR / NOT over typed leaves).

    ``far=True`` marks a node BEYOND the root edge of a multi-hop chain and keeps
    the tree to the executor-supported far-node surface: no ``NOT`` and no ``!=``.
    Both lower to a negation over the far node's reverse-FK path — an
    executor-rejected shape (it would compile to an existential anti-join with
    per-pattern, not per-binding, semantics — see `_guard_negated_far_predicate`).
    The positive / ``OR`` / ``IN`` / ``IS NULL`` / text / regex far-node forms are
    all still emitted, so far-node WHERE stays well-exercised.
    """
    ops = ("AND", "OR") if far else ("AND", "OR", "NOT")
    if depth >= 2 or rng.random() < 0.5:
        return rng.choice(_LEAF_GENERATORS)(rng, var, vals, far=far)
    op = rng.choice(ops)
    if op == "NOT":
        return f"NOT ({_gen_predicate(rng, var, vals, depth + 1, far=far)})"
    left = _gen_predicate(rng, var, vals, depth + 1, far=far)
    right = _gen_predicate(rng, var, vals, depth + 1, far=far)
    return f"({left}) {op} ({right})"


# ---------------------------------------------------------------------------
# Query generation — three families over the oracle's modeled surface
# ---------------------------------------------------------------------------

# (field-path suffix, alias stem) — the alias is qualified with the variable so a
# multi-variable RETURN never emits two columns under the same alias (a duplicate
# output alias is a malformed query the two engines resolve differently: the
# oracle last-wins, the executor returns nothing).
_PROJECTABLE = (
    ("data.kind", "kind"),
    ("data.severity_score", "sev"),
    ("data.name", "nm"),
    ("data.description", "descr"),
    ("data.is_open", "op"),
    ("entity_id", "eid"),
)


def _projection(rng: random.Random, var: str) -> str:
    picks = rng.sample(_PROJECTABLE, rng.randint(1, 3))
    return ", ".join(f"{var}.{suffix} AS {var}_{stem}" for suffix, stem in picks)


def _gen_typescan(rng: random.Random, vals: _Values) -> str:
    """`MATCH (v:LABEL) [WHERE p] [RETURN ...] [ORDER BY f [DESC] [LIMIT k]]`."""
    query = f"MATCH (v:{rng.choice(_LABELS)})"
    if rng.random() < 0.85:
        query += f" WHERE {_gen_predicate(rng, 'v', vals)}"

    # No node-only COUNT aggregation: the executor deliberately scopes
    # aggregation to traversals ("Advanced executor requires at least one edge"),
    # so `MATCH (v:L) RETURN v.data.kind AS k, COUNT(v) AS c` is a clean v0
    # rejection, not a supported shape — the fuzzer exercises COUNT over chains
    # (which do support it) instead. (Recorded as a v0 gap in spec-gridkin-v0.md.)
    mode = rng.choices(("envelope", "bare", "proj"), weights=(3, 2, 3))[0]
    if mode == "bare":
        return query + " RETURN v"
    if mode == "proj":
        return query + f" RETURN {_projection(rng, 'v')}"

    # envelope (RETURN omitted): the one shape ORDER BY / LIMIT is legal on. A
    # total tiebreak (entity_id ASC, applied by both engines) makes the LIMIT
    # subset deterministic; LIMIT is never emitted without ORDER BY.
    if rng.random() < 0.5:
        order_field = rng.choice(("v.data.severity_score", "v.data.observed_at"))
        direction = rng.choice(("", " DESC", " ASC"))
        query += f" ORDER BY {order_field}{direction}"
        if rng.random() < 0.7:
            query += f" LIMIT {rng.randint(0, 8)}"
    return query


def _edge_step(rng: random.Random) -> str:
    """A random single-hop edge step (directed; typed or type-less)."""
    etype = rng.choice((*_EDGE_TYPES, None))
    body = f":{etype}" if etype else ""
    return f"-[{body}]->" if rng.random() < 0.75 else f"<-[{body}]-"


def _gen_chain(rng: random.Random, vals: _Values) -> str:
    """`MATCH (a:L)-[..]->(b:L)[-[..]->(c:L)] [WHERE ...] [RETURN ...]`.

    The WHERE is an AND of independent single-variable predicate trees (the
    corpus's two-node-AND shape) — a form both engines apply per bound variable.
    Traversal patterns take no ORDER BY / LIMIT (the executor rejects them, and
    the oracle refuses to model them).

    WHERE is emitted on both single- and multi-hop chains, including on a node
    BEYOND the root edge (`c` on a two-hop chain). That far-node case was a
    deferred executor defect — the predicate path `to_entity__edges_out__…`
    spawned a duplicate join (row inflation + wrong-edge-type far nodes) — now
    fixed by folding the WHERE into the chain's single `.filter()`
    (`_build_chain_queryset`); the `far_node_where` gridkin scenarios regression-
    lock it and the generator exercises the path here.
    """
    node_vars = ["a", "b"]
    pattern = f"MATCH (a:{rng.choice(_LABELS)}){_edge_step(rng)}(b:{rng.choice(_LABELS)})"
    two_hop = rng.random() < 0.3
    if two_hop:
        pattern += f"{_edge_step(rng)}(c:{rng.choice(_LABELS)})"
        node_vars.append("c")

    # Nodes past the root edge (index ≥ 2) bind through a multi-valued reverse-FK
    # hop; a negation over their predicate (`NOT`, or `!=`) is executor-rejected,
    # so generate their leaves on the positive far-node surface only.
    far_vars = set(node_vars[2:])
    where_parts = [f"({_gen_predicate(rng, v, vals, far=v in far_vars)})" for v in node_vars if rng.random() < 0.5]
    if where_parts:
        pattern += " WHERE " + " AND ".join(where_parts)

    mode = rng.choices(("envelope", "bare", "proj", "agg"), weights=(3, 2, 2, 2))[0]
    if mode == "bare":
        return pattern + " RETURN " + ", ".join(node_vars)  # must name ALL bound vars
    if mode == "proj":
        return pattern + " RETURN " + ", ".join(_projection(rng, v) for v in node_vars)
    if mode == "agg":
        anchor, counted = node_vars[0], node_vars[-1]
        return pattern + f" RETURN {anchor}.entity_id AS aid, COUNT({counted}) AS c"
    return pattern  # envelope (RETURN omitted)


def _gen_union(rng: random.Random, vals: _Values) -> str:
    """`MATCH (a:L1) MATCH (b:L2) [WHERE p]` — deduplicated envelope union.

    Modeled only in the RETURN-omitted envelope form; the one global WHERE is
    scoped per clause (a leaf on a variable a clause does not bind is not applied
    to it).
    """
    query = f"MATCH (a:{rng.choice(_LABELS)}) MATCH (b:{rng.choice(_LABELS)})"
    if rng.random() < 0.6:
        query += f" WHERE {_gen_predicate(rng, rng.choice(('a', 'b')), vals)}"
    return query


def _gen_query(rng: random.Random, nodes: list[dict[str, Any]]) -> str:
    vals = _sample_values(nodes)
    family = rng.choices(("typescan", "chain", "union"), weights=(6, 3, 1))[0]
    if family == "typescan":
        return _gen_typescan(rng, vals)
    if family == "chain":
        return _gen_chain(rng, vals)
    return _gen_union(rng, vals)


# ---------------------------------------------------------------------------
# Case assembly (seedable, replayable)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Case:
    """One seeded graph plus the batch of queries generated against it.

    Every query runs read-only against the one seeded graph, so a whole batch
    shares a single (expensive) DB seed — many differentials per truncation.
    """

    graph_seed: int
    document: dict[str, Any]
    nodes: list[dict[str, Any]]
    queries: tuple[str, ...]

    @property
    def case_id(self) -> str:
        return f"g{self.graph_seed}"


def build_cases(base_seed: int, n_graphs: int, queries_per_graph: int) -> list[Case]:
    """Deterministically build `n_graphs` cases, each with `queries_per_graph` queries.

    Graph `i` derives entirely from `random.Random(base_seed + i)`: first the
    graph, then its queries, off the same stream — so the whole case replays from
    `base_seed + i` alone.
    """
    cases: list[Case] = []
    for i in range(n_graphs):
        seed = base_seed + i
        rng = random.Random(seed)
        document, nodes = _gen_graph(rng)
        queries = tuple(_gen_query(rng, nodes) for _ in range(queries_per_graph))
        cases.append(Case(graph_seed=seed, document=document, nodes=nodes, queries=queries))
    return cases


# ---------------------------------------------------------------------------
# Execution: seed once, then diff executor vs oracle per query
# ---------------------------------------------------------------------------


def seed_document(document: dict[str, Any]) -> None:
    """Import a generated graph through the real GRIFT path.

    Mirrors `gridkin/runner.py::_seed_fixture`'s production seeding and its
    fail-loud error discipline (`result.success` alone can miss a partially
    rejected import — a bad fixture must not fake-green). No soft-delete
    directives: the fuzzer never tombstones.
    """
    result = grift_import(document, dangling_edge_mode="strict")  # TAP-AUTHZ-COV: pytest-only fuzz seed
    if not result.success or result.errors:
        messages = [issue.message for issue in result.errors]
        raise AssertionError(f"fuzz fixture did not import cleanly (success={result.success}): {messages}")


@dataclass(frozen=True)
class QueryOutcome:
    """The differential verdict for one generated query."""

    query: str
    status: str  # "agree" | "diverge" | "unmodeled" | "rejected"
    detail: str = ""


def run_query(document: dict[str, Any], query: str) -> QueryOutcome:
    """Run one generated query through the executor and the oracle; diff them.

    - `agree`     — executor and oracle computed the same identity/row set.
    - `diverge`   — they disagree: a translation-fidelity bug in one engine.
    - `unmodeled` — the oracle does not model the shape (honest skip, not a green).
    - `rejected`  — the executor refused a query the oracle *does* model: an
      over-rejection bug (a well-typed generator should never trip this; if it
      does, it is a real finding, not a skip).
    - `crashed`   — the executor raised something OTHER than a clean
      `SearchExecutionError` (e.g. it emitted invalid SQL and Postgres raised).
      Emitting broken SQL is always a defect: a query is either answered or
      cleanly rejected, never crashed. Reported as a failure, never swallowed.
    """
    try:
        result = explain_gryphon_raw(  # TAP-AUTHZ-COV: pytest-only fuzz harness, not a production path
            query, {}, db_alias="default", layer="full"
        )
    except SearchExecutionError as exc:
        # Differentiate an out-of-surface shape from a genuine over-rejection by
        # asking whether the oracle even models the query.
        try:
            evaluate(parse_gryphon(query), Graph.from_grift(document), {})
        except OracleUnmodeled:
            return QueryOutcome(query, "unmodeled", f"executor-rejected + oracle-unmodeled: {exc}")
        return QueryOutcome(query, "rejected", f"executor rejected a query the oracle models: {exc}")
    except Exception as exc:  # noqa: BLE001 — a non-clean executor failure is a finding, not a harness crash
        return QueryOutcome(query, "crashed", f"{type(exc).__name__}: {exc}")

    actual = result["envelope"]
    try:
        parsed = parse_gryphon(query)
        oracle = evaluate(parsed, Graph.from_grift(document), {})
    except OracleUnmodeled as exc:
        return QueryOutcome(query, "unmodeled", str(exc))

    agrees, detail = _oracle_agrees(oracle, parsed, actual)
    return QueryOutcome(query, "agree" if agrees else "diverge", "" if agrees else detail)


def render_failure(case: Case, outcome: QueryOutcome) -> str:
    """A fully self-contained, replayable divergence report."""
    return (
        f"\n=== GRYPHON FUZZ DIVERGENCE ({outcome.status}) ===\n"
        f"replay: random.Random({case.graph_seed}) — regenerates this exact graph + query batch\n"
        f"query:\n  {outcome.query}\n"
        f"detail:\n{outcome.detail}\n"
        f"GRIFT graph:\n{json.dumps(case.document, indent=2, ensure_ascii=False)}\n"
        f"=== end divergence ===\n"
    )
