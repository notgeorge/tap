# Gridkin Playground Plugin Specification (v0)

## Philosophy

Gridkin is TAP's scenario-driven test format for the Gryphon query language. The format pairs (a) committed graph fixtures, (b) a Gryphon query, (c) the expected response envelope, and (d) the expected ORM-compiled SQL the executor should produce — all as eyeballable artifacts that a human can read without traversing Python.

The `gridkin_playground` plugin is the home for those artifacts. It registers bespoke node and edge types designed *only* to exercise query patterns — cycles, self-loops, multi-edges, sparse/dense regions, optional relationships, dimension partitions. Keeping the playground decoupled from real domain models (lotr, aws_core, samsite) means Gridkin scenarios don't accidentally constrain real-world graph shapes, and real-world graph evolution doesn't accidentally break Gridkin tests.

The format takes its name from Cucumber/Gherkin (the Given/When/Then BDD format widely adopted across the testing ecosystem since ~2010) and from openCypher's Technology Compatibility Kit (the Cucumber-based test corpus used by Neo4j, Memgraph, RedisGraph, AgensGraph and others since ~2016). Gridkin is intentionally *not* a port of either — it is a thin TAP-vocabulary scenario format whose shape is designed for TAP's nested envelope responses, TAP's typed BaseModel data model, and TAP's dimension partitioning. The precedent is named so future work can borrow from it deliberately rather than discover the shape by accident.

