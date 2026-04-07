"""Frozen dataclasses representing the TAP gryphon AST.

All nodes are immutable. The transformer in parser.py builds these from the lark parse tree.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# Field path
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DotStep:
    """Access a named field: `variable.field`."""

    name: str


@dataclass(frozen=True)
class KeyStep:
    """Access a JSON key via bracket notation: `variable["key"]`."""

    key: str


@dataclass(frozen=True)
class IndexStep:
    """Access an array element by position: `variable.field[0]`."""

    index: int


@dataclass(frozen=True)
class WildcardStep:
    """Array wildcard: `variable.field[*]` — match any array member."""


FieldStep = DotStep | KeyStep | IndexStep | WildcardStep


@dataclass(frozen=True)
class FieldPath:
    """A dot/bracket path rooted at a named variable.

    Examples::
        hub.entity_id            → FieldPath("hub", [DotStep("entity_id")])
        node.dimensions["tap.g"] → FieldPath("node", [DotStep("dimensions"), KeyStep("tap.g")])
        node.aliases[*].name     → FieldPath("node", [DotStep("aliases"), WildcardStep(), DotStep("name")])
    """

    variable: str
    steps: tuple[FieldStep, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParamRef:
    """A runtime input variable reference: `$entity_id`."""

    name: str


# Scalar values that may appear in predicates and inline property maps.
# str | int | float | bool | None are plain Python types; ParamRef is TAP-specific.
GryphonValue = str | int | float | bool | None | ParamRef


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NodePattern:
    """A node pattern element: `(variable:label {props})`."""

    variable: str | None
    label: str | None
    inline_props: dict[str, GryphonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class EdgePattern:
    """An edge pattern element: `-[variable:TYPE*min..max {props}]->`."""

    variable: str | None
    edge_type: str | None
    direction: Literal["out", "in", "any"]
    min_hops: int = 1
    max_hops: int = 1
    inline_props: dict[str, GryphonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class PathPattern:
    """A single chain of nodes and edges in a MATCH clause.

    nodes and edges alternate: nodes[0] -edges[0]-> nodes[1] -edges[1]-> nodes[2] ...
    len(nodes) == len(edges) + 1 is always true.
    """

    nodes: tuple[NodePattern, ...]
    edges: tuple[EdgePattern, ...]


# ---------------------------------------------------------------------------
# WHERE predicates
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Comparison:
    """A single field-op-value predicate: `hub.entity_id = $entity_id`."""

    field_path: FieldPath
    op: Literal["=", "!=", "<", ">", "<=", ">="]
    value: GryphonValue


@dataclass(frozen=True)
class AndPred:
    """Conjunction: both operands must be true."""

    left: Predicate
    right: Predicate


@dataclass(frozen=True)
class OrPred:
    """Disjunction: either operand must be true."""

    left: Predicate
    right: Predicate


@dataclass(frozen=True)
class NotPred:
    """Negation: operand must be false."""

    operand: Predicate


Predicate = Comparison | AndPred | OrPred | NotPred


# ---------------------------------------------------------------------------
# Clauses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MatchClause:
    """A MATCH clause with optional path variable and one or more patterns."""

    path_var: str | None
    patterns: tuple[PathPattern, ...]


@dataclass(frozen=True)
class WhereClause:
    """A WHERE clause with its root predicate."""

    predicate: Predicate


@dataclass(frozen=True)
class ReturnItem:
    """A single item in a RETURN clause: `field_path AS alias`."""

    path: FieldPath
    alias: str | None


@dataclass(frozen=True)
class ReturnClause:
    """A RETURN clause.

    items=None means the RETURN was omitted — TAP returns a graph envelope by default.
    items=[...] means the caller wants row projection of the listed fields.
    """

    items: tuple[ReturnItem, ...] | None


# ---------------------------------------------------------------------------
# Root AST node
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GryphonAST:
    """The parsed representation of a complete gryphon query."""

    match_clauses: tuple[MatchClause, ...]
    where_clause: WhereClause | None
    return_clause: ReturnClause

    def required_params(self) -> frozenset[str]:
        """Return the set of $var names referenced anywhere in this AST."""
        params: set[str] = set()
        _collect_params_from_predicate(self.where_clause.predicate if self.where_clause else None, params)
        for mc in self.match_clauses:
            for pattern in mc.patterns:
                for node in pattern.nodes:
                    for v in node.inline_props.values():
                        if isinstance(v, ParamRef):
                            params.add(v.name)
                for edge in pattern.edges:
                    for v in edge.inline_props.values():
                        if isinstance(v, ParamRef):
                            params.add(v.name)
        return frozenset(params)


def _collect_params_from_predicate(pred: Predicate | None, out: set[str]) -> None:
    if pred is None:
        return
    if isinstance(pred, Comparison):
        if isinstance(pred.value, ParamRef):
            out.add(pred.value.name)
    elif isinstance(pred, (AndPred, OrPred)):
        _collect_params_from_predicate(pred.left, out)
        _collect_params_from_predicate(pred.right, out)
    elif isinstance(pred, NotPred):
        _collect_params_from_predicate(pred.operand, out)
