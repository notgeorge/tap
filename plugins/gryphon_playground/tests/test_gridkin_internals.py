"""Unit tests for the Gridkin runner internals.

These exercise the runner mechanics — JSON Schema validation, SQL
normalization, the coverage matrix — without a database. Full-scenario
integration is `test_gridkin.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plugins.gryphon_playground.gridkin import coverage, loader
from plugins.gryphon_playground.gridkin.loader import GridkinScenarioError, Scenario
from plugins.gryphon_playground.gridkin.runner import normalize_sql

_VALID_SCENARIO = {
    "feature": "Type scan returns every node of a type",
    "background": {"grift_fixture": "fixtures/sparse_dense.grift.json"},
    "scenarios": [
        {
            "name": "scan returns all pg_node entities",
            "covers": ["req-grid-traversal-lang-shape"],
            "query": "MATCH (n:pg_node) RETURN n",
            "expected_envelope": "expected/type_scan.expected.json",
            "expected_sql_snapshot": "expected/type_scan.sql.txt",
        }
    ],
}


def _write(tmp_path: Path, name: str, document: object) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


class TestNormalizeSql:
    def test_collapses_whitespace_runs(self):
        assert normalize_sql("SELECT   a,    b") == "SELECT a, b"

    def test_trims_lines_and_drops_blanks(self):
        assert normalize_sql("  SELECT a \n\n   FROM t  \n") == "SELECT a\nFROM t"

    def test_empty_input_is_empty(self):
        assert normalize_sql("   \n  \n") == ""


class TestSchemaValidation:
    def test_accepts_a_minimal_valid_file(self, tmp_path):
        _write(tmp_path, "type_scan.gridkin.json", _VALID_SCENARIO)
        scenarios = loader.discover_scenarios(tmp_path)
        assert len(scenarios) == 1
        assert scenarios[0].name == "scan returns all pg_node entities"
        assert scenarios[0].layer == "full"  # default applied

    def test_rejects_missing_required_field(self, tmp_path):
        bad = json.loads(json.dumps(_VALID_SCENARIO))
        del bad["scenarios"][0]["query"]
        _write(tmp_path, "bad.gridkin.json", bad)
        with pytest.raises(GridkinScenarioError, match="schema violation"):
            loader.discover_scenarios(tmp_path)

    def test_rejects_unknown_field(self, tmp_path):
        bad = json.loads(json.dumps(_VALID_SCENARIO))
        bad["scenarios"][0]["typo_field"] = "oops"
        _write(tmp_path, "bad.gridkin.json", bad)
        with pytest.raises(GridkinScenarioError, match="schema violation"):
            loader.discover_scenarios(tmp_path)

    def test_rejects_empty_covers(self, tmp_path):
        bad = json.loads(json.dumps(_VALID_SCENARIO))
        bad["scenarios"][0]["covers"] = []
        _write(tmp_path, "bad.gridkin.json", bad)
        with pytest.raises(GridkinScenarioError, match="schema violation"):
            loader.discover_scenarios(tmp_path)

    def test_rejects_invalid_json(self, tmp_path):
        (tmp_path / "bad.gridkin.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(GridkinScenarioError, match="invalid JSON"):
            loader.discover_scenarios(tmp_path)

    def test_empty_directory_yields_no_scenarios(self, tmp_path):
        assert loader.discover_scenarios(tmp_path) == []


def _scenario(scenario_id: str, covers: tuple[str, ...]) -> Scenario:
    base = Scenario(
        scenario_id=scenario_id,
        feature="f",
        name=scenario_id,
        tags=(),
        covers=covers,
        inspired_by=None,
        layer="full",
        query="MATCH (n:pg_node) RETURN n",
        params={},
        fixture_path=Path("x"),
        expected_envelope_path=Path("x"),
        expected_sql_path=Path("x"),
        source_file=Path("x"),
    )
    return base


class TestCoverageMatrix:
    def test_maps_rid_to_covering_scenarios(self):
        scenarios = [
            _scenario("a", ("req-grid-traversal-lang-shape",)),
            _scenario("b", ("req-grid-traversal-lang-shape", "req-grid-traversal-lang-patterns")),
        ]
        matrix = coverage.build_matrix(scenarios)
        assert matrix["req-grid-traversal-lang-shape"] == ["a", "b"]
        assert matrix["req-grid-traversal-lang-patterns"] == ["b"]

    def test_render_reports_uncovered_requirements(self):
        # The capture-seam RID exists in the execution spec and is covered by
        # nothing here, so it must show up in the uncovered gap list.
        report = coverage.render([_scenario("a", ("req-grid-traversal-lang-shape",))])
        assert "req-grid-traversal-exec-sql-capture" in report
        assert "Uncovered Gryphon-spec requirements" in report
