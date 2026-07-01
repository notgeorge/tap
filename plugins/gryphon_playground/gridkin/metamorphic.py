"""Metamorphic relations over the Gryphon corpus — executor *self*-consistency.

The model oracle (`req-gridkin-oracle-assertion`) checks each query against an
independent recomputation. Metamorphic relations add a *different* kind of check:
they transform one query into related forms that MUST agree, and compare the
executor against **itself**. That catches a bug the oracle and the executor could
share (common-mode — both authored the same null-logic mistake), and it exercises
cross-*path* consistency the single-query oracle cannot.

**TLP (Ternary Logic Partitioning, after SQLancer)** is the relation shipped here.
For a predicate `p` over a bound variable, the rows where `p` is TRUE, FALSE, and
UNKNOWN must *partition* the unfiltered rows — pairwise disjoint, and together the
whole. This is a direct probe of Gryphon's deliberate 2VL/3VL null divergence,
which the discriminator below respects (getting it wrong is the whole trap):

- **Null *field* vs a non-null literal → SQL 3VL.** `p` is UNKNOWN exactly when the
  field is unobserved, so the third partition is `<field> IS UNKNOWN`. TRUE / FALSE
  / UNKNOWN is a genuine three-way split of the scan.
- **Null *literal* operand → 2VL short-circuit.** `field OP null` is genuine FALSE
  (never UNKNOWN), so there is NO third partition: TRUE is empty, FALSE is
  everything. A naive `<field> IS UNKNOWN` third partition would *double-count* the
  field-null rows (which live in FALSE here) — so TLP MUST discriminate on whether
  the null is in the query text (literal) or the data (field).

TLP is scoped to **labelled type scans** with a single `Comparison` WHERE: within
one declared type the TRUE/FALSE/UNKNOWN split is exact. (A bare labelless scan
defers OR/NOT and conflates "field is null" with "this type lacks the field", so
its partition is not clean.)

**NoREC (envelope-vs-projection) was considered and deferred**, deliberately. The
intent — a single-hop pattern+WHERE must agree run as an envelope vs as a
projection — does not yield a *distinct* check here: single-hop field projections
degrade to a bare-variable envelope (`_collect_graph_envelope` ignores the field
steps), so the two forms are the same computation; and a type-scan envelope-vs-
projection is same-path, redundant with TLP's TRUE partition. Its actual target
(the envelope-WHERE cross-path silent-drop) is already covered structurally by the
single-hop dispatch collapse and by the model oracle. Recorded, not faked.

Queries are derived as strings (the executor takes query text; there is no
AST-executor). The predicate text is lifted verbatim from the source query so no
literal is re-rendered; only field paths and node patterns — which carry no
literals — are rendered from the AST.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from tap_grid.gryphon.ast_nodes import Comparison, DotStep, GryphonAST, ParamRef
from tap_grid.gryphon.parser import parse_gryphon

if TYPE_CHECKING:
    from plugins.gryphon_playground.gridkin.loader import Scenario

# WHERE predicate text lifted from the source query, up to the next top-level
# clause. Eligible queries carry a single simple WHERE and no NOT EXISTS / brace
# block, so this span is unambiguous.
_WHERE_SPAN_RE = re.compile(
    r"\bWHERE\b(?P<pred>.+?)(?:\bRETURN\b|\bORDER\s+BY\b|\bLIMIT\b|$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TLPPlan:
    """A derived TLP partition for one eligible scenario."""

    unfiltered_query: str
    true_query: str
    false_query: str
    unknown_query: str | None  # None ⟺ 2VL null-literal (no UNKNOWN partition)
    is_two_valued: bool


def _normalize(query: str) -> str:
    return " ".join(query.split())


def _render_field_path(field_path: Any) -> str | None:
    """Render `var.step.step` — dot steps only (no literals, so no re-quoting risk)."""
    parts = [field_path.variable]
    for step in field_path.steps:
        if not isinstance(step, DotStep):
            return None  # key/index/wildcard steps not supported
        parts.append(step.name)
    return ".".join(parts)


def _where_text(query: str) -> str | None:
    match = _WHERE_SPAN_RE.search(_normalize(query))
    if match is None:
        return None
    text = match.group("pred").strip()
    return text or None


def _single_node_pattern(ast: GryphonAST) -> Any | None:
    """The lone node of a single-clause, single-pattern, node-only, variable-bound,
    prop-free MATCH — or None if the query is not that shape."""
    if ast.optional_match_clauses or ast.not_exists_clauses:
        return None
    if len(ast.match_clauses) != 1 or len(ast.match_clauses[0].patterns) != 1:
        return None
    pattern = ast.match_clauses[0].patterns[0]
    if len(pattern.edges) != 0:
        return None
    node = pattern.nodes[0]
    if node.variable is None or node.inline_props:
        return None
    return node


def _render_node_pattern(node: Any) -> str:
    return f"MATCH ({node.variable}:{node.label})" if node.label else f"MATCH ({node.variable})"


def _literal_is_null(value: Any, params: dict[str, Any]) -> bool:
    """True if the comparison's right operand resolves to a null literal (2VL)."""
    if isinstance(value, ParamRef):
        return params.get(value.name) is None
    return value is None


def derive_tlp(scenario: Scenario) -> TLPPlan | None:
    """Derive a TLP partition from a scenario, or None if it is not eligible.

    Eligible: a single node-only type/bare scan with a WHERE that is exactly one
    `Comparison` over the bound variable, whose field path is dot-steps only. The
    RETURN is normalized to an entity-id projection so the relation compares
    identity sets regardless of the scenario's own RETURN shape.
    """
    if scenario.expected_error is not None:
        return None
    try:
        ast = parse_gryphon(scenario.query)
    except Exception:
        return None

    node = _single_node_pattern(ast)
    if node is None or ast.where_clause is None:
        return None
    # Labelled type scans only. A bare labelless scan (`MATCH (n)`) restricts
    # data-lane WHERE to AND-joined predicates (OR/NOT are deferred across the
    # per-type field-absence boundary), so its FALSE partition (`WHERE NOT (...)`)
    # can be rejected outright; and `IS UNKNOWN` over a bare scan conflates
    # "field is null" with "this type has no such field". The partition is clean
    # only within one declared type.
    if node.label is None:
        return None
    predicate = ast.where_clause.predicate
    if not isinstance(predicate, Comparison):
        return None
    if predicate.field_path.variable != node.variable:
        return None
    field_text = _render_field_path(predicate.field_path)
    where_text = _where_text(scenario.query)
    if field_text is None or where_text is None:
        return None

    pattern = _render_node_pattern(node)
    projection = f"RETURN {node.variable}.entity_id AS id"
    is_two_valued = _literal_is_null(predicate.value, scenario.params)

    return TLPPlan(
        unfiltered_query=f"{pattern} {projection}",
        true_query=f"{pattern} WHERE {where_text} {projection}",
        false_query=f"{pattern} WHERE NOT ({where_text}) {projection}",
        unknown_query=(None if is_two_valued else f"{pattern} WHERE {field_text} IS UNKNOWN {projection}"),
        is_two_valued=is_two_valued,
    )
