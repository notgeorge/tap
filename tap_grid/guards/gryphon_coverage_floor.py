"""Gryphon branch-coverage floor honesty guard — `req-gridkin-executor-branch-coverage`.

The floor comparison itself is a ~10-15 min coverage-instrumented run
(`scripts/gryphon-coverage-ratchet`, which calls `tap.ratchet.ratchet_floor`) — too
slow for a per-commit gate. This guard is the cheap per-commit half: it keeps the
*committed floor* honest (valid integer in range, not exceeding the last real
measurement, provenance recorded), so a malformed or wishful floor is caught by CI
even though the full instrumented comparison is not. The floor direction has no
per-commit `measure()`, so this is a structural `Guard`, not a ratchet subclass.

Owned by tap_grid because the floor file and the executor it covers both live under
`tap_grid/gryphon/`.
"""

from __future__ import annotations

import json

from tap.guards.base import REPO_ROOT, Guard

_BASELINE = REPO_ROOT / "tap_grid" / "gryphon" / "coverage-baseline.json"


class GryphonCoverageFloorGuard(Guard):
    slug = "gryphon-coverage-floor"
    map_row = "Gryphon branch-coverage floor (well-formedness)"
    rid = "req-gridkin-executor-branch-coverage"
    description = (
        "The executor branch-coverage floor is enforced only by a slow on-demand script, so nothing "
        "per-commit stops the committed floor from being set above the real measurement — a wishful floor "
        "that reads as protection but guards nothing. This asserts the floor is a valid integer percent "
        "that does not exceed the last recorded measurement, with its provenance kept."
    )

    def check(self) -> None:
        data = json.loads(_BASELINE.read_text(encoding="utf-8"))
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
