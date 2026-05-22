"""Gridkin pytest integration for the gryphon_playground plugin.

Registers the `gridkin` marker and, at session end, emits the snapshot-discipline
reminder and / or the requirement-traceability coverage matrix when their
environment switches are set:

- GRIDKIN_UPDATE_SNAPSHOTS=1 — regenerate expected oracle files (see test_gridkin).
- GRIDKIN_COVERAGE=1        — print the RID -> covering-scenarios matrix.

Environment switches (not pytest `--flags`) keep the Gridkin tooling entirely
self-contained within the plugin — no `pytest_addoption` in the repo-root
conftest. Per spec-gridkin-v0.md req-gridkin-snapshot-discipline / -req-traceability.
"""

from __future__ import annotations

from plugins.gryphon_playground.gridkin import coverage, loader

_ORACLE_REMINDER = (
    "GRIDKIN_UPDATE_SNAPSHOTS was set — expected envelope / SQL files were\n"
    "regenerated from the current executor output. Expected files are ORACLES,\n"
    "not captures: review every line of the `git diff` before committing. A\n"
    "captured expected that nobody read cannot catch a systematic bug the\n"
    "executor already has (spec-gridkin-v0.md req-gridkin-oracle-assertion)."
)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "gridkin: a Gridkin scenario test for the Gryphon query language.",
    )


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if loader.env_flag("GRIDKIN_UPDATE_SNAPSHOTS"):
        terminalreporter.section("Gridkin — snapshots regenerated")
        terminalreporter.write_line(_ORACLE_REMINDER)
    if loader.env_flag("GRIDKIN_COVERAGE"):
        terminalreporter.section("Gridkin — requirement coverage")
        terminalreporter.write_line(coverage.render(loader.discover_scenarios()))
