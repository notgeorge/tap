"""TAP gryphon language parser.

Converts gryphon text (str or list[str]) into a GryphonAST using lark.
"""

from __future__ import annotations

import os
from typing import Any

from lark import Lark, Token, Transformer, UnexpectedInput, v_args

from tap_grid.gryphon.ast_nodes import (
    AggregateCall,
    AggregateReturnItem,
    AndPred,
    Comparison,
    DotStep,
    EdgePattern,
    FieldPath,
    GryphonAST,
    IndexStep,
    KeyStep,
    MatchClause,
    NodePattern,
    NotExistsClause,
    NotPred,
    OrPred,
    ParamRef,
    PathPattern,
    ReturnClause,
    ReturnItem,
    WhereClause,
    WildcardStep,
)

_GRAMMAR_PATH = os.path.join(os.path.dirname(__file__), "grammar.lark")

with open(_GRAMMAR_PATH) as _f:
    _GRAMMAR_TEXT = _f.read()

# Build the parser once at module load. LALR(1) is fast; ambiguity=resolve
# handles the OR/AND/NOT precedence rules in the grammar.
_PARSER = Lark(
    _GRAMMAR_TEXT,
    parser="earley",
    ambiguity="resolve",
    propagate_positions=False,
)


class GryphonParseError(Exception):
    """Raised when gryphon text cannot be parsed.

    Attributes:
        message: Human-readable description.
        line: Line number (1-based) if available.
        col: Column number (1-based) if available.
    """

    def __init__(self, message: str, line: int | None = None, col: int | None = None) -> None:
        self.message = message
        self.line = line
        self.col = col
        loc = f" (line {line}, col {col})" if line is not None else ""
        super().__init__(f"Gryphon parse error{loc}: {message}")


# ---------------------------------------------------------------------------
# Transformer-internal markers
# ---------------------------------------------------------------------------
#
# node_body and edge_body parse into a handful of optional children — variable
# name, label, inline props, hop range — and lark flattens identically-typed
# children, so we need a way to distinguish "NAME that appeared BEFORE the
# colon" from "NAME that appeared AFTER the colon" in the transformer. These
# marker str-subclasses carry that distinction out of the sub-rule.


class _VarMarker(str):
    """A NAME token that appeared in the variable position of a node/edge body."""


class _LabelMarker(str):
    """A NAME token that appeared in the label/type position (after the colon)."""


# ---------------------------------------------------------------------------
# Lark transformer
# ---------------------------------------------------------------------------


