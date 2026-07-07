"""Guards for the executor findings ledger (`req-gridkin-findings-ledger`).

Pure-Python (no DB): validates the committed ledger against the controlled
vocabulary so a malformed or mis-tagged finding fails the gate, and unit-tests
the reporter + the coverage enrichment (with a synthetic executor + coverage
JSON, so the assertion does not churn as executor.py line numbers shift).
"""

from __future__ import annotations

import json
from pathlib import Path

from plugins.gryphon_playground.gridkin import findings_ledger as fl

_LEDGER = Path("plugins/gryphon_playground/gridkin/gryphon-findings.jsonl")
_EXECUTOR = Path("tap_grid/gryphon/executor.py")


def test_committed_ledger_is_valid() -> None:
    """Every committed finding is well-formed and uses the controlled vocabulary."""
    rows = fl.load(str(_LEDGER))
    assert rows, "the findings ledger should be backfilled, not empty"
    fl.validate(rows)  # raises LedgerError on any structural / vocab violation


def test_report_renders_all_sections() -> None:
    """The hotspot report renders its sections over the committed ledger."""
    out = fl.report(str(_LEDGER), str(_EXECUTOR), coverage_json_path="")
    for section in ("HOTSPOTS BY SUBSYSTEM", "HOTSPOTS BY FUNCTION", "BY DISCOVERY SOURCE"):
        assert section in out, f"missing report section: {section}"


def test_function_subsystem_map_targets_known_subsystems() -> None:
    """Every function->subsystem entry points at a declared subsystem (no typos)."""
    unknown = {sub for sub in fl.FUNCTION_SUBSYSTEM.values() if sub not in fl.SUBSYSTEMS}
    assert not unknown, f"FUNCTION_SUBSYSTEM references undeclared subsystems: {unknown}"


def test_coverage_enrichment_maps_lines_to_subsystems(tmp_path: Path) -> None:
    """subsystem_line_coverage sums covered/total lines over a subsystem's functions.

    Uses a synthetic executor module + coverage JSON so the arithmetic is exact
    and stable (real executor.py line numbers move; the algorithm does not).
    """
    exe = tmp_path / "executor.py"
    # `_build_chain_queryset` -> chain-join, lines 1-4; `_comparison_to_q` ->
    # predicate-lowering, lines 6-9. (Bodies are irrelevant; only line spans matter.)
    exe.write_text(
        "def _build_chain_queryset():\n    a = 1\n    b = 2\n    return a\n\n"
        "def _comparison_to_q():\n    c = 3\n    d = 4\n    return c\n",
        encoding="utf-8",
    )
    cov = tmp_path / "cov.json"
    # chain-join: lines 2,3 executed, 4 missing -> 2/3. predicate-lowering: 7
    # executed, 8,9 missing -> 1/3.
    cov.write_text(
        json.dumps(
            {"files": {"x/tap_grid/gryphon/executor.py": {"executed_lines": [2, 3, 7], "missing_lines": [4, 8, 9]}}}
        ),
        encoding="utf-8",
    )
    per = fl.subsystem_line_coverage(str(exe), str(cov))
    assert per["chain-join"] == (2, 3)
    assert per["predicate-lowering"] == (1, 3)


def test_coverage_absent_is_graceful() -> None:
    """Missing coverage JSON yields no coverage data, not an error."""
    assert fl.subsystem_line_coverage(str(_EXECUTOR), "/no/such/coverage.json") == {}
