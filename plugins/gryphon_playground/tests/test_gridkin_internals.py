"""Unit tests for the Gridkin runner internals.

These exercise the runner mechanics — JSON Schema validation, SQL
normalization, the coverage matrix — without a database. Full-scenario
integration is `test_gridkin.py`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from plugins.gryphon_playground.gridkin import coverage, loader, stage_coverage
from plugins.gryphon_playground.gridkin.loader import GridkinScenarioError, Scenario
from plugins.gryphon_playground.gridkin.runner import normalize_sql
from tap.jsonfiles import load_json_file, load_schema

_VALID_SCENARIO = {
    "feature": "Type scan returns every node of a type",
    "background": {"grift_fixture": "fixtures/sparse_dense.grift.json"},
    "scenarios": [
        {
            "name": "scan returns all pg_node entities",
            "covers": ["req-grid-traversal-lang-shape"],
            "inspired_by": "opencypher TCK — clauses/match (full label scan)",
            "query": "MATCH (n:gryphon_playground__pg_node) RETURN n",
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
        with pytest.raises(GridkinScenarioError, match="schema validation"):
            loader.discover_scenarios(tmp_path)

    def test_rejects_unknown_field(self, tmp_path):
        bad = json.loads(json.dumps(_VALID_SCENARIO))
        bad["scenarios"][0]["typo_field"] = "oops"
        _write(tmp_path, "bad.gridkin.json", bad)
        with pytest.raises(GridkinScenarioError, match="schema validation"):
            loader.discover_scenarios(tmp_path)

    def test_rejects_empty_covers(self, tmp_path):
        bad = json.loads(json.dumps(_VALID_SCENARIO))
        bad["scenarios"][0]["covers"] = []
        _write(tmp_path, "bad.gridkin.json", bad)
        with pytest.raises(GridkinScenarioError, match="schema validation"):
            loader.discover_scenarios(tmp_path)

    def test_rejects_missing_inspired_by(self, tmp_path):
        # Anti-drift guard (req-grid-traversal-lang-tck-mining-3): a forgotten
        # TCK mining pass — a scenario with no breadcrumb — fails loudly.
        bad = json.loads(json.dumps(_VALID_SCENARIO))
        del bad["scenarios"][0]["inspired_by"]
        _write(tmp_path, "bad.gridkin.json", bad)
        with pytest.raises(GridkinScenarioError, match="schema validation"):
            loader.discover_scenarios(tmp_path)

    def test_rejects_malformed_inspired_by(self, tmp_path):
        # A non-empty but non-conforming breadcrumb (e.g. a TODO) is rejected:
        # the author must write a folder cite or the explicit empty-pass marker.
        bad = json.loads(json.dumps(_VALID_SCENARIO))
        bad["scenarios"][0]["inspired_by"] = "TODO: mine the TCK"
        _write(tmp_path, "bad.gridkin.json", bad)
        with pytest.raises(GridkinScenarioError, match="schema validation"):
            loader.discover_scenarios(tmp_path)

    def test_accepts_empty_pass_marker(self, tmp_path):
        # "Looked, found nothing" is a deliberate, recorded state for a
        # TAP-native feature with no TCK analog — and must be accepted.
        ok = json.loads(json.dumps(_VALID_SCENARIO))
        ok["scenarios"][0][
            "inspired_by"
        ] = "opencypher TCK — no applicable feature folder (TAP-native: soft-delete visibility filter)"
        _write(tmp_path, "ok.gridkin.json", ok)
        scenarios = loader.discover_scenarios(tmp_path)
        assert len(scenarios) == 1

    def test_every_shipped_scenario_carries_a_tck_breadcrumb(self):
        # The corpus-level guard: loading the real scenario directory validates
        # every shipped scenario against the schema (which requires a conforming
        # `inspired_by`). A new scenario that skips the mining pass breaks this.
        scenarios = loader.discover_scenarios()
        missing = [s.name for s in scenarios if not s.inspired_by]
        assert not missing, (
            "Gridkin scenarios missing the openCypher-TCK breadcrumb — run the "
            "mining pass per req-gridkin-tck-inspiration / build-gryphon-capability "
            "Step 8, then cite the folder or record the empty-pass marker: " + ", ".join(missing)
        )


_FOLDER_RE = re.compile(r"^opencypher TCK — ([a-zA-Z][a-zA-Z-]*/[a-zA-Z][a-zA-Z-]*)")


def _cited_folder(inspired_by: str) -> str | None:
    """Extract the TCK folder from a folder-cite breadcrumb, or None for an
    empty-pass ('no applicable feature folder ...') marker."""
    match = _FOLDER_RE.match(inspired_by)
    return match.group(1) if match else None


class TestTckCoverageLedger:
    """Guard for the corpus-wide TCK coverage ledger (req-gridkin-tck-coverage).

    The ledger answers 'how much of each TCK folder did we carry over' with an
    auditable, machine-checked record. `covered` is DERIVED here (scenarios
    citing the folder), never stored — so the x/y ratio cannot silently lie.
    """

    LEDGER = loader.SCENARIOS_DIR / "gryphon_playground.tck-coverage.json"
    LEDGER_SCHEMA = loader.SCENARIOS_DIR / "tck-coverage.schema.json"

    def _load_ledger(self):
        return load_json_file(self.LEDGER, schema=load_schema(self.LEDGER_SCHEMA))

    def test_ledger_validates_against_its_schema(self):
        ledger = self._load_ledger()
        assert ledger["folders"], "coverage ledger has no folder entries"

    def test_every_cited_folder_has_a_ledger_entry(self):
        # Forgotten-mining guard: a scenario citing a TCK folder with no ledger
        # entry means a folder was used without recording its coverage state.
        scenarios = loader.discover_scenarios()
        cited = {f for s in scenarios if (f := _cited_folder(s.inspired_by or ""))}
        ledgered = {entry["folder"] for entry in self._load_ledger()["folders"]}
        missing = cited - ledgered
        assert not missing, (
            "TCK folders cited by scenarios but absent from the coverage ledger — "
            "run the folder's mining pass and add its ledger entry: " + ", ".join(sorted(missing))
        )

    def test_no_orphan_ledger_entries(self):
        # Orphan guard: a ledger folder no scenario cites is stale (or its last
        # scenario was removed) and should be pruned or backfilled.
        scenarios = loader.discover_scenarios()
        cited = {f for s in scenarios if (f := _cited_folder(s.inspired_by or ""))}
        ledgered = {entry["folder"] for entry in self._load_ledger()["folders"]}
        orphans = ledgered - cited
        assert not orphans, "the coverage ledger lists folders no scenario cites (stale entries): " + ", ".join(
            sorted(orphans)
        )

    def test_no_applicable_folder_features_use_the_empty_pass_marker(self):
        # Every feature recorded as having no TCK analog must actually exist and
        # carry the empty-pass breadcrumb on its scenarios.
        ledger = self._load_ledger()
        by_file: dict[str, list[str]] = {}
        for scenario in loader.discover_scenarios():
            stem = scenario.source_file.name.replace(".gridkin.json", "")
            by_file.setdefault(stem, []).append(scenario.inspired_by or "")
        for entry in ledger.get("no_applicable_folder", []):
            feature = entry["feature"]
            assert feature in by_file, f"no_applicable_folder lists unknown feature {feature!r}"
            non_empty = [b for b in by_file[feature] if _cited_folder(b) is not None]
            assert not non_empty, (
                f"{feature} is recorded as having no applicable TCK folder but a " f"scenario cites one: {non_empty}"
            )

    def test_carried_over_ratio_is_derivable(self):
        # x/y carried-over = covered / (covered + open gaps), with covered derived
        # live. Asserts each ledger folder has at least one covering scenario (it
        # is cited) — i.e. the ratio is well-formed and never 0/y.
        scenarios = loader.discover_scenarios()
        covered_counts: dict[str, int] = {}
        for s in scenarios:
            folder = _cited_folder(s.inspired_by or "")
            if folder:
                covered_counts[folder] = covered_counts.get(folder, 0) + 1
        for entry in self._load_ledger()["folders"]:
            covered = covered_counts.get(entry["folder"], 0)
            assert covered >= 1, f"ledger folder {entry['folder']} has no covering scenario"

    def test_rejects_invalid_json(self, tmp_path):
        (tmp_path / "bad.gridkin.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(GridkinScenarioError, match="invalid JSON"):
            loader.discover_scenarios(tmp_path)

    def test_empty_directory_yields_no_scenarios(self, tmp_path):
        assert loader.discover_scenarios(tmp_path) == []

    def test_accepts_a_rejection_scenario(self, tmp_path):
        # A rejection scenario asserts the query is refused — expected_error
        # instead of an envelope/SQL pair.
        doc = json.loads(json.dumps(_VALID_SCENARIO))
        sc = doc["scenarios"][0]
        del sc["expected_envelope"]
        del sc["expected_sql_snapshot"]
        sc["expected_error"] = {"type": "GryphonParseError", "message_contains": "LIMIT"}
        _write(tmp_path, "reject.gridkin.json", doc)
        scenarios = loader.discover_scenarios(tmp_path)
        assert len(scenarios) == 1
        assert scenarios[0].expected_error == {"type": "GryphonParseError", "message_contains": "LIMIT"}
        assert scenarios[0].expected_envelope_path is None

    def test_rejects_scenario_with_both_envelope_and_error(self, tmp_path):
        # The two modes are mutually exclusive.
        doc = json.loads(json.dumps(_VALID_SCENARIO))
        doc["scenarios"][0]["expected_error"] = {"type": "GryphonParseError"}
        _write(tmp_path, "bad.gridkin.json", doc)
        with pytest.raises(GridkinScenarioError, match="schema validation"):
            loader.discover_scenarios(tmp_path)

    def test_rejects_scenario_with_neither_envelope_nor_error(self, tmp_path):
        doc = json.loads(json.dumps(_VALID_SCENARIO))
        del doc["scenarios"][0]["expected_envelope"]
        del doc["scenarios"][0]["expected_sql_snapshot"]
        _write(tmp_path, "bad.gridkin.json", doc)
        with pytest.raises(GridkinScenarioError, match="schema validation"):
            loader.discover_scenarios(tmp_path)


def _scenario(scenario_id: str, covers: tuple[str, ...]) -> Scenario:
    base = Scenario(
        scenario_id=scenario_id,
        feature="f",
        name=scenario_id,
        tags=(),
        covers=covers,
        inspired_by=None,
        layer="full",
        query="MATCH (n:gryphon_playground__pg_node) RETURN n",
        params={},
        fixture_paths=(Path("x"),),
        expected_envelope_path=Path("x"),
        expected_sql_path=Path("x"),
        source_file=Path("x"),
    )
    return base


class TestStageCoverage:
    """Empirical executor-stage coverage gate (the intent≠path-coverage AAR).

    The dispatch-path set is derived from the executor source (every
    `gryphon_stage("...")` call), the exercised set from the committed SQL
    snapshots. The gate is sharpened past reachability: each stage must be
    exercised by a scenario that *carries a WHERE* — the property whose absence
    on the edge-type-scan path was the envelope-WHERE silent-drop bug.
    """

    def test_every_dispatch_stage_is_exercised_with_a_where(self):
        enumerated = stage_coverage.enumerate_stage_labels()
        _, with_where = stage_coverage.where_exercised_stages(loader.discover_scenarios())
        uncovered = enumerated - with_where
        assert not uncovered, (
            "executor dispatch stages never exercised by a WHERE-carrying result "
            f"scenario: {sorted(uncovered)}. Each stage applies a WHERE; a stage "
            "reached only without one is the envelope-WHERE blind spot the "
            "intent≠path-coverage AAR names. Author a WHERE-carrying scenario that "
            "routes through it (see stage_coverage.py)."
        )

    def test_no_snapshot_stage_is_unknown_to_the_executor(self):
        # Drift axis: a stage label in a committed snapshot that the executor no
        # longer emits (renamed / removed) is a stale snapshot or a typo.
        enumerated = stage_coverage.enumerate_stage_labels()
        seen, _ = stage_coverage.where_exercised_stages(loader.discover_scenarios())
        stale = seen - enumerated
        assert not stale, (
            "SQL snapshots record stage labels the executor source no longer emits "
            f"(regenerate the snapshots or fix the label): {sorted(stale)}"
        )

    def test_known_dispatch_stages_are_acknowledged(self):
        # Tripwire: adding or removing a dispatch stage changes this set, forcing
        # the author to confront the new path's coverage rather than let it slip in
        # untested. The WHERE-coverage test above already fails for an unexercised
        # new stage; this pins the inventory so the change is deliberate.
        assert stage_coverage.enumerate_stage_labels() == {
            "optional-match",
            "advanced",
            "bare-type-scan",
            "type-scan",
            "single-hop",
        }

    def test_enumerate_stage_labels_rejects_a_non_literal(self, tmp_path):
        source = tmp_path / "fake_executor.py"
        source.write_text("label = 'x'\ngryphon_stage(label)\n", encoding="utf-8")
        with pytest.raises(ValueError, match="non-literal stage label"):
            stage_coverage.enumerate_stage_labels(source)

    def test_snapshot_stages_parses_the_header_lines(self):
        text = "-- statement 1 · stage: single-hop\nSELECT 1\n\n-- statement 2 · stage: advanced\nSELECT 2\n"
        assert stage_coverage.snapshot_stages(text) == {"single-hop", "advanced"}

    def test_query_carries_where_counts_not_exists_inner(self):
        # A NOT EXISTS with only an inner WHERE still exercises the advanced
        # stage's WHERE-application path, so it counts as WHERE-carrying.
        no_where = "MATCH (n:gryphon_playground__pg_node) RETURN n"
        outer_where = "MATCH (n:gryphon_playground__pg_node) WHERE n.data.severity_score > 1 RETURN n"
        inner_only = (
            "MATCH (s)-[:PG_LINKS__gryphon_playground]->(t) "
            "NOT EXISTS { MATCH (g:gryphon_playground__pg_node)-[:PG_OPTIONAL__gryphon_playground]->(t) "
            "WHERE g.data.severity_score > 100 }"
        )
        assert not stage_coverage.query_carries_where(no_where)
        assert stage_coverage.query_carries_where(outer_where)
        assert stage_coverage.query_carries_where(inner_only)


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
