"""Gridkin — the scenario-driven test runner for the Gryphon query language.

This package is the runner *library* for the Gridkin scenario format
(specs/spec-gridkin-v0.md):

- `loader`   — discover `scenarios/*.gridkin.json`, validate against the JSON
               Schema, parse into `Scenario` objects.
- `runner`   — seed a scenario's GRIFT fixture, execute the query, compare the
               response envelope and the captured SQL against oracle files.
- `coverage` — the requirement-traceability matrix (RID -> covering scenarios).

The pytest entry point is `tests/test_gridkin.py`, which parametrizes one test
item per discovered scenario.
"""
