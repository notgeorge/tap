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


def gryphon_spec_rids() -> set[str]:
    """All requirement-level `req-grid-*` RIDs declared across the Gryphon specs."""
    rids: set[str] = set()
    for spec in _GRYPHON_SPECS:
        if spec.is_file():
            for rid in _RID_RE.findall(spec.read_text(encoding="utf-8")):
                if not _ACID_TAIL_RE.search(rid):
                    rids.add(rid)
    return rids


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
    return "\n".join(lines)
