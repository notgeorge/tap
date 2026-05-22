"""Gridkin requirement-traceability coverage matrix.

Maps each spec RID cited in a scenario's `covers` field to the scenarios that
cover it, and flags Gryphon-spec RIDs that no scenario covers — the derived
traceability matrix the Gryphon validation audit identified as missing.

Per spec-gridkin-v0.md: req-gridkin-req-traceability.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING

from plugins.gryphon_playground.gridkin.loader import PLUGIN_ROOT

if TYPE_CHECKING:
    from plugins.gryphon_playground.gridkin.loader import Scenario

_REPO_ROOT = PLUGIN_ROOT.parent.parent

# The Gryphon-language spec files whose requirements the matrix reports against.
_GRYPHON_SPECS = (
    _REPO_ROOT / "tap_grid" / "specs" / "spec-grid-traversal-language.md",
    _REPO_ROOT / "tap_grid" / "specs" / "spec-grid-traversal-execution.md",
    _REPO_ROOT / "tap_grid" / "specs" / "spec-grid-gryphon-multihop-aggregation.md",
)

_RID_RE = re.compile(r"\breq-grid-[a-z0-9.]+(?:-[a-z0-9.]+)*\b")
# An ACID is a RID with a trailing -<number>; the gap report tracks
# requirement-level RIDs, not individual acceptance criteria.
_ACID_TAIL_RE = re.compile(r"-\d+$")


def build_matrix(scenarios: Iterable[Scenario]) -> dict[str, list[str]]:
    """RID -> sorted list of scenario_ids that cover it."""
    matrix: dict[str, list[str]] = {}
    for scenario in scenarios:
        for rid in scenario.covers:
            matrix.setdefault(rid, []).append(scenario.scenario_id)
    return {rid: sorted(ids) for rid, ids in sorted(matrix.items())}


def gryphon_spec_ids() -> set[str]:
    """Every `req-grid-*` id — requirement RIDs and ACIDs — in the Gryphon specs.

    Used to flag `covers` entries that match no real spec id (a typo or a
    stale id) — an unvalidated `covers` would otherwise count as false coverage.
    """
    ids: set[str] = set()
    for spec in _GRYPHON_SPECS:
        if spec.is_file():
            ids.update(_RID_RE.findall(spec.read_text(encoding="utf-8")))
    return ids


def gryphon_spec_rids() -> set[str]:
    """Requirement-level RIDs only (ACIDs filtered out) — for the gap list."""
    return {sid for sid in gryphon_spec_ids() if not _ACID_TAIL_RE.search(sid)}


def render(scenarios: Iterable[Scenario]) -> str:
    """Render the coverage matrix and the uncovered-RID gap list as text."""
    scenarios = list(scenarios)
    matrix = build_matrix(scenarios)
    covered = set(matrix)
    uncovered = sorted(gryphon_spec_rids() - covered)

    lines: list[str] = [
        f"{len(scenarios)} scenario(s) cover {len(covered)} requirement / ACID id(s).",
        "",
    ]
    if matrix:
        lines.append("Covered:")
        for rid, ids in matrix.items():
            lines.append(f"  {rid}")
            for scenario_id in ids:
                lines.append(f"      {scenario_id}")
    else:
        lines.append("Covered: (none — no scenarios discovered)")
    lines.append("")
    if uncovered:
        lines.append(f"Uncovered Gryphon-spec requirements ({len(uncovered)}):")
        lines.extend(f"  {rid}" for rid in uncovered)
    else:
        lines.append("Uncovered Gryphon-spec requirements: (none)")

    # Flag covers entries that match no real spec id — a typo or stale id would
    # otherwise sit in the matrix above as false coverage.
    cited = {rid for scenario in scenarios for rid in scenario.covers}
    unrecognized = sorted(cited - gryphon_spec_ids())
    lines.append("")
    if unrecognized:
        lines.append(f"Unrecognized `covers` ids — typo or stale ({len(unrecognized)}):")
        lines.extend(f"  {rid}" for rid in unrecognized)
    else:
        lines.append("Unrecognized `covers` ids: (none)")
    return "\n".join(lines)
