# Gridkin Scenario Format Specification (v0)

## Philosophy

Gridkin is TAP's scenario-driven test format for the Gryphon query language. A
Gridkin scenario pairs four eyeballable, committed artifacts: (a) a graph fixture,
(b) a Gryphon query, (c) the expected response envelope, and (d) the expected
ORM-compiled SQL the executor should produce. All four are files a human can read
end-to-end without traversing Python.

The format takes its name from Cucumber/Gherkin (the Given/When/Then BDD format
widely adopted across the testing ecosystem since ~2010) and from openCypher's
Technology Compatibility Kit (the Cucumber-based test corpus used by Neo4j,
Memgraph, RedisGraph, AgensGraph and others since ~2016). Gridkin is intentionally
*not* a port of either — it is a thin TAP-vocabulary scenario format whose shape
is designed for TAP's nested envelope responses, TAP's typed BaseModel data model,
and TAP's dimension partitioning. The precedent is named so future work can borrow
from it deliberately rather than discover the shape by accident.

This spec governs the **file format and runner contract**. The plugin that hosts
the Gridkin corpus — its playground node and edge vocabulary, its two-tier fixture
structure, and the runner's home — is specified in the companion
[spec-gryphon-playground-v0.md](spec-gryphon-playground-v0.md). The two specs are
designed to be read together; [`doc-dev-gryphon-wishlist.md`](../../../docs/misc/doc-dev-gryphon-wishlist.md)
is their shared operational companion.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Eyeballable    | Every Gridkin scenario is short committed files (graph + query + expected envelope + expected SQL) a human can read end-to-end |
| 2. | Oracle-bearing | Expected envelopes and SQL are hand-authored or independently computed — not derived from the executor under test |
| 3. | Snapshot-disciplined | Regenerating expected files requires explicit opt-in and human review of the diff before commit |
| 4. | Traceable      | Every scenario carries the spec requirement IDs it covers, producing a derived coverage matrix |
| 5. | Inspirable     | The openCypher TCK is studied as a scenario-mine for corner cases; no TCK queries or graphs are copied into Gridkin |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-gridkin-scenario-format | [Gridkin Scenario Format](#gridkin-scenario-format) | Implemented | The JSON shape of a `.gridkin.json` file |
| req-gridkin-runner-contract | [Gridkin Runner Contract](#gridkin-runner-contract) | Implemented | Discovery, loading, execution, and assertion behavior |
| req-gridkin-oracle-assertion | [Oracle Assertion Discipline](#oracle-assertion-discipline) | Implemented | Expected envelopes are independent of the executor under test |
| req-gridkin-snapshot-discipline | [Snapshot Regeneration Discipline](#snapshot-regeneration-discipline) | Implemented | Explicit opt-in and human review when regenerating |
| req-gridkin-explain-snapshot | [Explain SQL Snapshot](#explain-sql-snapshot) | Implemented | Each scenario commits the ORM-compiled SQL Gryphon emits |
| req-gridkin-req-traceability | [Requirement Traceability](#requirement-traceability) | Implemented | Every scenario cites the spec RIDs it covers |
| req-gridkin-tck-inspiration | [TCK as Scenario Inspiration](#tck-as-scenario-inspiration) | Implemented | Mine the openCypher TCK for corner-case intent; never port queries |
| req-gridkin-json-schema | [JSON Schema for Scenario Files](#json-schema-for-scenario-files) | Implemented | Author and validate-at-load a JSON Schema for the scenario format |
| req-gridkin-multi-fixture-load | [Multi-Fixture Background Loads](#multi-fixture-background-loads) | Approved for Development | `background.grift_fixture` accepts a list of fixture paths; the runner imports each in order |
| req-gridkin-nongoals | [v0 Non-Goals](#v0-non-goals) | Implemented | Explicitly deferred concerns |

### Gridkin Scenario Format
----
RID: `req-gridkin-scenario-format`
Status: `Implemented`

A Gridkin scenario file is a JSON document that defines one feature's worth of
test scenarios against a named fixture.

#### Implementation

The file lives at `plugins/gryphon_playground/scenarios/<feature>.gridkin.json`
and has the shape:

```json
{
  "feature": "Hub-and-spoke traversal returns the hub and its one-hop neighbors",
  "background": {
    "grift_fixture": "fixtures/sparse_dense.grift.json"
  },
  "scenarios": [
    {
      "name": "hub anchored by entity_id returns hub plus neighbors",
      "tags": ["hub-and-spoke", "traversal"],
      "covers": ["req-grid-traversal-lang-shape", "req-grid-traversal-lang-patterns"],
      "query": "MATCH (hub)-[e]-(neighbor) WHERE hub.entity_id = $entity_id RETURN hub, e, neighbor",
      "params": {"entity_id": "01999999-0000-7000-8000-0000000000a1"},
      "expected_envelope": "expected/hub_and_spoke_basic.expected.json",
      "expected_sql_snapshot": "expected/hub_and_spoke_basic.sql.txt"
    }
  ]
}
```

Field semantics:

- `feature` (string, required) — a human-readable description of the feature this
  file covers
- `background.grift_fixture` (string, required) — path (relative to the plugin
  root) to the GRIFT fixture that seeds the test database
- `scenarios` (array, required, at least one) — the list of scenarios in this
  feature
- `scenarios[].name` (string, required) — human-readable scenario name
- `scenarios[].tags` (array of strings, optional) — tags for selective test runs
  (e.g. `pytest -m gridkin -k hub-and-spoke`)
- `scenarios[].covers` (array of strings, required, at least one) — the spec RIDs
  and ACIDs this scenario exercises (drives the traceability matrix)
- `scenarios[].inspired_by` (string, optional) — breadcrumb to an openCypher TCK
  feature file when the scenario's intent was mined from the TCK; purely
  informational, never a license claim
- `scenarios[].layer` (string, optional) — the GRIFT subgraph return layer to
  execute the query at, one of `lite` / `full` / `extended`; defaults to `full`
- `scenarios[].query` (string, required) — the Gryphon query to execute
- `scenarios[].params` (object, optional) — runtime `$param` values for the query
- `scenarios[].expected_envelope` (string, required) — path to the JSON file
  holding the exact expected response envelope
- `scenarios[].expected_sql_snapshot` (string, required) — path to the text file
  holding the expected ORM-compiled SQL (see
  [req-gridkin-explain-snapshot](#explain-sql-snapshot))

The expected envelope file is a literal JSON document matching the canonical
three-lane envelope shape (`spec-grift-envelope.md`, `req-grift-envelope-shape`)
as emitted by the subgraph serializer for the requested layer. The three-lane
envelope landed in the serializer ahead of this spec; when its remaining
acceptance criteria settle, affected envelope side files are regenerated as a
coordinated change under the snapshot discipline.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-scenario-format-1 | All Required Fields Validated | Implemented | The runner rejects scenario files missing any required field, with a clear error pointing at the offending field. | |
| req-gridkin-scenario-format-2 | Expected Side Files Resolve | Implemented | The runner resolves `expected_envelope` and `expected_sql_snapshot` paths relative to the plugin root and fails loudly if either is missing. | |
| req-gridkin-scenario-format-3 | Covers Field Is Required Non-Empty | Implemented | Scenarios without at least one `covers` entry are rejected — traceability is binding, not optional. | |

### Gridkin Runner Contract
----
RID: `req-gridkin-runner-contract`
Status: `Implemented`

The runner is pytest-discoverable and follows a fixed lifecycle per scenario.

#### Implementation

For each scenario in each `.gridkin.json` file, the runner:

1. Loads the named Tier 1 fixture into the test database via the standard GRIFT
   importer (the same path real plugins use — no Gridkin-specific seed path)
2. Executes the scenario's Gryphon query with its `params`, capturing both the
   response envelope and — via the SQL-capture seam — the ordered, stage-labelled
   SQL the executor produced (see [req-gridkin-explain-snapshot](#explain-sql-snapshot))
3. Loads the expected envelope JSON and asserts deep equality against the actual
   response envelope
4. Loads the expected SQL text and asserts equality against the captured SQL
   (whitespace-normalized)
5. Reports separately on envelope mismatch vs. SQL mismatch — a scenario can fail
   on one without the other, and the failure mode tells you whether behavior
   changed or query plan changed

Discovery is by directory scan: any `*.gridkin.json` file under
`plugins/gryphon_playground/scenarios/` is discovered automatically. Tags are
surfaced as pytest markers for selective runs.

Loading isolation: each scenario starts from an empty test database, loads its
fixture, runs, and tears down. No state bleeds between scenarios. This is
intentionally slow — the priority is correctness signal, not test-suite speed.

Envelope equality is structural, not literal: `nodes` and `edges` are compared
as sets (a graph envelope's members are unordered, and the executor emits them
in DB-discretion order), and volatile provenance fields (`created_at`,
`updated_at`, `originating_grid_id`) are redacted before comparison — a scenario
asserts what a query returns, not when its fixture was imported or on which
grid. `rows` are compared in order.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-runner-contract-1 | Pytest Discoverable | Implemented | Gridkin scenarios appear as pytest tests and can be run via `pytest plugins/gryphon_playground/`. | |
| req-gridkin-runner-contract-2 | Per-Scenario Isolation | Implemented | Each scenario runs against a freshly-seeded test database; no inter-scenario state. | |
| req-gridkin-runner-contract-3 | Envelope and SQL Asserted Separately | Implemented | A scenario can fail on envelope mismatch, SQL mismatch, or both — each is reported distinctly. | |
| req-gridkin-runner-contract-4 | Uses Standard GRIFT Importer | Implemented | Fixtures load through the same path as real plugin GRIFT data — no Gridkin-specific seed shortcut. | |

### Oracle Assertion Discipline
----
RID: `req-gridkin-oracle-assertion`
Status: `Implemented`

The expected envelope and expected SQL files are oracles, not derivations.

#### Implementation

An "oracle" assertion is one where the expected value comes from an independent
source — hand-computation, hand-authorship, or a parallel implementation — rather
than from the system under test. The classic anti-pattern is: "run the system,
capture its output, commit the output as the expected, assert against future
runs." This catches *regressions* but cannot catch *systematic bugs the original
implementation already had* (an executor that overcounts by a consistent factor
will produce consistent overcounts forever, and every test will pass).

Gridkin requires the oracle discipline:

- Expected envelope files are either hand-authored or computed independently (raw
  ORM query, hand enumeration). The author of the expected file must be able to
  defend the contents on inspection.
- When a scenario is *new*, the expected envelope is written *before* the scenario
  runs against the implementation. If they disagree, both the implementation and
  the expected are reviewed — the implementation isn't assumed correct.
- When a feature *evolves* and existing scenarios need regenerated expecteds, the
  diff is reviewed line-by-line by a human (see
  [req-gridkin-snapshot-discipline](#snapshot-regeneration-discipline)).

The discipline is tractable only because fixtures are tiny (per
`spec-gryphon-playground-v0.md`, `req-gryphon-playground-fixtures`):
hand-enumerating the expected result of a query over a ten-entity graph is
feasible; over a thousand-entity graph it is not. Keeping Tier 1 fixtures small is
what makes the oracle real rather than aspirational.

The motivation is captured in `feedback_borrow_from_oss_prior_art`: every
well-known query engine's test suite (SQLite's sqllogictest, PostgreSQL's
golden-file regression suite, openCypher's TCK) treats expected values as
committed contracts authored with intent, not as captured snapshots.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-oracle-assertion-1 | Expected Files Are Contracts | Implemented | The convention that expected files represent intent (not capture) is documented in the plugin README and surfaced in `--update-snapshots` output. | |
| req-gridkin-oracle-assertion-2 | New Scenarios Author Expected First | Implemented | When introducing a scenario, author the expected envelope before observing the implementation's output. | Workflow norm, not runtime check |

### Snapshot Regeneration Discipline
----
RID: `req-gridkin-snapshot-discipline`
Status: `Implemented`

Regenerating expected files requires explicit opt-in and human review.

#### Implementation

The runner regenerates the expected envelope and expected SQL files from the
current implementation's output when the `GRIDKIN_UPDATE_SNAPSHOTS` environment
variable is set. Without it, mismatches are test failures. An environment
variable — rather than a pytest `--flag` — keeps the Gridkin tooling entirely
self-contained in the plugin (no `pytest_addoption` in the repo-root conftest).

The switch is **never** set automatically (no CI step regenerates snapshots; no
pre-commit hook regenerates snapshots). It is set by a developer who is
intentionally changing behavior, after which:

1. `git diff` shows the expected-file changes
2. The developer reads the diff and confirms each change is intended
3. The expected files are committed in the same change as the implementation
   change

The runner's output on `--update-snapshots` writes a banner to stderr reminding
the developer of the oracle discipline (per
[req-gridkin-oracle-assertion](#oracle-assertion-discipline)) — that capture
without review defeats the entire validation strategy.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-snapshot-discipline-1 | Update Flag Explicit | Implemented | Snapshot regeneration requires an explicit flag; no implicit regeneration path exists. | |
| req-gridkin-snapshot-discipline-2 | Update Banner Reminds Discipline | Implemented | The runner prints an oracle-discipline reminder when snapshots are regenerated. | |
| req-gridkin-snapshot-discipline-3 | No CI Regeneration | Implemented | No CI job or hook sets `GRIDKIN_UPDATE_SNAPSHOTS`; it is developer-only. | |

### Explain SQL Snapshot
----
RID: `req-gridkin-explain-snapshot`
Status: `Implemented`

Each scenario commits the exact ORM-compiled SQL the Gryphon executor produces for
its query.

#### Implementation

The Gryphon executor compiles each Gryphon query into **one or more** Django ORM
`QuerySet`s. A simple type scan produces a single QuerySet; multi-stage patterns
produce several — hub-and-spoke, for example, loads the anchor entity, then runs a
per-direction edge scan, then a bulk neighbor fetch — and a later stage is built
from an earlier stage's results. There is no single `QuerySet.query` that
represents "the query", so capture happens during execution, not as a pure
compile step.

Capture is done by the **SQL-capture seam in `tap_grid/gryphon/`** —
`capture_sql()` and `explain_gryphon_raw()`, specified in
`spec-grid-traversal-execution.md` (`req-grid-traversal-exec-sql-capture`). A
`connection.execute_wrapper` records every `SELECT` the executor issues during a
run, in execution order, each tagged with the dispatch stage that produced it
(`type-scan`, `hub-and-spoke`, `edge-type-scan`, `advanced`). Each captured
statement is the parameterized SQL plus its bound parameters, kept separate rather
than inlined — that is deterministic, sidesteps value-quoting edge cases, and
still reads cleanly (query shape and literal values shown distinctly). For the
capture to be byte-stable the executor sorts the id collections it filters with
`pk__in` before querying.

Gridkin captures that ordered, stage-labelled sequence and asserts it —
whitespace-normalized — against a committed `<scenario>.sql.txt` side file. The
side file is a **multi-statement document**: one labelled block per captured
`SELECT`, in execution order. A query that runs three statements has three blocks
in its `.sql.txt`.

The value of this assertion:

- **Eyeballable correctness check.** A developer (or the user) can read the
  committed SQL and judge whether it makes sense for the query without reading the
  executor source. This directly addresses the human-in-the-loop verifiability
  problem: a load-bearing system extended largely by AI, validated without the
  reviewer having to read every line of executor code.
- **Query-plan regression detection.** Refactors that change the executor's
  compilation strategy (different JOIN order, reverse-FK vs. explicit ID list, an
  added or dropped stage) show up as SQL diffs even when the response envelope is
  byte-identical. Sometimes that's intended (a perf improvement); sometimes it's a
  latent bug (a different JOIN shape that will inflate under a graph shape no
  current fixture exercises).
- **Shared infrastructure with `gryphon explain`.** The same capture seam backs
  the future `gryphon explain` developer surface (wishlist H3) — a CLI /
  management command that renders the compiled SQL for any query against the
  playground graph. The seam is built once, here, and reused.

The SQL is whitespace-normalized (collapsed whitespace runs, trimmed lines) so
trivial formatting changes don't churn snapshots. Everything else — table names,
column names, JOIN structure, WHERE clauses, inlined values, the stage labels, and
the block count and order — is asserted byte-exact after normalization.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-explain-snapshot-1 | SQL Captured Per Scenario | Implemented | Every Gridkin scenario commits an `expected_sql_snapshot` file. | |
| req-gridkin-explain-snapshot-2 | Whitespace Normalized | Implemented | The runner whitespace-normalizes both expected and actual SQL before comparing. | |
| req-gridkin-explain-snapshot-3 | Failure Distinct From Envelope Failure | Implemented | SQL mismatch is reported as a distinct failure mode from envelope mismatch. | |
| req-gridkin-explain-snapshot-4 | Multi-Statement Capture | Implemented | The `.sql.txt` side file holds one labelled block per `SELECT` the executor executes, in execution order; queries that run multiple statements capture all of them. | |

### Requirement Traceability
----
RID: `req-gridkin-req-traceability`
Status: `Implemented`

Every Gridkin scenario cites the spec RIDs it exercises.

#### Implementation

The `scenarios[].covers` field is required and must contain at least one RID or
ACID. The runner emits a derived coverage matrix on demand — set the
`GRIDKIN_COVERAGE` environment variable and the matrix prints in the pytest
terminal summary, listing for each cited RID the scenarios that cover it, and the
requirement-level RIDs in the Gryphon specs that no scenario covers.

This produces, for free, the requirement-traceability matrix that the Gryphon
validation audit identified as missing from current Gryphon tests.

`covers` is binding for new scenarios. Existing Gryphon tests (in
`tap_grid/tests/test_gryphon.py`) are not retroactively required to cite `covers`
— the traceability investment happens at the Gridkin boundary going forward.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-req-traceability-1 | Covers Required | Implemented | Scenario files without a `covers` field on every scenario fail to load. | |
| req-gridkin-req-traceability-2 | Coverage Matrix Generable | Implemented | A CLI command emits a coverage matrix mapping RID → covering scenarios. | |
| req-gridkin-req-traceability-3 | Gap Surfaced | Implemented | The coverage matrix flags any RID cited in a Gryphon spec that has zero covering Gridkin scenarios. | Drives prioritization |

### TCK as Scenario Inspiration
----
RID: `req-gridkin-tck-inspiration`
Status: `Implemented`

The openCypher Technology Compatibility Kit is mined for corner-case intent. No
TCK content is copied into Gridkin.

#### Implementation

When authoring Gridkin scenarios for a Gryphon feature, the recommended workflow
is:

1. Identify the openCypher TCK feature folder corresponding to the feature being
   implemented (e.g. `tck/features/clauses/optional-match/` for OPTIONAL MATCH)
2. Read each scenario file in that folder for its *intent* — what corner case is
   it pinning down? What historical confusion does it guard against? (TCK
   scenarios exist because real graph engines historically broke on real edge
   cases.)
3. Write a short notes list of corner-case intents that apply to Gryphon's
   semantics. Skip intents that are Cypher-specific quirks (null comparison
   semantics, list comprehensions, etc.) — those are not Gryphon's contract.
4. Author Gridkin scenarios in TAP vocabulary covering each retained corner case.
   The query is written in Gryphon syntax against the `pg_*` playground
   vocabulary; the graph fixture is hand-authored; the expected envelope is
   hand-authored per [req-gridkin-oracle-assertion](#oracle-assertion-discipline).
5. Set the scenario's `inspired_by` field to the TCK feature folder path. This is
   an attribution breadcrumb — it lets future-us trace which corner-case
   taxonomies have been mined and which haven't.

Constraints:

- **No TCK query text appears in any Gridkin scenario.** Even verbatim-equivalent
  Cypher (`MATCH (a)-[:KNOWS]->(b)`) is rewritten in TAP vocabulary (`MATCH
  (a:pg_node)-[:PG_LINKS]->(b:pg_node)`). Per `feedback_borrow_from_oss_prior_art`,
  inspiration only; clean-room reimplementation in our own words.
- **No TCK graph data is reused.** Playground fixtures use playground node types;
  TCK graph data is property-bag and doesn't translate.
- **No TCK expected results are reused.** They reflect Cypher semantics; Gridkin
  asserts against Gryphon semantics.

The legal posture: the openCypher TCK is Apache 2.0 licensed and could be reused
with attribution. Gridkin chooses not to — the project standing rule is
clean-room reimplementation regardless of license permissions. The breadcrumb is
intellectual honesty, not legal cover.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-tck-inspiration-1 | Inspired-By Breadcrumb Convention | Implemented | When a Gridkin scenario's intent was mined from a TCK feature, the scenario's `inspired_by` field cites the source folder. | |
| req-gridkin-tck-inspiration-2 | No TCK Content Copied | Implemented | No TCK query text, graph data, or expected results appear in any Gridkin file. | |
| req-gridkin-tck-inspiration-3 | Cypher-Specific Quirks Excluded | Implemented | Scenario authors filter TCK intent for applicability to Gryphon semantics; Cypher-specific behaviors are not inherited. | |

#### Future

Long-horizon seam: when TAP's satellite system arrives (per
`project_satellite_system_vision`), Gridkin becomes the natural contract for
satellite query authors — the same role openCypher's TCK serves for multi-engine
Cypher compatibility. The scenario format is designed so that this evolution is
structural, not a rewrite. Until that demand signal arrives, Gridkin is
internal-only.

### JSON Schema for Scenario Files
----
RID: `req-gridkin-json-schema`
Status: `Implemented`

The Gridkin scenario format is a new structured-data format and ships with a JSON
Schema validated at load.

#### Implementation

Per the standing rule (`feedback_json_formats_need_schema`, mirrored in AGENTS.md
Core TAP Rules): every new structured-data format authors a JSON Schema in the
same change that introduces the format, and the runner validates each scenario
file against the schema on load — failing loud on violations rather than silently
coercing.

The schema lives at
`plugins/gryphon_playground/scenarios/gridkin-scenario.schema.json` (sibling to
the scenario files it governs). The runner loads it once and validates every
`.gridkin.json` against it before parsing.

This requirement is bound to the runner work — the schema and the runner are
designed and shipped together.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-json-schema-1 | Schema Authored Same-Change | Implemented | The schema is written in the same change that introduces the runner — not a follow-up. | |
| req-gridkin-json-schema-2 | Validation On Load | Implemented | Every scenario file is validated against the schema before its contents are used; invalid files fail loudly. | |

### Multi-Fixture Background Loads
----
RID: `req-gridkin-multi-fixture-load`
Status: `Approved for Development`

`background.grift_fixture` accepts either a single path (the existing form) or an ordered array of paths. When the array form is used, the runner imports each fixture in order during the seed phase. This unlocks scenarios that need pre-existing state for the flow under test — the canonical motivating case is optimistic concurrency (`req-grift-concurrency-version`), where the interesting OCC paths require an entity to exist before a subsequent fixture declares an `entity_expected_version` against it.

#### Implementation

The schema relaxes `background.grift_fixture` to `oneOf` `{string, array of strings (minItems 1)}`. The loader normalizes both forms into a `tuple[Path, ...]` on the `Scenario` dataclass (renamed `fixture_path` → `fixture_paths`). The runner's seed phase loops over the tuple and imports each fixture with the same contract the single-fixture form has today: every fixture must satisfy `result.success and not result.errors`, or the scenario fails loudly with the offending fixture's name in the error message.

Soft-delete directives in `background.soft_delete` apply once after the last fixture finishes loading. They are not interleaved between fixtures and there is no per-fixture override.

#### Boundaries

- Every fixture in the sequence must import cleanly. The harness does not yet support expected-failure fixtures (e.g. "fixture #2 is supposed to fail with `entity_version_conflict`"); that pattern stays in pytest where multi-call + assertion machinery is well-trodden.
- No per-fixture options. All fixtures load with the same `dangling_edge_mode="strict"` the runner uses today. Adding per-fixture options is a future seam, not a v0 concern.
- The order of fixtures is significant. The loader preserves declaration order; the runner imports in that order. Re-ordering a fixture array changes the test.

#### Backward Compatibility

The single-string form remains valid and behaves identically to today. No existing scenario needs to change. The change is purely additive to the schema's permitted shape.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-multi-fixture-load-1 | String Or Array | Approved for Development | `background.grift_fixture` validates as either a string or an array of strings with at least one element. | Schema `oneOf` constraint. |
| req-gridkin-multi-fixture-load-2 | Normalized Loader Surface | Approved for Development | The `Scenario` dataclass exposes `fixture_paths: tuple[Path, ...]` regardless of the source form. Single-string fixtures yield a one-element tuple. | |
| req-gridkin-multi-fixture-load-3 | Sequential Import | Approved for Development | The runner imports each fixture in declared order via `grift_import(...)`; every fixture must succeed cleanly. | Same import-cleanly contract as single-fixture. |
| req-gridkin-multi-fixture-load-4 | Soft-Delete After All Fixtures | Approved for Development | `background.soft_delete` runs once, after the last fixture finishes loading. | Soft-deletes are not interleaved or per-fixture. |
| req-gridkin-multi-fixture-load-5 | Backward Compatible | Approved for Development | Existing scenarios using the single-string form continue to work unchanged. | Purely additive change to the schema. |

### v0 Non-Goals
----
RID: `req-gridkin-nongoals`
Status: `Implemented`

Concerns explicitly excluded from Gridkin v0:

- **Cypher subset compatibility claim.** Gridkin asserts Gryphon's behavior
  against intent we authored; it makes no claim that Gryphon implements any
  portion of Cypher to spec.
- **Write-side testing.** Gryphon is read-only; Gridkin tests read behavior only.
  CREATE/MERGE/DELETE/SET are not in Gryphon's grammar and have no Gridkin
  coverage.
- **Performance / scale testing.** Gridkin fixtures are small. Benchmarking and
  large-graph behavior are deferred until a demand signal arrives.
- **Property-based / fuzz testing.** Tools like SQLancer's TLP/NoREC and
  sqlsmith-style query generators are powerful but premature; deferred until
  Gryphon's surface is stable.
- **Public conformance kit.** Gridkin is internal. When the satellite system
  arrives it may evolve into a public contract; the format is designed not to
  preclude that, but no public-facing work happens in v0.
- **Mechanical TCK port.** The TCK is mined for intent only; mechanical
  translation (parse Gherkin, translate Cypher to Gryphon, translate property-bag
  graphs to BaseModel envelopes) is not pursued. The translation cost is high and
  the value below the bar until external compatibility becomes a demand.
- **Backward compatibility with the existing `test_gryphon.py` suite.** Gridkin
  does not replace the existing executor tests; it complements them. The existing
  suite is not retroactively migrated.
- **CI integration.** Wiring Gridkin into the multi-session promote-gate happens
  after the runner exists and the CI surface is built — not part of v0.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-nongoals-1 | Non-Goals Documented | Implemented | The plugin README links to this section so contributors find the non-goals before proposing scope expansion. | |

## Status Vocabulary

| Status States |  |
| --- | --- |
| Proposed | Requirement is accepted and ready to be implemented |
| In Development | Implementation is underway |
| Implemented | Requirement is implemented |
| Verified | Implementation is implemented and independently verified |
| Refactoring |  |
| Deprecating |  |
| Deprecated | Not part of the current architecture and should not be implemented |
