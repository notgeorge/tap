"""Empirical executor-stage coverage — derive the dispatch-path set from the code.

The intent-coverage AAR (`docs/aar/2026-06-30-gridkin-intent-coverage-not-path-coverage.md`)
found a silent-wrong-answer bug living on an executor dispatch path that *no*
scenario exercised, while a green "intents covered" ledger sat directly over it.
The lesson: coverage of language *intent* is not coverage of executor *paths*,
and where one feature has several dispatch paths, intent-coverage systematically
under-counts.

This module closes that gap mechanically. The executor tags every dispatch path
with a `gryphon_stage("<label>")` context manager, and every committed Gridkin
SQL snapshot records the stage each statement ran under
(`-- statement N · stage: <label>`). So the authoritative path inventory can be
*derived from the source* (not a hand-kept list), and the set actually exercised
can be *derived from the snapshots* — and the two cross-checked.

The gate is **sharpened past mere reachability**: the bug that motivated it was a
stage reached only *without* a WHERE (so its WHERE-application code — absent —
was never exercised). Reachability alone would have passed. So the gate asserts
each stage is exercised by a scenario that actually *carries a WHERE* — the
property whose absence was the defect. All five current stages apply a WHERE, so
all five must be WHERE-exercised.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import TYPE_CHECKING

import tap_grid.gryphon.executor as executor_module
from tap_grid.gryphon.parser import parse_gryphon

if TYPE_CHECKING:
    from plugins.gryphon_playground.gridkin.loader import Scenario

_STAGE_FUNC = "gryphon_stage"
# Snapshot header line, e.g. `-- statement 1 · stage: single-hop`.
_SNAPSHOT_STAGE_RE = re.compile(r"^-- statement \d+ · stage: (.+)$", re.MULTILINE)

EXECUTOR_SOURCE = Path(executor_module.__file__)


def enumerate_stage_labels(source_path: Path = EXECUTOR_SOURCE) -> set[str]:
    """Every string-literal label passed to `gryphon_stage()` in the executor.

    AST-based, not a text grep: a `gryphon_stage(non_literal)` call is caught and
    raised on rather than silently missed. The stage list is the authoritative
    dispatch-path inventory — it must come from the code, and the gate must fail
    loudly the moment a stage stops being enumerable rather than under-report.
    """
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    labels: set[str] = set()
    non_literal_lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name != _STAGE_FUNC or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            labels.add(first.value)
        else:
            non_literal_lines.append(node.lineno)
    if non_literal_lines:
        raise ValueError(
            f"{_STAGE_FUNC}() called with a non-literal stage label at "
            f"{source_path.name}:{non_literal_lines} — the stage-coverage gate "
            "cannot enumerate a computed label; use a string literal."
        )
    return labels


def snapshot_stages(sql_text: str) -> set[str]:
    """The set of stage labels recorded in a committed SQL snapshot document."""
    return {match.strip() for match in _SNAPSHOT_STAGE_RE.findall(sql_text)}


def query_carries_where(query: str) -> bool:
    """True if the query applies a WHERE anywhere the executor would honor one.

    Counts both the top-level `WHERE` and a `NOT EXISTS { ... WHERE ... }` inner
    predicate — the advanced stage applies the latter inside the anti-join, so a
    NOT-EXISTS-with-inner-WHERE scenario legitimately exercises that stage's
    WHERE-application path.
    """
    parsed = parse_gryphon(query)
    if parsed.where_clause is not None:
        return True
    return any(clause.where_clause is not None for clause in parsed.not_exists_clauses)


def where_exercised_stages(scenarios: list[Scenario]) -> tuple[set[str], set[str]]:
    """Scan result scenarios' snapshots for the stages exercised.

    Returns `(stages_seen, stages_seen_with_where)`:

    - `stages_seen`: every stage label appearing in any result scenario's
      snapshot (the drift axis — a label here but not in the source is stale).
    - `stages_seen_with_where`: the subset of those reached by a scenario whose
      query carries a WHERE (the sharpened coverage axis).
    """
    stages_seen: set[str] = set()
    stages_with_where: set[str] = set()
    for scenario in scenarios:
        if scenario.expected_sql_path is None:
            continue  # rejection scenario — no snapshot to inspect
        stages = snapshot_stages(scenario.expected_sql_path.read_text(encoding="utf-8"))
        stages_seen |= stages
        if query_carries_where(scenario.query):
            stages_with_where |= stages
    return stages_seen, stages_with_where
