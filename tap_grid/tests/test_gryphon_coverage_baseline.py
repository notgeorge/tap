"""Guard: the Gryphon executor branch-coverage ratchet baseline is well-formed.

The ratchet itself (`scripts/gryphon-coverage-ratchet`) is a ~10-15 min
coverage-instrumented run over the executor-exercising suites — too slow to be a
per-commit pytest gate, so it is a script tracked in the `spec-dev-validation.md`
Validation Map (`req-gridkin-executor-branch-coverage`). This cheap test keeps the
*committed floor* honest per-commit: valid JSON, an integer floor in range, and
the provenance keys present — so a malformed or nonsensical floor is caught by CI
even though the full instrumented comparison is not.
"""

from __future__ import annotations

import json
from pathlib import Path

BASELINE = Path(__file__).resolve().parents[1] / "gryphon" / "coverage-baseline.json"


def test_baseline_file_is_well_formed():
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    floor = data["executor_branch_pct_floor"]
    assert isinstance(floor, int), "executor_branch_pct_floor must be an integer percent"
    assert 0 <= floor <= 100, f"floor out of range: {floor}"
    # The floor must not exceed the last real measurement — it is a floor, not a
    # wish. int(measured) is the tightest floor that tolerates sub-point wobble.
    measured = data["measured_branch_pct"]
    assert measured >= floor, f"floor {floor} exceeds last measured {measured}"
    assert int(measured) >= floor
    assert data["suites"], "baseline must record which suites the floor was measured over"
    assert data["note"], "baseline must carry a human note pointing at the ratchet script"
