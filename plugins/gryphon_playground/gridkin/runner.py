"""Gridkin scenario execution: seed the fixture, run the query, compare oracles.

For one scenario the runner:

1. Loads the named GRIFT fixture through the standard `grift_import` path.
2. Executes the Gryphon query via `explain_gryphon_raw`, capturing the response
   envelope and the SQL the executor issued.
3. Compares both against committed oracle files — reporting envelope mismatch
   and SQL mismatch as separate failure modes.

Snapshot regeneration (`GRIDKIN_UPDATE_SNAPSHOTS`) overwrites the oracle files
with the current output instead of asserting; it is opt-in and the regenerated
diff must be human-reviewed (req-gridkin-oracle-assertion / -snapshot-discipline).

Per spec-gridkin-v0.md: req-gridkin-runner-contract, req-gridkin-explain-snapshot.
"""

from __future__ import annotations

import difflib
import json
from typing import TYPE_CHECKING, Any

from tap_grid.grift import grift_import
from tap_grid.gryphon import explain_gryphon_raw
from tap_grid.services import delete_node

if TYPE_CHECKING:
    from pathlib import Path

    from plugins.gryphon_playground.gridkin.loader import Scenario


def normalize_sql(text: str) -> str:
    """Whitespace-normalize SQL for comparison: collapse runs, trim, drop blanks.

    Trivial formatting differences do not churn snapshots; everything else —
    table/column names, JOIN structure, predicates, params, stage labels — is
    compared exactly.
    """
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def run_scenario(scenario: Scenario, *, update_snapshots: bool = False) -> list[str]:
    """Run one Gridkin scenario.

    Returns a list of failure messages — empty means the scenario passed.
    Envelope and SQL mismatches are separate entries so the caller can tell
    whether behavior changed or the query plan changed.

    With `update_snapshots`, the oracle files are regenerated and an empty list
    is returned (regeneration never "fails").
    """
    _seed_fixture(scenario)
    result = explain_gryphon_raw(scenario.query, scenario.params, db_alias="default", layer=scenario.layer)
    actual_envelope: dict[str, Any] = result["envelope"]
    actual_sql: str = result["sql"].render()

    if update_snapshots:
        _write_snapshots(scenario, actual_envelope, actual_sql)
        return []

    failures: list[str] = []
    failures.extend(_check_envelope(scenario, actual_envelope))
    failures.extend(_check_sql(scenario, actual_sql))
    return failures


def _seed_fixture(scenario: Scenario) -> None:
    """Seed the test DB: import each GRIFT fixture in order, then apply
    soft-delete directives.

    Multi-fixture scenarios (req-gridkin-multi-fixture-load) declare an
    array of fixture paths. The runner imports each in order; every fixture
    must import cleanly (`result.success && not result.errors`) or the
    scenario fails. Soft-delete directives run once after the last fixture
    loads.
    """
    for fixture_path in scenario.fixture_paths:
        if not fixture_path.is_file():
            raise AssertionError(f"{scenario.scenario_id}: GRIFT fixture not found: {fixture_path}")
        document = json.loads(fixture_path.read_text(encoding="utf-8"))
        result = grift_import(document, dangling_edge_mode="strict")
        # A non-collector direct grift_import caller owns checking result.errors —
        # result.success alone can miss a partially-rejected import. A bad fixture
        # must fail loud, not fake-green (the GRIFT atomic-batch-rejection rule).
        if not result.success or result.errors:
            messages = [issue.message for issue in result.errors]
            raise AssertionError(
                f"{scenario.scenario_id}: GRIFT fixture {fixture_path.name} "
                f"did not import cleanly (success={result.success}): {messages}"
            )

    # GRIFT import is additive/upsert-only (spec-grift-v0.md) — it never
    # tombstones entities. Soft-deleted graph state is set up here instead:
    # each `soft_delete` entity id is deleted through the service-layer
    # delete_node verb, post-import, before the scenario query runs.
    for entity_id in scenario.soft_delete:
        delete_result = delete_node(entity_id)
        if not delete_result.success:
            raise AssertionError(f"{scenario.scenario_id}: soft-delete of {entity_id} failed: {delete_result.errors}")


