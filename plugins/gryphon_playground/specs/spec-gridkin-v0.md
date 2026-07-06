# Gridkin Scenario Format Specification (v0)

> **Development doctrine (standing filter).** Before any change to the Gryphon language, executor, or tests, consult [`doc-gryphon-commandments.md`](../../../docs/doc-gryphon-commandments.md) — the standing thou-shalt/shalt-not doctrine for all Gryphon work (the §IV Testing & Validation commandments cite this harness as their Enforcement).

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
is their shared operational companion. [`doc-gryphon-commandments-codex.md`](../../../docs/doc-gryphon-commandments-codex.md)
is the standing guidance for how Gryphon language, executor, and validation work
must be shaped; Gridkin scenario authors should treat it as required reading
alongside the wishlist.

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
| req-gridkin-rejection-scenario | [Rejection Scenarios](#rejection-scenarios) | Implemented | A scenario may assert the query is *refused* (`expected_error`) instead of returning an envelope |
| req-gridkin-oracle-assertion | [Oracle Assertion Discipline](#oracle-assertion-discipline) | Implemented | Expected envelopes are independent of the executor under test |
| req-gridkin-snapshot-discipline | [Snapshot Regeneration Discipline](#snapshot-regeneration-discipline) | Implemented | Explicit opt-in and human review when regenerating |
| req-gridkin-explain-snapshot | [Explain SQL Snapshot](#explain-sql-snapshot) | Implemented | Each scenario commits the ORM-compiled SQL Gryphon emits |
| req-gridkin-req-traceability | [Requirement Traceability](#requirement-traceability) | Implemented | Every scenario cites the spec RIDs it covers |
| req-gridkin-tck-inspiration | [TCK as Scenario Inspiration](#tck-as-scenario-inspiration) | Implemented | Mine the openCypher TCK for corner-case intent; never port queries |
| req-gridkin-tck-coverage | [TCK Coverage Ledger](#tck-coverage-ledger) | Implemented | A machine-checked, corpus-wide ledger of per-folder TCK coverage (covered/gaps/excluded) |
| req-gridkin-stage-coverage | [Executor-Stage Coverage Gate](#executor-stage-coverage-gate) | Implemented | Every executor dispatch stage is exercised by a WHERE-carrying scenario; the path set is derived from the source, not a hand-kept list |
| req-gridkin-executor-branch-coverage | [Executor Branch-Coverage Ratchet](#executor-branch-coverage-ratchet) | Implemented | `coverage.py` branch coverage of `executor.py`, ratcheted against a committed floor — the branch-level complement to the stage gate |
| req-gridkin-metamorphic-tlp | [Metamorphic TLP Corpus Assertion](#metamorphic-tlp-corpus-assertion) | Implemented | Ternary-logic partitioning derived from corpus scenarios probes the executor's 2VL/3VL null boundary for self-consistency |
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
- `scenarios[].inspired_by` (string, **required**) — openCypher-TCK mining
  breadcrumb (req-gridkin-tck-inspiration). Either a folder cite
  (`opencypher TCK — <folder> (<intent>)`) or, where no TCK folder applies, the
  explicit empty-pass marker (`opencypher TCK — no applicable feature folder
  (<reason>)`). A missing breadcrumb is a forgotten mining pass and fails schema
  validation. Purely informational, never a license claim. Per-folder *coverage*
  state lives in the coverage ledger (req-gridkin-tck-coverage), not here.
- `scenarios[].layer` (string, optional) — the GRIFT subgraph return layer to
  execute the query at, one of `lite` / `full` / `extended`; defaults to `full`
- `scenarios[].query` (string, required) — the Gryphon query to execute
- `scenarios[].params` (object, optional) — runtime `$param` values for the query
- `scenarios[].expected_envelope` (string, required for a *result* scenario) —
  path to the JSON file holding the exact expected response envelope
- `scenarios[].expected_sql_snapshot` (string, required for a *result* scenario)
  — path to the text file holding the expected ORM-compiled SQL (see
  [req-gridkin-explain-snapshot](#explain-sql-snapshot))
- `scenarios[].expected_error` (object) — present for a *rejection* scenario
  instead of the two `expected_*` paths (the modes are mutually exclusive, per
  [req-gridkin-rejection-scenario](#rejection-scenarios)). Fields: `type`
  (`GryphonParseError` | `SearchExecutionError`) and optional `message_contains`
  (case-insensitive substring). The query must be refused with that error.

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

One volatile element is redacted, mirroring the envelope's volatile-spine-field
redaction. A labelless `MATCH (n)` compiles to a bare type-scan whose WHERE
enumerates **every registered node type** —
`entity_type IN (%s, %s, … one per type …)`. That enumeration is an *environment
fact*: it grows whenever any plugin (anywhere in the tree) registers a new node
type, with no change to the Gryphon query plan under test. Snapshotting it verbatim
would make the labelless-scan oracles churn on every new entity type for no
behavioral reason. So the runner redacts the `entity_type IN (…)` placeholder run
and its matching leading params to a single `<entity-type-registry>` sentinel
before comparing (and writes the sentinel form on regeneration). This is surgical:
only the bare-type-scan emits an `IN` on `tap_entity.entity_type`, so no other
scenario is affected. The residual filter (`= %s` / `LIKE %s`), the
`IN`-on-`entity_type` shape itself, and every other clause are still asserted
exactly — and the **envelope** assertion still verifies the exact rows the scan
returns, so a behavioral regression in the bare scan is still caught.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-explain-snapshot-1 | SQL Captured Per Scenario | Implemented | Every Gridkin scenario commits an `expected_sql_snapshot` file. | |
| req-gridkin-explain-snapshot-2 | Whitespace Normalized | Implemented | The runner whitespace-normalizes both expected and actual SQL before comparing. | |
| req-gridkin-explain-snapshot-3 | Failure Distinct From Envelope Failure | Implemented | SQL mismatch is reported as a distinct failure mode from envelope mismatch. | |
| req-gridkin-explain-snapshot-4 | Multi-Statement Capture | Implemented | The `.sql.txt` side file holds one labelled block per `SELECT` the executor executes, in execution order; queries that run multiple statements capture all of them. | |
| req-gridkin-explain-snapshot-5 | Registry Enumeration Redacted | Implemented | The labelless bare-type-scan's `entity_type IN (…)` enumeration of all registered node types is redacted to a `<entity-type-registry>` sentinel on both comparison sides and on regeneration, so the oracle is stable across node-type registry growth; the residual filter and the response envelope still assert behavior exactly. | Surgical: only the bare-type-scan emits `IN` on `entity_type` |

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

### Rejection Scenarios
----
RID: `req-gridkin-rejection-scenario`
Status: `Implemented`

The traversal contract includes which queries are *rejected*, not only which
return rows. A query that must be refused — a negative `LIMIT`, a non-list `IN`
right-hand side, an unsupported pattern shape — is as much a part of the contract
as one that returns an envelope. Such cases live in Gridkin alongside the result
scenarios, so the whole traversal contract is validated in one place rather than
split across Gridkin and a separate `test_gryphon.py` surface.

#### Implementation

- A scenario sets `expected_error` *instead of* `expected_envelope` +
  `expected_sql_snapshot`; the JSON Schema enforces that exactly one mode is
  present (`oneOf`).
- `expected_error.type` is the refusal class — `GryphonParseError` (a grammar
  refusal) or `SearchExecutionError` (a semantic / unsupported-shape refusal at
  execution). The optional `message_contains` pins the diagnostic with a
  case-insensitive substring.
- The runner seeds the fixture, executes the query, and asserts it raised the
  named error type (and, if given, the message substring). A query that succeeds,
  or raises a different type, is a contract failure. `expected_error` is the
  hand-authored oracle: there is no snapshot to regenerate, so
  `GRIDKIN_UPDATE_SNAPSHOTS` is a no-op for rejection scenarios (the oracle
  discipline still holds — the author asserts the refusal, the executor is not
  consulted to write it).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-rejection-scenario-1 | Mutually-Exclusive Modes | Implemented | A scenario carries either the envelope+SQL pair or `expected_error`, never both and never neither (schema `oneOf`). | |
| req-gridkin-rejection-scenario-2 | Typed Refusal Oracle | Implemented | `expected_error.type` names the refusal class; an optional `message_contains` pins the diagnostic. The runner fails if the query succeeds or raises a different type. | |
| req-gridkin-rejection-scenario-3 | No Regeneration | Implemented | Rejection oracles are hand-authored; `GRIDKIN_UPDATE_SNAPSHOTS` does not write them. | |

### TCK Coverage Ledger
----
RID: `req-gridkin-tck-coverage`
Status: `Implemented`

`req-gridkin-tck-inspiration` makes each scenario cite *where* its intent came
from. It does not, by itself, answer *how much* of a TCK folder's corner-case
taxonomy has actually been carried over. The coverage ledger
(`scenarios/gryphon_playground.tck-coverage.json`, validated by `scenarios/tck-coverage.schema.json`)
closes that gap: a corpus-wide, machine-checked record of per-folder coverage so
"we mined this folder and here is exactly what we still owe" is auditable instead
of asserted.

#### Implementation

- **Granularity is the folder, not the scenario.** Coverage is a property of a
  TCK folder against the *whole* scenario corpus (many files cite
  `clauses/match`; a self-loop tested in `cycles.gridkin.json` counts as covered
  for the folder). The ledger therefore keys on folder, with one entry per TCK
  folder that any scenario's `inspired_by` cites.
- **`covered` is derived, never stored.** The guard
  (`tests/test_gridkin_internals.py::TestTckCoverageLedger`) computes
  `covered` = the number of scenarios whose `inspired_by` cites the folder. The
  carried-over ratio is `x / y = covered / (covered + open gaps)`. Storing a
  literal coverage count would be a self-certifying number that rots; deriving it
  means the ratio cannot silently lie.
- **Each entry records `gaps` and `excluded`.** `gaps[]` are applicable TCK
  intents not yet covered — the actionable debt, each tagged `kind`
  (`test` = closeable by authoring a scenario; `feature` = needs a Gryphon
  language feature first; `unknown` = not yet classified). `excluded[]` are TCK
  intents deliberately filtered out as Cypher-specific (three-valued-null logic,
  write clauses, scalar string/list functions, variable-length paths, …), each
  with a reason.
- **`no_applicable_folder[]`** records features whose scenarios have no TCK
  analog (TAP-native, or a surface the TCK does not cover — e.g. the `=~` regex
  operator, whose TCK feature files are empty stubs). Those scenarios carry the
  empty-pass `inspired_by` marker instead of a folder cite.
- **Clean-room is inherited verbatim** from `req-gridkin-tck-inspiration`: every
  intent string is in TAP's own words; no TCK query text, graph data, or expected
  results are copied into the ledger.

The drift guard is bidirectional: every folder a scenario cites must have a
ledger entry (a forgotten mining pass fails), and every ledger entry must be
cited by a scenario (a stale entry fails). Extending the Gryphon language surface
therefore forces a ledger update in the same change — the obligation is
structural, not a convention to remember.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-tck-coverage-1 | Folder-Keyed Ledger | Implemented | `gryphon_playground.tck-coverage.json` records per-TCK-folder coverage for the whole scenario corpus, validated against its JSON Schema at test time. | |
| req-gridkin-tck-coverage-2 | Covered Is Derived | Implemented | `covered` (and thus the carried-over ratio) is computed from scenario `inspired_by` cites, never stored, so it cannot drift from the corpus. | |
| req-gridkin-tck-coverage-3 | Gaps And Exclusions Enumerated | Implemented | Each folder enumerates uncovered applicable intents (`gaps`, each `kind`-tagged) and deliberately-excluded Cypher-specific intents (`excluded`, each with a reason). | |
| req-gridkin-tck-coverage-4 | Bidirectional Folder Tie | Implemented | Every cited folder has a ledger entry and every ledger entry is cited — enforced by the guard, so language extensions force a ledger update. | |

### Executor-Stage Coverage Gate
----
RID: `req-gridkin-stage-coverage`
Status: `Implemented`

`req-gridkin-tck-coverage` accounts for coverage of the language *intent*
surface. It says nothing about coverage of the executor's *dispatch paths* — and
the two are not the same. The intent≠path-coverage AAR
(`docs/aar/2026-06-30-gridkin-intent-coverage-not-path-coverage.md`) records a
silent-wrong-answer bug that lived on an executor path *no* scenario exercised,
while a green "intents covered" ledger sat directly over it: one intent ("a WHERE
over two bound nodes") mapped many-to-one onto dispatch paths, and the buggy path
had zero scenarios. This gate closes that specific accounting gap — a second
coverage axis, keyed on executor path rather than TCK folder.

#### Implementation

- **The path set is derived from the source, never hand-kept.** The executor tags
  every dispatch path with a `gryphon_stage("<label>")` context manager
  (`tap_grid/gryphon/executor.py`). `stage_coverage.enumerate_stage_labels()`
  AST-parses those call sites into the authoritative stage inventory. A
  `gryphon_stage()` called with a non-literal label raises rather than being
  silently missed — the inventory must fail loud, not under-report. The current
  stages are `optional-match`, `advanced`, `bare-type-scan`, `type-scan`, and
  `single-hop`.
- **The exercised set is derived from the committed snapshots.** Every result
  scenario's `.sql.txt` records the stage each statement ran under
  (`-- statement N · stage: <label>`, per `req-gridkin-explain-snapshot`).
  `snapshot_stages()` parses those headers; the union across the corpus is the
  set actually exercised.
- **The gate is sharpened past reachability — WHERE-carrying, not merely reached.**
  The motivating bug was a stage reached only *without* a WHERE, so its
  WHERE-application code was never run; reachability alone would have passed. So a
  stage counts as covered only when a scenario that *carries a WHERE* routes
  through it. "Carries a WHERE" counts a top-level `WHERE` and a
  `NOT EXISTS { … WHERE … }` inner predicate (the advanced stage applies the
  latter inside the anti-join). All five current stages apply a WHERE, so all five
  must be WHERE-exercised.
- **The tie is bidirectional.** Every enumerated stage must be WHERE-exercised (a
  new dispatch path with no WHERE-carrying scenario fails the gate — the direct
  regression lock for the AAR's class), and every stage label seen in a snapshot
  must still be emitted by the source (a renamed/removed stage leaves a stale
  label that fails the drift axis). The guard lives in
  `tests/test_gridkin_internals.py::TestStageCoverage`.
- **A pinned inventory forces acknowledgment.** A tripwire test pins the current
  five-stage set, so adding or removing a dispatch path is a deliberate, reviewed
  change rather than a silent one — the author must confront the new path's
  coverage, which the WHERE-coverage assertion then enforces.

This gate is what makes "the executor is covered" a claim about *paths* rather
than *intents*. Its complement is the model-based reference oracle (the third
Gridkin assertion, `req-gridkin-oracle-assertion`), which checks each exercised
path returns the *right answer*; together they cover both "is every path run"
and "does every run agree with an independent recomputation."

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-stage-coverage-1 | Path Set Derived From Source | Implemented | The dispatch-stage inventory is AST-parsed from the executor's `gryphon_stage()` call sites; a non-literal label raises rather than being silently dropped. | Not a hand-kept list. |
| req-gridkin-stage-coverage-2 | Every Stage WHERE-Exercised | Implemented | Each enumerated stage is exercised by at least one result scenario whose query carries a WHERE (top-level or NOT-EXISTS-inner). | The direct lock for the intent≠path AAR class. |
| req-gridkin-stage-coverage-3 | No Stale Snapshot Labels | Implemented | Every stage label appearing in a committed SQL snapshot is still emitted by the executor source; a renamed/removed label fails the drift axis. | Bidirectional tie. |
| req-gridkin-stage-coverage-4 | Inventory Pinned | Implemented | The current stage set is pinned by a tripwire test so adding or removing a dispatch path is a deliberate, reviewed change. | Forces coverage acknowledgment for a new path. |

### Executor Branch-Coverage Ratchet
----
RID: `req-gridkin-executor-branch-coverage`
Status: `Implemented`

The stage gate (`req-gridkin-stage-coverage`) proves every dispatch *path* runs
with a WHERE, but its granularity is the whole stage — it cannot see an
unexercised *branch within* a stage (a new WHERE operator, a null-handling arm, a
direction fan-out). `coverage.py` branch coverage over `tap_grid/gryphon/executor.py`,
ratcheted against a committed floor, is that finer complement — the "branch
coverage on the executor, ratcheted" corrective action named in the
intent≠path-coverage AAR §7.

#### Implementation

- **Measured across the whole executor corpus.** The floor is branch coverage of
  `executor.py` under the union of the suites that exercise it — the tap_grid unit
  and SQL-capture suites, the Gridkin scenario suite, and the API-level Gryphon
  suite. Measuring across the corpus is deliberate: the envelope-WHERE branch was
  reached only by a Gridkin scenario, so a unit-suite-only floor would have
  mislabelled a covered branch as a gap.
- **A script, not a per-commit pytest gate — and honestly labelled as such.**
  `coverage.py` must wrap the whole test process, and the instrumented run of the
  full corpus takes ~10-15 minutes, so it cannot ride the per-commit `pytest`
  path the way the stage gate does. It is `scripts/gryphon-coverage-ratchet`, run
  on-demand (inside the compose web container) and, once the dev-validation
  promote gate lands, from there. Its honest guard status lives in the
  `spec-dev-validation.md` Validation Map — the per-commit-CI piece is only the
  baseline-file sanity guard, not the coverage comparison itself.
- **Committed floor, ratchets up.** `tap_grid/gryphon/coverage-baseline.json`
  records the integer branch-coverage floor plus provenance (the exact percent
  measured, the commit, the suites). The script fails if `int(current) < floor`
  (a real regression), tolerating sub-point wobble; when coverage improves it
  prints a reminder to bump the floor and lock the gain. A cheap per-commit test
  (`tap_grid/tests/test_gryphon_coverage_baseline.py`) keeps the committed floor
  well-formed and never above the last real measurement.
- **First instance of the standardizing pattern.** This is the bounded, reviewed,
  in-repo, ratcheting mechanism `spec-dev-validation.md` names as TAP's canonical
  honesty convention (alongside the log-site-ID and authz-coverage baselines). As
  the build/validation pipeline is standardized, this ratchet is the template the
  dev-validation gate absorbs rather than a one-off.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-executor-branch-coverage-1 | Branch Coverage Measured | Implemented | `scripts/gryphon-coverage-ratchet` runs the executor-exercising suites under `coverage.py --branch` and reads `executor.py` branch coverage. | Union of unit, SQL-capture, Gridkin, and API suites. |
| req-gridkin-executor-branch-coverage-2 | Ratchet Floor Enforced | Implemented | The script fails when integer branch coverage drops below the committed floor; sub-point wobble is tolerated. | Regression is loud and blocking. |
| req-gridkin-executor-branch-coverage-3 | Floor Committed And Honest | Implemented | The floor lives in a committed baseline file with provenance; a per-commit guard test keeps it well-formed and never above the last measurement. | |
| req-gridkin-executor-branch-coverage-4 | Honest Guard Status | Implemented | The Validation Map records the ratchet as script-invoked (not per-commit CI), with only the baseline-file sanity as the CI-guarded piece, until the dev-validation gate absorbs it. | Counters the false-confidence failure mode. |

### Metamorphic TLP Corpus Assertion
----
RID: `req-gridkin-metamorphic-tlp`
Status: `Implemented`

The model oracle (`req-gridkin-oracle-assertion`) checks each query against an
independent recomputation; the stage/branch gates check that paths and branches
run. A *metamorphic* relation adds a third, orthogonal kind of check: it transforms
one query into related forms that must agree, and compares the executor against
**itself** — catching a bug the oracle and the executor could share (common-mode:
both authored the same null-logic mistake) without needing a known-correct answer.
Ternary Logic Partitioning (TLP, after SQLancer) is the relation shipped here, aimed
squarely at Gryphon's highest-risk surface, the null boundary.

#### Implementation

- **The relation.** For a predicate `p` over a bound variable, the rows where `p` is
  TRUE, FALSE, and UNKNOWN must *partition* the unfiltered scan — pairwise disjoint,
  and together the whole. `gridkin/metamorphic.py` derives four queries from an
  eligible scenario (unfiltered, `WHERE p`, `WHERE NOT (p)`, and — in 3VL —
  `WHERE <field> IS UNKNOWN`), all normalized to an entity-id projection so the
  relation compares identity sets. `tests/test_gryphon_metamorphic.py` seeds each
  scenario's fixture (per-scenario isolation, as `test_gridkin.py`) and asserts the
  partition.
- **The 2VL/3VL discriminator is load-bearing.** A null *field* vs a non-null literal
  follows SQL 3VL, so `p` is UNKNOWN exactly when the field is unobserved and the
  third partition is `<field> IS UNKNOWN`. A null *literal* operand short-circuits to
  genuine FALSE (2VL) — `p` is never UNKNOWN, so there is **no** third partition, the
  TRUE partition must be empty, and a naive `IS UNKNOWN` third partition would
  double-count the field-null rows. TLP discriminates on where the null lives
  (`Comparison.value is None`, resolving params); getting this wrong is the whole
  trap the relation exists to catch.
- **Scope: labelled type scans, single `Comparison` WHERE.** Within one declared type
  the split is exact. A bare labelless scan defers OR/NOT and conflates
  "field is null" with "this type lacks the field", so it is excluded. Derivation is
  mechanical from existing scenarios (no hand-authored expected — the partition *is*
  the oracle); ineligible shapes are simply not emitted, and an eligibility floor
  guards against a silent collapse to vacuous coverage.
- **NoREC deferred, honestly.** The envelope-vs-projection relation (which first
  caught the envelope-WHERE bug by hand) does not yield a *distinct* check: single-hop
  field projections degrade to a bare-variable envelope, and a type-scan
  envelope-vs-projection is same-path and redundant with TLP's TRUE partition. Its
  target is already covered by the single-hop dispatch collapse and the model oracle,
  so it is recorded as considered-and-deferred, not built.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-metamorphic-tlp-1 | Partition Holds | Implemented | For each eligible scenario the TRUE / FALSE / (UNKNOWN) partitions are pairwise disjoint and union to the unfiltered scan. | Executor self-consistency. |
| req-gridkin-metamorphic-tlp-2 | 2VL/3VL Discriminated | Implemented | The UNKNOWN partition is emitted only for a 3VL null-field predicate; a 2VL null-literal operand yields no UNKNOWN partition and an empty TRUE partition. | The load-bearing null boundary. |
| req-gridkin-metamorphic-tlp-3 | Derived, Not Authored | Implemented | Partition queries are derived mechanically from corpus scenarios; the predicate text is lifted verbatim so no literal is re-rendered. | The relation is the oracle. |
| req-gridkin-metamorphic-tlp-4 | Non-Vacuous | Implemented | An eligibility floor fails if a regression collapses the derived set, so the check cannot silently pass by covering nothing. | |

### Differential Property Fuzzer
----
RID: `req-gridkin-property-fuzz`
Status: `Implemented`

The model oracle (`req-gridkin-oracle-assertion`) is a second Gryphon engine that
recomputes each *authored* scenario's answer with zero lowering shared with the
executor. The property fuzzer removes the "authored" restriction: a **seedable
generator** emits a random small GRIFT graph over the playground types and a random
VALID query over the oracle's modeled surface, runs both engines, and asserts they
agree on identity / row sets. The oracle IS the differential harness the fuzzer
needs; the generator is the only new part. This is the capstone rung of the ladder
(`doc-gryphon-testing-philosophy.md` "The frontier"): the methodology stops being
purely *sampled* over hand-authored scenarios and starts covering the language
surface mechanically.

#### Implementation

- **Generator** (`gridkin/fuzz.py`): a `random.Random(graph_seed)` stream produces a
  graph (3–8 nodes over `pg_node`/`pg_hub`/`pg_leaf`, deliberate `observed_at`
  nulls, 0–n edges over `PG_LINKS`/`PG_OPTIONAL`, including self-loops and
  multi-edges) and a batch of queries against it. Every case replays from its seed
  alone — entity UUIDs are drawn from the seeded RNG, never `uuid4()`.
- **Well-typed by construction.** Query literals are sampled from the values
  actually present in the seeded graph (filters bind to real rows) and matched to
  each field's declared type (severity_score/int, is_open/bool,
  kind·name·description/string, observed_at/null-predicates), so the type-strictness
  gate never rejects a generated query. Nulls are produced on both sides of the
  boundary: the 2VL null *literal* operand (`field OP null`) and the 3VL null
  *field* (unobserved `observed_at`).
- **Seed once, diff many.** Each parametrized item seeds one graph (through the real
  `grift_import` path, per-graph DB isolation as `test_gridkin.py`) and runs its
  whole read-only query batch against it — many differentials per truncation.
  Committed default 12 graphs × 15 queries; env-tunable
  (`GRYPHON_FUZZ_GRAPHS`/`_QUERIES`/`_SEED`) for a longer soak.
- **Honest skips + a floor.** A shape the oracle does not model raises
  `OracleUnmodeled` and is recorded as a loud skip, never a fake green; the one
  permanent oracle skip (`LIMIT` without `ORDER BY`) is never generated. A
  per-case floor fails if most generated queries stop being asserted — the
  vacuous-coverage tripwire (sibling of the metamorphic eligibility floor). A
  non-clean executor failure (invalid SQL) is classified `crashed` and reported,
  never swallowed.
- **Zero shared lowering, still.** The generator and oracle are authored from the
  language spec / grammar; neither imports a line of `executor.py` lowering — the
  entire source of the differential guarantee.

#### Findings (the fuzzer earned its keep)

The first runs surfaced six real issues; each was triaged by evidence and either
fixed with a regression-locking scenario or scoped with a recorded rationale —
never papered over.

- **Executor, `= null` / `!= null` (fixed).** The executor lowered `field = null`
  to `IS NULL` and `field != null` to `IS NOT NULL` (a Django `field=None`
  artifact), silently returning null-/non-null-field rows — violating the
  two-valued "unobserved operand" rule that `spec-grid-traversal-language.md`
  mandates (a null literal short-circuits to genuine FALSE). Fixed in
  `_comparison_to_q`; locked by the two `is_null` `null-literal` scenarios.
- **Executor, single-hop field projection (fixed).** A single-hop traversal with a
  field-projection RETURN fell through to the *envelope* dispatch, which silently
  ignored the projection (returned nodes/edges, no rows) — the accept-and-drop
  class the AAR names. `_has_advanced_features` now routes it to the row executor;
  locked by `single_hop_dispatch-…-field-projection`.
- **Executor, anonymous connecting edge (fixed).** A bare-variable `RETURN a, b`
  over an anonymous (`-[]->`) edge dropped the connecting edge from the envelope
  (only *named* edges were collected). `_collect_graph_envelope` now collects
  anonymous hop edges too; locked by `single_hop_dispatch-…-anonymous-edge`.
- **Oracle, union WHERE scoping under NOT (fixed).** The reference oracle's
  per-clause union scoping substituted TRUE for an unbound-variable leaf and
  evaluated it, so a `NOT` over that leaf wrongly emptied the arm. It now *prunes*
  unbound leaves (the executor's own scoping rule, authored independently); locked
  by `union-…-not-scoped-to-one-arm`. (The reference impl is expected to need
  debugging too — that is the differential method.)
- **v0 boundary, node-only aggregation (scoped).** `MATCH (v:L) RETURN …, COUNT(v)`
  is cleanly rejected ("aggregation requires ≥1 edge") — a deliberate v0 boundary,
  not a silent-wrong-answer. The generator emits COUNT over chains only. Node-only
  aggregation is a named v0 gap, not a bug.
- **Executor, multi-hop far-node WHERE (RESOLVED).** A WHERE on a node beyond the
  root edge of a multi-hop chain resolves through a reverse-FK path
  (`to_entity__edges_out__to_entity__…`) identical to a structural hop path.
  Applied as a *separate* `.filter()` (as it was), Django spawned a *duplicate*
  join carrying none of the structural edge_type/label filters; the projection
  bound to it, so the chain silently returned far nodes reached by the WRONG edge
  type and COUNT inflated. **Fixed** by folding the predicate `Q` into the SAME
  `.filter()` as the structural hop filters (`_build_chain_queryset(...,
  predicate=..., bindings=...)`), so the far-node predicate reuses the one
  structural join. Regression-locked by the `far_node_where` scenarios (envelope
  + COUNT); the generator can now emit WHERE on multi-hop chains. A *negated*
  far-node comparison (`!=` or `NOT (...)`, both lowering to `~Q` over the
  reverse-FK path — the residual `bigint = uuid` crash) is now cleanly REJECTED
  (`_guard_negated_far_predicate`) rather than crashing; the third `far_node_where`
  scenario locks the rejection, and full row-level-negation support is a named
  deferred gap (per-field `F()` annotation). See
  `spec-grid-gryphon-multihop-aggregation.md` `req-grid-gryphon-multihop-envelope-3`
  + Future.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-property-fuzz-1 | Seedable & Replayable | Implemented | Every case (graph + query batch) is generated from `random.Random(graph_seed)` and replays from the seed alone; a divergence report prints the seed, the emitted GRIFT, the query, and both results. | UUIDs from the seeded RNG, not `uuid4()`. |
| req-gridkin-property-fuzz-2 | Well-Typed, Binding, Null-Probing | Implemented | Generated queries are well-typed (never tripping type-strictness), sample literals from the seeded graph so filters bind, and deliberately produce both 2VL null-literal and 3VL null-field predicates. | The null boundary is where risk concentrates. |
| req-gridkin-property-fuzz-3 | Zero Shared Lowering | Implemented | The generator and oracle are authored from the spec/grammar and share no lowering with `executor.py`; the executor is exercised through the real `grift_import` seeding and `explain_gryphon_raw`. | The differential guarantee. |
| req-gridkin-property-fuzz-4 | Honest Skips, No Fake Green | Implemented | An unmodeled shape is a loud skip (never asserted false-positive); a non-clean executor failure is reported as `crashed`; a per-case floor fails on vacuous coverage. | `LIMIT`-without-`ORDER BY` is never generated. |
| req-gridkin-property-fuzz-5 | Bounded Committed Run | Implemented | The committed run is small (12×15) and env-tunable for a longer soak, so it does not balloon the gate. | Per-graph DB isolation, read-only query batches. |

### Fuzz Campaign Ledger
----
RID: `req-gridkin-fuzz-campaign`
Status: `Implemented`

The property fuzzer's long-soak, trend-tracking complement. The per-commit gate (`req-gridkin-property-fuzz`) asserts a small committed band and fails on any divergence; a **campaign** grinds a large band the executor has never seen, classifies every query WITHOUT failing, and appends one summary row to an append-only ledger so the **bug frequency can be watched trending down as the executor hardens**. It is on-demand / loopable, never a per-commit gate (like the branch-coverage ratchet).

#### Implementation

- Engine: `tests/test_gryphon_fuzz_campaign.py` — one `transaction=True` parametrized item per graph (DB isolation inherited from the gate; `search_readonly` shares the physical DB, so seeds must commit to be visible and rollback isolation cannot be used). Every query is classified via `fuzz.run_query`; nothing is asserted; a seeding failure is recorded (not aborted) so the band completes. Activated only when `GRYPHON_FUZZ_CAMPAIGN_OUT` is set, so a normal `pytest` run skips it.
- Ledger + trend: `gridkin/fuzz_campaign.py` (stdlib-only) — `next_base_seed` advances the band past every prior campaign (divergences are deterministic; re-testing a fixed band reports zero), `append_row` stamps commit/UTC, `trend` renders the table. Ledger: `gridkin/fuzz-campaign-log.jsonl` (committed).
- Orchestrator: `scripts/gryphon-fuzz-campaign` — run in-container; loop it to grind for hours, one fresh band per iteration.
- Repeatable process: the **`gryphon-fuzz-soak`** skill (`plugins/gryphon_playground/skills/gryphon-fuzz-soak/`) is the canonical way to run a long unattended soak — it takes a duration argument, calibrates the band size, loops the orchestrator in the background to a deadline, then triages each persisted defect (replayable from its seed) and drives any real find through the fix discipline.
- The metric that trends down-and-to-the-right is **distinct new defects per 100k queries over fresh seed space**; a defect is fingerprinted by query SHAPE + status (+ exception class) so distinct seeds tripping one bug collapse to one defect. The **oracle-asserted fraction** is recorded beside it so a falling defect rate cannot be faked by the generator drifting off the modeled surface.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-fuzz-campaign-1 | Fresh Bands, Never Re-Tested | Implemented | Each campaign advances the seed band past the highest `seed_end` on record, so no seed is ever re-tested. | Deterministic divergences make a re-run of a fixed band report zero. |
| req-gridkin-fuzz-campaign-2 | Records, Never Gates | Implemented | The engine classifies every query and writes a summary without asserting; a seeding failure is recorded as a defect, not an abort. | The gate is `req-gridkin-property-fuzz`; this is measurement. |
| req-gridkin-fuzz-campaign-3 | Distinct-Defect Trend + Honest Denominator | Implemented | The ledger records distinct-defect fingerprints (query shape + status) and the oracle-asserted fraction; the trend reports distinct-new-defects-per-100k over fresh space. | Asserted fraction guards against a falling rate from exploration collapse. |
| req-gridkin-fuzz-campaign-4 | On-Demand, Not A Per-Commit Gate | Implemented | Skipped unless explicitly requested; run in-container and looped for a long soak. | Sibling of the branch-coverage ratchet. |

### Findings Ledger (Bug Locality)
----
RID: `req-gridkin-findings-ledger`
Status: `Implemented`

The fuzz-campaign ledger tracks bug **frequency over time** (trending down as the executor hardens); this tracks bug **locality** — WHERE in the executor defects concentrate — so the hot spots become the deliberate **refactor / simplification targets**. Every executor or oracle bug already earns a regression scenario; this rides that same discipline by appending one human-authored row at fix time recording which `subsystem` (a small structural vocabulary, each a set of executor functions) and which `functions` the defect lived in, its `class`, `discovery` source, and cross-cutting `tags`. The concentration is then read as a histogram: the hottest subsystem/function is where the next refactor pays off most.

#### Implementation

- Ledger + reporter: `gridkin/findings_ledger.py` (stdlib-only, imports neither Django nor the executor) — `SUBSYSTEMS` (the structural vocabulary) + `FUNCTION_SUBSYSTEM` (function→subsystem map), `load` / `validate` (schema + controlled-vocabulary enforcement), and `report` (renders hotspots by subsystem, function, tag, and discovery source). Ledger: `gridkin/gryphon-findings.jsonl` (committed, append-only, one row per root-caused defect).
- Renderer: `scripts/gryphon-findings` — prints the hotspot report in-container.
- **Honest denominator (do not drop it):** found-bug hotspots are biased toward where we have LOOKED — a subsystem with zero findings may be under-tested, not clean. The report pairs each subsystem's finding count with its **line coverage** (parsed from the branch-coverage ratchet's JSON via each function's AST line span, when the JSON is present): high-coverage + high-findings is a genuine refactor target; low-coverage + low-findings is a blind spot, not a clean bill. Same honest-denominator move as the campaign's asserted-fraction.
- **Discipline:** every executor/oracle bug fix appends a `gryphon-findings.jsonl` row in the same commit as its regression scenario. Well-formedness + vocabulary are CI-guarded (`tests/test_gryphon_findings_ledger.py`); the hotspot analysis itself is a manual read, not a gate.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gridkin-findings-ledger-1 | Structural Locality Vocabulary | Implemented | Each finding names a `subsystem` from a small structural vocabulary (each subsystem a set of executor functions) plus the specific `functions`; conceptual concerns that cut across functions are `tags`, a secondary lens. | The subsystem key drives both the histogram and the coverage column. |
| req-gridkin-findings-ledger-2 | Well-Formedness CI-Guarded | Implemented | A test loads the committed ledger and asserts every row is well-formed and uses the controlled `class` / `discovery` / `subsystem` vocabulary; a malformed or mis-tagged row fails the gate. | The hotspot READ is manual; only well-formedness is gated. |
| req-gridkin-findings-ledger-3 | Honest Denominator (Coverage-Paired) | Implemented | The report pairs each subsystem's finding count with its executor line coverage so a zero-findings subsystem is read as blind-spot-or-clean, not assumed clean. | Coverage from the branch-coverage ratchet JSON; column omitted with a caveat when absent. |
| req-gridkin-findings-ledger-4 | Fix-Time Discipline | Implemented | Every executor/oracle bug fix appends a findings row in the same commit as its regression scenario; findings are historical facts, so a row's named function is never asserted to still exist (it may be deleted by the very refactor the map motivated). | Rides the existing "every bug earns a regression scenario" rule. |

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