This is a **Proposed** spec authored ahead of plugin initialization. The plugin's scaffold (tap-plugin.toml, models, runner, fixtures, scenarios) is deliberately not in this change; a fresh session will spawn off this spec and build them. See `project_spec_before_plugin_init_workflow_gap` (agent memory, 2026-05-20) for the open workflow question this case surfaced.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Eyeballable    | Every Gridkin scenario is three short committed files (graph + query + expected) a human can read end-to-end |
| 2. | Oracle-bearing | Expected envelopes are hand-authored or independently computed — not derived from the executor under test |
| 3. | Snapshot-disciplined | Regenerating expected files requires explicit opt-in and human review of the diff before commit |
| 4. | Traceable      | Every scenario carries the spec requirement IDs it covers, producing a derived coverage matrix |
| 5. | Decoupled      | Playground node and edge types do not collide with any real domain plugin's vocabulary |
| 6. | Inspirable     | The openCypher TCK is studied as a scenario-mine for corner cases; no TCK queries or graphs are copied into Gridkin |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-gridkin-plugin-scope | [Plugin Scope](#plugin-scope) | Proposed | What the plugin contains and what it does not |
| req-gridkin-playground-node-types | [Playground Node and Edge Types](#playground-node-and-edge-types) | Proposed | Bespoke vocabulary for query-pattern testing |
| req-gridkin-scenario-format | [Gridkin Scenario Format](#gridkin-scenario-format) | Proposed | The JSON shape of a `.gridkin.json` file |
| req-gridkin-fixture-tier-structure | [Two-Tier Fixture Structure](#two-tier-fixture-structure) | Proposed | Shape-targeted fixtures + one canonical playground graph |
| req-gridkin-runner-contract | [Gridkin Runner Contract](#gridkin-runner-contract) | Proposed | Discovery, loading, execution, and assertion behavior |
| req-gridkin-oracle-assertion | [Oracle Assertion Discipline](#oracle-assertion-discipline) | Proposed | Expected envelopes are independent of the executor under test |
| req-gridkin-snapshot-discipline | [Snapshot Regeneration Discipline](#snapshot-regeneration-discipline) | Proposed | Explicit opt-in and human review when regenerating |
| req-gridkin-explain-snapshot | [Explain SQL Snapshot](#explain-sql-snapshot) | Proposed | Each scenario commits the ORM-compiled SQL Gryphon emits |
| req-gridkin-req-traceability | [Requirement Traceability](#requirement-traceability) | Proposed | Every scenario cites the spec RIDs it covers |
| req-gridkin-tck-inspiration | [TCK as Scenario Inspiration](#tck-as-scenario-inspiration) | Proposed | Mine the openCypher TCK for corner-case intent; never port queries |
| req-gridkin-json-schema | [JSON Schema for Scenario Files](#json-schema-for-scenario-files) | Proposed | Author and validate-at-load a JSON Schema for the scenario format |
| req-gridkin-nongoals | [v0 Non-Goals](#v0-non-goals) | Proposed | Explicitly deferred concerns |

### Plugin Scope
----
RID: `req-gridkin-plugin-scope`
Status: `Proposed`

The `gridkin_playground` plugin exists to host Gryphon test scenarios and their backing graph fixtures.

#### Implementation

The plugin contains:

- A bespoke set of playground node and edge types (see [req-gridkin-playground-node-types](#playground-node-and-edge-types)), used only by Gridkin fixtures
- A directory of shape-targeted GRIFT fixtures (`fixtures/<shape>.grift.json`) — each fixture seeds one specific graph topology corner
- One canonical multi-shape playground fixture (`fixtures/playground.grift.json`) — used for the `gryphon explain` demo surface and as a tutorial graph for the language
- A directory of Gridkin scenario files (`scenarios/<feature>.gridkin.json`) — each scenario set covers one Gryphon feature
- A directory of expected-envelope side files (`expected/<feature>.expected.json`) and expected-SQL side files (`expected/<feature>.sql.txt`)
- A pytest-discoverable Gridkin runner that drives all of the above

The plugin does **not** contain:

- The Gryphon executor or any of its source — Gridkin tests the executor, it does not implement it
- A collector — the playground graph is seeded from committed GRIFT files, not collected
- Pages, panels, or any user-facing surface — the playground is a developer artifact
- Domain vocabulary — playground node types are deliberately abstract (`pg_node`, `pg_hub`, etc.)

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-plugin-scope-1 | Hosts Scenario Corpus | Proposed | The plugin contains the canonical home for Gridkin scenario files and their expected side files. | |
| req-gridkin-plugin-scope-2 | Hosts Playground Vocabulary | Proposed | The plugin registers playground node and edge types used only by Gridkin fixtures. | |
| req-gridkin-plugin-scope-3 | Excludes Executor Source | Proposed | The plugin does not contain Gryphon executor, parser, or grammar source — those live in `tap_grid/gryphon/`. | |
| req-gridkin-plugin-scope-4 | Excludes User-Facing Surface | Proposed | The plugin registers no pages, panels, searches, or layouts. | |

### Playground Node and Edge Types
----
RID: `req-gridkin-playground-node-types`
Status: `Proposed`

Gridkin fixtures use a small, abstract vocabulary of node and edge types that exist only to exercise query patterns.

#### Implementation

Initial node types:

- `pg_node` — generic playground node, no special semantics; the default building block
- `pg_hub` — semantically marked as a hub (graph patterns where one node has many neighbors); the executor doesn't care, but tests can target the type to set up hub-and-spoke shapes
- `pg_leaf` — semantically marked as a leaf (terminal in a chain); same — typed only so tests can construct intended shapes
- `pg_cycle_node` — used to construct cycles, self-loops, and multi-cycles

Initial edge types:

- `PG_LINKS` — generic directional edge
- `PG_NESTS` — used to construct compound/nested graph shapes
- `PG_LOOPS` — used to construct self-loops and small cycles
- `PG_OPTIONAL` — used to construct sparse fan-outs where some nodes have the edge and some don't (for OPTIONAL MATCH testing once implemented)

Naming convention: `pg_*` for node types, `PG_*` for edge types. The `pg_` prefix is unambiguous against any real domain plugin (no production vocabulary starts with `pg_`) and short enough to read in queries without noise.

Each playground node type has a BaseModel with at minimum: `entity_id`, `name`, `description`, `tags` (JSONField for testing JSON-key access predicates), and a small set of typed fields chosen to exercise the predicate language (e.g. `severity_score: int`, `is_open: bool`, `kind: str`). Specific fields are designed in the same change that builds the plugin scaffold; this spec lists the *intent*, not the exact field list.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-playground-node-types-1 | Decoupled From Domain Vocabulary | Proposed | No playground node or edge type collides with any production plugin's vocabulary. | `pg_*` / `PG_*` prefix |
| req-gridkin-playground-node-types-2 | Typed Fields Cover Predicate Surface | Proposed | Playground BaseModels carry typed fields covering each scalar predicate type the executor supports (string, int, bool, datetime, JSONField). | |
| req-gridkin-playground-node-types-3 | Vocabulary Documented Inline | Proposed | The plugin README or a sibling doc lists the playground node and edge types and their intended use, so scenario authors don't reinvent. | |

### Gridkin Scenario Format
----
RID: `req-gridkin-scenario-format`
Status: `Proposed`

A Gridkin scenario file is a JSON document that defines one feature's worth of test scenarios against a named fixture.

#### Implementation

The file lives at `plugins/gridkin_playground/scenarios/<feature>.gridkin.json` and has the shape:

```json
{
  "feature": "OPTIONAL MATCH preserves rows when the optional pattern does not bind",
  "background": {
    "grift_fixture": "fixtures/optional_relations.grift.json"
  },
  "scenarios": [
    {
      "name": "lambda with zero findings still appears",
      "tags": ["optional-match", "aggregation"],
      "covers": ["req-grid-gryphon-optional-match", "req-grid-gryphon-count"],
      "inspired_by": "opencypher/tck/features/clauses/optional-match/Mandatory1.feature",
      "query": "MATCH (l:pg_hub) OPTIONAL MATCH (l)-[:PG_LINKS]->(f:pg_leaf) RETURN l, COUNT(f) AS findings",
      "params": {},
      "expected_envelope": "expected/optional_match_lambda_zero_findings.expected.json",
      "expected_sql_snapshot": "expected/optional_match_lambda_zero_findings.sql.txt"
    }
  ]
}
```

Field semantics:

- `feature` (string, required) — a human-readable description of the feature this file covers
- `background.grift_fixture` (string, required) — path (relative to the plugin root) to the GRIFT fixture that seeds the test database
- `scenarios` (array, required, at least one) — the list of scenarios in this feature
- `scenarios[].name` (string, required) — human-readable scenario name
- `scenarios[].tags` (array of strings, optional) — tags for selective test runs (e.g. `pytest -m gridkin -k optional-match`)
- `scenarios[].covers` (array of strings, required, at least one) — the spec RIDs and ACIDs this scenario exercises (drives the traceability matrix)
- `scenarios[].inspired_by` (string, optional) — breadcrumb to an openCypher TCK feature file when the scenario's intent was mined from the TCK; pure informational, never a license claim
- `scenarios[].query` (string, required) — the Gryphon query to execute
- `scenarios[].params` (object, optional) — runtime `$param` values for the query
- `scenarios[].expected_envelope` (string, required) — path to the JSON file holding the exact expected response envelope
- `scenarios[].expected_sql_snapshot` (string, required) — path to the text file holding the expected ORM-compiled SQL (see [req-gridkin-explain-snapshot](#explain-sql-snapshot))

The expected envelope file is a literal JSON document matching the canonical subgraph envelope shape from `spec-grift-envelope.md`. When that spec moves from Proposed to Implemented, existing envelope side files are regenerated as a coordinated change.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-scenario-format-1 | All Required Fields Validated | Proposed | The runner rejects scenario files missing any required field, with a clear error pointing at the offending field. | |
| req-gridkin-scenario-format-2 | Expected Side Files Resolve | Proposed | The runner resolves `expected_envelope` and `expected_sql_snapshot` paths relative to the plugin root and fails loudly if either is missing. | |
| req-gridkin-scenario-format-3 | Covers Field Is Required Non-Empty | Proposed | Scenarios without at least one `covers` entry are rejected — traceability is binding, not optional. | |

### Two-Tier Fixture Structure
----
RID: `req-gridkin-fixture-tier-structure`
Status: `Proposed`

Fixtures come in two tiers, each serving a distinct role.

#### Implementation

**Tier 1 — shape-targeted fixtures** (`fixtures/<shape>.grift.json`):

Each fixture seeds one graph topology corner in isolation. Initial set (extended as features land):

- `cycles.grift.json` — 2-cycle, 3-cycle, self-loop
- `multi_edge.grift.json` — same node pair connected by multiple edges of different types
- `sparse_dense.grift.json` — one densely connected hub, plus isolated islands
- `soft_deletes.grift.json` — mix of live and soft-deleted entities (deleted_at not null)
- `polymorphic.grift.json` — multiple node types sharing edge types
- `nesting.grift.json` — parent/child compound structures
- `optional_relations.grift.json` — sparse fan-out: some nodes have the edge, some don't (for OPTIONAL MATCH)
- `dimensions.grift.json` — entities partitioned across dimension scopes
- `json_payloads.grift.json` — entities with rich JSON-backed fields (for JSON-key-access predicates and the JSON nested-search work landing in a parallel session)

Tier 1 fixtures are loaded individually by individual scenarios — small, focused, isolated.

**Tier 2 — the canonical playground fixture** (`fixtures/playground.grift.json`):

One larger GRIFT file that combines representative samples from every shape. Its role is *not* test isolation — it's the demo and tutorial graph. The `gryphon explain` surface (when built) defaults to loading the playground fixture so that a developer can paste a query and see it run against a known graph. The playground fixture is also the recommended graph for ad-hoc exploration in the shell during development.

Tier 2 has exactly one fixture file. It is not used by Gridkin scenario assertions (those use Tier 1) — keeping the demo graph separate from the test graphs means tweaking the playground for tutorial clarity doesn't ripple into test failures.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-fixture-tier-structure-1 | Tier 1 Fixtures Isolated | Proposed | Each Tier 1 fixture seeds exactly one shape and is small enough to read in full. | |
| req-gridkin-fixture-tier-structure-2 | Tier 2 Playground Distinct | Proposed | The canonical playground fixture is not used by any Gridkin scenario's `background.grift_fixture` field. | Demo vs. test separation |
| req-gridkin-fixture-tier-structure-3 | Fixtures Validate As GRIFT | Proposed | Both tiers use the standard GRIFT format and pass standard GRIFT validation on load. | |

### Gridkin Runner Contract
----
RID: `req-gridkin-runner-contract`
Status: `Proposed`

The runner is pytest-discoverable and follows a fixed lifecycle per scenario.

#### Implementation

For each scenario in each `.gridkin.json` file, the runner:

1. Loads the named Tier 1 fixture into the test database via the standard GRIFT importer (the same path real plugins use — no Gridkin-specific seed path)
2. Executes the scenario's Gryphon query with its `params`, capturing both the response envelope and the ORM-compiled SQL that the executor produced
3. Loads the expected envelope JSON and asserts deep equality against the actual response envelope
4. Loads the expected SQL text and asserts string equality against the captured SQL (whitespace-normalized)
5. Reports separately on envelope mismatch vs. SQL mismatch — a scenario can fail on one without the other, and the failure mode tells you whether behavior changed or query plan changed

Discovery is by directory scan: any `*.gridkin.json` file under `plugins/gridkin_playground/scenarios/` is discovered automatically. Tags are surfaced as pytest markers for selective runs.

Loading isolation: each scenario starts from an empty test database, loads its fixture, runs, and tears down. No state bleeds between scenarios. This is intentionally slow — the priority is correctness signal, not test-suite speed.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-runner-contract-1 | Pytest Discoverable | Proposed | Gridkin scenarios appear as pytest tests and can be run via `pytest plugins/gridkin_playground/`. | |
| req-gridkin-runner-contract-2 | Per-Scenario Isolation | Proposed | Each scenario runs against a freshly-seeded test database; no inter-scenario state. | |
| req-gridkin-runner-contract-3 | Envelope and SQL Asserted Separately | Proposed | A scenario can fail on envelope mismatch, SQL mismatch, or both — each is reported distinctly. | |
| req-gridkin-runner-contract-4 | Uses Standard GRIFT Importer | Proposed | Fixtures load through the same path as real plugin GRIFT data — no Gridkin-specific seed shortcut. | |

### Oracle Assertion Discipline
----
RID: `req-gridkin-oracle-assertion`
Status: `Proposed`

The expected envelope and expected SQL files are oracles, not derivations.

#### Implementation

An "oracle" assertion is one where the expected value comes from an independent source — hand-computation, hand-authorship, or a parallel implementation — rather than from the system under test. The classic anti-pattern is: "run the system, capture its output, commit the output as the expected, assert against future runs." This catches *regressions* but cannot catch *systematic bugs the original implementation already had* (an executor that overcounts by a consistent factor will produce consistent overcounts forever, and every test will pass).

Gridkin requires the oracle discipline:

- Expected envelope files are either hand-authored or computed independently (raw ORM query, hand enumeration). The author of the expected file must be able to defend the contents on inspection.
- When a scenario is *new*, the expected envelope is written *before* the scenario runs against the implementation. If they disagree, both the implementation and the expected are reviewed — the implementation isn't assumed correct.
- When a feature *evolves* and existing scenarios need regenerated expecteds, the diff is reviewed line-by-line by a human (see [req-gridkin-snapshot-discipline](#snapshot-regeneration-discipline)).

The motivation is captured in `feedback_borrow_from_oss_prior_art`: every well-known query engine's test suite (SQLite's sqllogictest, PostgreSQL's golden-file regression suite, openCypher's TCK) treats expected values as committed contracts authored with intent, not as captured snapshots.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-oracle-assertion-1 | Expected Files Are Contracts | Proposed | The convention that expected files represent intent (not capture) is documented in the plugin README and surfaced in `--update-snapshots` output. | |
| req-gridkin-oracle-assertion-2 | New Scenarios Author Expected First | Proposed | When introducing a scenario, author the expected envelope before observing the implementation's output. | Workflow norm, not runtime check |

### Snapshot Regeneration Discipline
----
RID: `req-gridkin-snapshot-discipline`
Status: `Proposed`

Regenerating expected files requires explicit opt-in and human review.

#### Implementation

The runner supports a `--update-snapshots` flag (or equivalent environment variable) that, when set, overwrites the expected envelope and expected SQL files with the current implementation's output. Without the flag, mismatches are test failures.

The flag is **never** invoked automatically (no CI step regenerates snapshots; no pre-commit hook regenerates snapshots). It is invoked by a developer who is intentionally changing behavior, after which:

1. `git diff` shows the expected-file changes
2. The developer reads the diff and confirms each change is intended
3. The expected files are committed in the same change as the implementation change

The runner's output on `--update-snapshots` writes a banner to stderr reminding the developer of the oracle discipline (per [req-gridkin-oracle-assertion](#oracle-assertion-discipline)) — that capture without review defeats the entire validation strategy.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-snapshot-discipline-1 | Update Flag Explicit | Proposed | Snapshot regeneration requires an explicit flag; no implicit regeneration path exists. | |
| req-gridkin-snapshot-discipline-2 | Update Banner Reminds Discipline | Proposed | The runner prints an oracle-discipline reminder when snapshots are regenerated. | |
| req-gridkin-snapshot-discipline-3 | No CI Regeneration | Proposed | No CI job or hook invokes `--update-snapshots`; it is developer-only. | |

### Explain SQL Snapshot
----
RID: `req-gridkin-explain-snapshot`
Status: `Proposed`

Each scenario commits the exact ORM-compiled SQL the Gryphon executor produces for its query.

#### Implementation

The Gryphon executor compiles each query into a Django ORM `QuerySet`. The `QuerySet.query` attribute carries the compiled SQL representation. Gridkin captures that representation (whitespace-normalized) and asserts it matches a committed `<scenario>.sql.txt` file.

The value of this assertion:

- **Eyeballable correctness check.** A developer can read the committed SQL and judge whether it makes sense for the query without reading the executor source.
- **Query-plan regression detection.** Refactors that change the executor's compilation strategy (e.g. joining via reverse-FK vs. explicit ID list) show up as SQL diffs even when the response envelope is identical. Sometimes that's intended (perf improvement); sometimes it's a bug (different JOIN shape causing future inflation).
- **Demo surface.** The `gryphon explain` developer tool (a CLI / management command, designed in a sibling spec when built) renders the same compiled SQL on demand for any query against the playground graph — letting developers verify behavior without writing a test first.

The SQL is whitespace-normalized (collapsed runs of whitespace; trimmed lines) so trivial formatting changes don't churn snapshots. The values inside the SQL — table names, column names, JOIN structure, WHERE clauses, parameter placeholders — are asserted byte-exact after normalization.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-explain-snapshot-1 | SQL Captured Per Scenario | Proposed | Every Gridkin scenario commits an `expected_sql_snapshot` file. | |
| req-gridkin-explain-snapshot-2 | Whitespace Normalized | Proposed | The runner whitespace-normalizes both expected and actual SQL before comparing. | |
| req-gridkin-explain-snapshot-3 | Failure Distinct From Envelope Failure | Proposed | SQL mismatch is reported as a distinct failure mode from envelope mismatch. | |

### Requirement Traceability
----
RID: `req-gridkin-req-traceability`
Status: `Proposed`

Every Gridkin scenario cites the spec RIDs it exercises.

#### Implementation

The `scenarios[].covers` field is required and must contain at least one RID or ACID. The runner emits a derived coverage matrix on demand (CLI: `pytest plugins/gridkin_playground/ --gridkin-coverage`) listing, for each cited RID, the scenarios that cover it — and, by implication, the RIDs in Gryphon-related specs that are *not* covered by any scenario.

This produces, for free, the requirement-traceability matrix that the audit identified as missing from current Gryphon tests.

`covers` is binding for new scenarios. Existing Gryphon tests (in `tap_grid/tests/test_gryphon.py`) are not retroactively required to cite `covers` — the traceability investment happens at the Gridkin boundary going forward.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-req-traceability-1 | Covers Required | Proposed | Scenario files without a `covers` field on every scenario fail to load. | |
| req-gridkin-req-traceability-2 | Coverage Matrix Generable | Proposed | A CLI command emits a coverage matrix mapping RID → covering scenarios. | |
| req-gridkin-req-traceability-3 | Gap Surfaced | Proposed | The coverage matrix flags any RID cited in a Gryphon spec that has zero covering Gridkin scenarios. | Drives prioritization |

### TCK as Scenario Inspiration
----
RID: `req-gridkin-tck-inspiration`
Status: `Proposed`

The openCypher Technology Compatibility Kit is mined for corner-case intent. No TCK content is copied into Gridkin.

#### Implementation

When authoring Gridkin scenarios for a Gryphon feature, the recommended workflow is:

1. Identify the openCypher TCK feature folder corresponding to the feature being implemented (e.g. `tck/features/clauses/optional-match/` for OPTIONAL MATCH)
2. Read each scenario file in that folder for its *intent* — what corner case is it pinning down? What historical confusion does it guard against? (TCK scenarios exist because real graph engines historically broke on real edge cases.)
3. Write a short notes list of corner-case intents that apply to Gryphon's semantics. Skip intents that are Cypher-specific quirks (null comparison semantics, list comprehensions, etc.) — those are not Gryphon's contract.
4. Author Gridkin scenarios in TAP vocabulary covering each retained corner case. The query is written in Gryphon syntax against the `pg_*` playground vocabulary; the graph fixture is hand-authored; the expected envelope is hand-authored per [req-gridkin-oracle-assertion](#oracle-assertion-discipline).
5. Set the scenario's `inspired_by` field to the TCK feature folder path. This is an attribution breadcrumb — it lets future-us trace which corner-case taxonomies have been mined and which haven't.

Constraints:

- **No TCK query text appears in any Gridkin scenario.** Even verbatim-equivalent Cypher (`MATCH (a)-[:KNOWS]->(b)`) is rewritten in TAP vocabulary (`MATCH (a:pg_node)-[:PG_LINKS]->(b:pg_node)`). Per `feedback_borrow_from_oss_prior_art`, inspiration only; clean-room reimplementation in our own words.
- **No TCK graph data is reused.** Playground fixtures use playground node types; TCK graph data is property-bag and doesn't translate.
- **No TCK expected results are reused.** They reflect Cypher semantics; Gridkin asserts against Gryphon semantics.

The legal posture: the openCypher TCK is Apache 2.0 licensed and could be reused with attribution. Gridkin chooses not to — the project standing rule is clean-room reimplementation regardless of license permissions. The breadcrumb is intellectual honesty, not legal cover.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-tck-inspiration-1 | Inspired-By Breadcrumb Convention | Proposed | When a Gridkin scenario's intent was mined from a TCK feature, the scenario's `inspired_by` field cites the source folder. | |
| req-gridkin-tck-inspiration-2 | No TCK Content Copied | Proposed | No TCK query text, graph data, or expected results appear in any Gridkin file. | |
| req-gridkin-tck-inspiration-3 | Cypher-Specific Quirks Excluded | Proposed | Scenario authors filter TCK intent for applicability to Gryphon semantics; Cypher-specific behaviors are not inherited. | |

#### Future

Long-horizon seam: when TAP's satellite system arrives (per `project_satellite_system_vision`), Gridkin becomes the natural contract for satellite query authors — the same role openCypher's TCK serves for multi-engine Cypher compatibility. The scenario format is designed so that this evolution is structural, not a rewrite. Until that demand signal arrives, Gridkin is internal-only.

### JSON Schema for Scenario Files
----
RID: `req-gridkin-json-schema`
Status: `Proposed`

The Gridkin scenario format is a new structured-data format and ships with a JSON Schema validated at load.

#### Implementation

Per the standing rule (`feedback_json_formats_need_schema`, mirrored in AGENTS.md Core TAP Rules): every new structured-data format authors a JSON Schema in the same change that introduces the format, and the runner validates each scenario file against the schema on load — failing loud on violations rather than silently coercing.

The schema lives at `plugins/gridkin_playground/scenarios/gridkin-scenario.schema.json` (sibling to the scenario files it governs). The runner loads it once and validates every `.gridkin.json` against it before parsing.

This requirement is bound to the runner work, not to this spec — the schema and the runner are designed and shipped together by the spawned session.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-json-schema-1 | Schema Authored Same-Change | Proposed | The schema is written in the same change that introduces the runner — not a follow-up. | |
| req-gridkin-json-schema-2 | Validation On Load | Proposed | Every scenario file is validated against the schema before its contents are used; invalid files fail loudly. | |

### v0 Non-Goals
----
RID: `req-gridkin-nongoals`
Status: `Proposed`

Concerns explicitly excluded from Gridkin v0:

- **Cypher subset compatibility claim.** Gridkin asserts Gryphon's behavior against intent we authored; it makes no claim that Gryphon implements any portion of Cypher to spec.
- **Write-side testing.** Gryphon is read-only; Gridkin tests read behavior only. CREATE/MERGE/DELETE/SET are not in Gryphon's grammar and have no Gridkin coverage.
- **Performance / scale testing.** Gridkin fixtures are small (≤100 entities each). Benchmarking and large-graph behavior are deferred until a demand signal arrives.
- **Property-based / fuzz testing.** Tools like SQLancer's TLP/NoREC and sqlsmith-style query generators are powerful but premature; deferred until Gryphon's surface is stable.
- **Public conformance kit.** Gridkin is internal. When the satellite system arrives it may evolve into a public contract; the format is designed not to preclude that, but no public-facing work happens in v0.
- **Mechanical TCK port.** The TCK is mined for intent only; mechanical translation (parse Gherkin, translate Cypher to Gryphon, translate property-bag graphs to BaseModel envelopes) is not pursued. The translation cost is high and the value below the bar until external compatibility becomes a demand.
- **Backward compatibility with the existing `test_gryphon.py` suite.** Gridkin does not replace the existing executor tests; it complements them. The existing suite is not retroactively migrated.
- **CI integration.** Wiring Gridkin into the multi-session promote-gate happens after the runner exists and the CI surface is built — not part of this plugin's v0.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-nongoals-1 | Non-Goals Documented | Proposed | The plugin README links to this section so contributors find the non-goals before proposing scope expansion. | |