# Spine fields that carry provenance, not query semantics: the import-time
# timestamps and the originating grid id. They vary per run and per
# environment, so the runner redacts them to a sentinel before comparing or
# writing a snapshot — a Gridkin scenario asserts what a query returns, not
# when the fixture was imported or on which grid.
_VOLATILE_SPINE_FIELDS = ("created_at", "updated_at", "originating_grid_id")
_REDACTED = "<volatile>"


def _redact_member(member: dict[str, Any]) -> dict[str, Any]:
    """Copy a node/edge envelope with volatile provenance fields redacted."""
    redacted = dict(member)
    for field in _VOLATILE_SPINE_FIELDS:
        if field in redacted:
            redacted[field] = _REDACTED
    return redacted


def _canonical_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """Return a stable, comparable form of a response envelope.

    - `nodes` and `edges` are sorted by entity_id: a graph envelope's member
      lists are sets, and the executor emits them in DB-discretion order (the
      hub-and-spoke neighbor fetch, for one, has no ORDER BY).
    - Volatile provenance fields (import timestamps, originating grid id) are
      redacted to a sentinel on every member — see `_VOLATILE_SPINE_FIELDS`.
    - `rows` (RETURN projection / aggregation output) is left untouched: its
      order can carry meaning and it has no volatile spine fields.

    Applied to both sides of every comparison and to the written snapshot, so
    the committed expected file is stable across runs and environments.
    """
    canonical = dict(envelope)
    for key in ("nodes", "edges"):
        members = canonical.get(key)
        if isinstance(members, list):
            redacted = [_redact_member(m) for m in members]
            canonical[key] = sorted(redacted, key=lambda m: str(m.get("entity_id", "")))
    return canonical


def _write_snapshots(scenario: Scenario, envelope: dict[str, Any], sql_text: str) -> None:
    scenario.expected_envelope_path.parent.mkdir(parents=True, exist_ok=True)
    scenario.expected_envelope_path.write_text(
        json.dumps(_canonical_envelope(envelope), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    scenario.expected_sql_path.parent.mkdir(parents=True, exist_ok=True)
    scenario.expected_sql_path.write_text(sql_text, encoding="utf-8")


def _check_envelope(scenario: Scenario, actual: dict[str, Any]) -> list[str]:
    path = scenario.expected_envelope_path
    if not path.is_file():
        return [_missing(scenario, "envelope", path)]
    expected = _canonical_envelope(json.loads(path.read_text(encoding="utf-8")))
    actual_canonical = _canonical_envelope(actual)
    if expected == actual_canonical:
        return []
    return ["ENVELOPE MISMATCH — the response envelope changed (behavior).\n" + _json_diff(expected, actual_canonical)]


def _check_sql(scenario: Scenario, actual_sql: str) -> list[str]:
    path = scenario.expected_sql_path
    if not path.is_file():
        return [_missing(scenario, "SQL", path)]
    expected = normalize_sql(path.read_text(encoding="utf-8"))
    actual = normalize_sql(actual_sql)
    if expected == actual:
        return []
    return ["SQL MISMATCH — the executor's compiled SQL changed (query plan).\n" + _line_diff(expected, actual)]


def _missing(scenario: Scenario, kind: str, path: Path) -> str:
    return (
        f"{kind.upper()}: expected file missing: {path}\n"
        f"  Author it by hand per the oracle discipline, or run with "
        f"GRIDKIN_UPDATE_SNAPSHOTS=1 to generate it — then review every line "
        f"of the diff before committing (spec-gridkin-v0.md "
        f"req-gridkin-oracle-assertion)."
    )


def _json_diff(expected: Any, actual: Any) -> str:
    exp = json.dumps(expected, indent=2, ensure_ascii=False, sort_keys=True).splitlines()
    act = json.dumps(actual, indent=2, ensure_ascii=False, sort_keys=True).splitlines()
    return _line_diff("\n".join(exp), "\n".join(act))


def _line_diff(expected: str, actual: str) -> str:
    diff = difflib.unified_diff(
        expected.splitlines(),
        actual.splitlines(),
        fromfile="expected (oracle)",
        tofile="actual (executor)",
        lineterm="",
    )
    return "\n".join(diff)