@v_args(inline=True)
class _ASTTransformer(Transformer):
    """Transform a lark parse tree into TAP AST dataclasses."""

    # -- start / clauses --

    def start(self, *clauses: Any) -> GryphonAST:
        match_clauses = [c for c in clauses if isinstance(c, MatchClause)]
        where_clauses = [c for c in clauses if isinstance(c, WhereClause)]
        return_clauses = [c for c in clauses if isinstance(c, ReturnClause)]
        not_exists_clauses = [c for c in clauses if isinstance(c, NotExistsClause)]

        if not match_clauses:
            raise GryphonParseError("At least one MATCH clause is required.")

        where = where_clauses[0] if where_clauses else None
        ret = return_clauses[0] if return_clauses else ReturnClause(items=None)

        return GryphonAST(
            match_clauses=tuple(match_clauses),
            where_clause=where,
            return_clause=ret,
            not_exists_clauses=tuple(not_exists_clauses),
        )

    def clause(self, inner: Any) -> Any:
        return inner

    def edge_pattern(self, inner: Any) -> Any:
        """Pass-through: unwraps the Tree wrapper lark adds for unaliased single-child rules."""
        return inner

    def predicate(self, inner: Any) -> Any:
        """Pass-through: unwraps Tree wrapper for the unaliased `comparison` alternative."""
        return inner

    # -- MATCH --

    def match_clause(self, *args: Any) -> MatchClause:
        path_var: str | None = None
        patterns: list[PathPattern] = []
        for a in args:
            if isinstance(a, str):
                path_var = a
            elif isinstance(a, PathPattern):
                patterns.append(a)
        return MatchClause(path_var=path_var, patterns=tuple(patterns))

    def path_var(self, name: Token) -> str:
        return str(name)

    def pattern(self, *args: Any) -> PathPattern:
        nodes = [a for a in args if isinstance(a, NodePattern)]
        edges = [a for a in args if isinstance(a, EdgePattern)]
        return PathPattern(nodes=tuple(nodes), edges=tuple(edges))

    def node_pattern(self, body: Any) -> NodePattern:
        return body

    def node_body(self, *args: Any) -> NodePattern:
        variable: str | None = None
        label: str | None = None
        props: dict[str, Any] = {}
        for a in args:
            if isinstance(a, _VarMarker):
                variable = str(a)
            elif isinstance(a, _LabelMarker):
                label = str(a)
            elif isinstance(a, dict):
                props = a
        return NodePattern(variable=variable, label=label, inline_props=props)

    def node_body_var(self, name: Token) -> _VarMarker:
        return _VarMarker(str(name))

    def node_body_label(self, name: Token) -> _LabelMarker:
        return _LabelMarker(str(name))

    def outbound_edge(self, body: Any) -> EdgePattern:
        return EdgePattern(
            variable=body.variable,
            edge_type=body.edge_type,
            direction="out",
            min_hops=body.min_hops,
            max_hops=body.max_hops,
            inline_props=body.inline_props,
        )

    def inbound_edge(self, body: Any) -> EdgePattern:
        return EdgePattern(
            variable=body.variable,
            edge_type=body.edge_type,
            direction="in",
            min_hops=body.min_hops,
            max_hops=body.max_hops,
            inline_props=body.inline_props,
        )

    def undirected_edge(self, body: Any) -> EdgePattern:
        return EdgePattern(
            variable=body.variable,
            edge_type=body.edge_type,
            direction="any",
            min_hops=body.min_hops,
            max_hops=body.max_hops,
            inline_props=body.inline_props,
        )

    def edge_body(self, *args: Any) -> EdgePattern:
        variable: str | None = None
        edge_type: str | None = None
        min_hops = 1
        max_hops = 1
        props: dict[str, Any] = {}
        for a in args:
            if isinstance(a, _VarMarker):
                variable = str(a)
            elif isinstance(a, _LabelMarker):
                edge_type = str(a)
            elif isinstance(a, tuple):  # hop_range
                min_hops, max_hops = a
            elif isinstance(a, dict):
                props = a
        # direction is set by the parent edge_pattern rule
        return EdgePattern(
            variable=variable,
            edge_type=edge_type,
            direction="any",
            min_hops=min_hops,
            max_hops=max_hops,
            inline_props=props,
        )

    def edge_body_var(self, name: Token) -> _VarMarker:
        return _VarMarker(str(name))

    def edge_body_type(self, name: Token) -> _LabelMarker:
        return _LabelMarker(str(name))

    def hop_range(self, lo: Token, hi: Token) -> tuple[int, int]:
        return int(lo), int(hi)

    def inline_props(self, *pairs: Any) -> dict[str, Any]:
        return dict(pairs)

    def prop_pair(self, name: Token, value: Any) -> tuple[str, Any]:
        return str(name), value

    # -- WHERE --

    def where_clause(self, predicate: Any) -> WhereClause:
        return WhereClause(predicate=predicate)

    def predicate(self, inner: Any) -> Any:
        return inner

    def and_pred(self, left: Any, right: Any) -> AndPred:
        return AndPred(left=left, right=right)

    def or_pred(self, left: Any, right: Any) -> OrPred:
        return OrPred(left=left, right=right)

    def not_pred(self, operand: Any) -> NotPred:
        return NotPred(operand=operand)

    def paren_pred(self, inner: Any) -> Any:
        return inner

    def comparison(self, fp: FieldPath, op: Token, value: Any) -> Comparison:
        return Comparison(field_path=fp, op=str(op), value=value)

    # -- Field paths --

    def field_path(self, name: Token, *steps: Any) -> FieldPath:
        return FieldPath(variable=str(name), steps=tuple(steps))

    def field_step(self, step: Any) -> Any:
        return step

    def dot_step(self, name: Token) -> DotStep:
        return DotStep(name=str(name))

    def key_step(self, key: Token) -> KeyStep:
        return KeyStep(key=str(key)[1:-1])  # strip surrounding quotes

    def index_step(self, idx: Token) -> IndexStep:
        return IndexStep(index=int(idx))

    def wildcard_step(self, _star: Token) -> WildcardStep:
        return WildcardStep()

    # -- NOT EXISTS --

    def not_exists_clause(self, *args: Any) -> NotExistsClause:
        mc = next((a for a in args if isinstance(a, MatchClause)), None)
        wc = next((a for a in args if isinstance(a, WhereClause)), None)
        if mc is None:
            raise GryphonParseError("NOT EXISTS block requires a MATCH clause.")
        return NotExistsClause(match_clause=mc, where_clause=wc)

    # -- RETURN --

    def return_clause(self, *items: Any) -> ReturnClause:
        return ReturnClause(items=tuple(items))

    def field_item(self, *args: Any) -> ReturnItem:
        path = args[0]
        alias = str(args[1]) if len(args) > 1 else None
        return ReturnItem(path=path, alias=alias)

    def aggregate_item(self, aggregate: AggregateCall, alias: Any) -> AggregateReturnItem:
        return AggregateReturnItem(aggregate=aggregate, alias=str(alias))

    def aggregate_call(self, path: FieldPath) -> AggregateCall:
        # Only COUNT is supported in v1; the _COUNT_KW terminal is discarded
        # by lark so the only child here is the field_path argument.
        return AggregateCall(function="count", argument=path)

    # -- Values --

    def string_val(self, s: Token) -> str:
        raw = str(s)
        return raw[1:-1].replace('\\"', '"').replace("\\\\", "\\")

    def number_val(self, n: Token) -> int | float:
        s = str(n)
        return float(s) if "." in s else int(s)

    def param_ref(self, name: Token) -> ParamRef:
        return ParamRef(name=str(name))

    def true_val(self) -> bool:
        return True

    def false_val(self) -> bool:
        return False

    def null_val(self) -> None:
        return None

    def value(self, inner: Any) -> Any:
        return inner


_TRANSFORMER = _ASTTransformer()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_gryphon(text: str | list[str]) -> GryphonAST:
    """Parse gryphon text into a GryphonAST.

    Args:
        text: A single string or a list of strings (one clause per line).
              Both forms are equivalent and normalize to the same AST.

    Returns:
        A frozen GryphonAST dataclass tree.

    Raises:
        GryphonParseError: If the text cannot be parsed.
    """
    if isinstance(text, list):
        normalized = " ".join(text)
    else:
        normalized = text.strip()

    try:
        tree = _PARSER.parse(normalized)
        return _TRANSFORMER.transform(tree)
    except GryphonParseError:
        raise
    except UnexpectedInput as exc:
        raise GryphonParseError(
            str(exc).split("\n")[0],
            line=getattr(exc, "line", None),
            col=getattr(exc, "column", None),
        ) from exc
    except Exception as exc:
        raise GryphonParseError(str(exc)) from exc
