# Gryphon Playground Plugin Specification (v0)

## Philosophy

The `gryphon_playground` plugin is TAP's dedicated environment for exercising and
testing the Gryphon query language. Gryphon is the canonical read path for
TAP-managed graph data — "Gryphon over ORM" is a canonical project rule — and that
load-bearing status makes a first-class place to stress, validate, and demonstrate
the language disproportionately valuable. Real-world use on the Sam-demo critical
path has already surfaced blocking executor bugs and regressions; the playground
exists to turn that class of failure into something a hand-authored test catches
before it ships.

The plugin hosts three things:

1. **A bespoke playground vocabulary** of node and edge types (`pg_*` / `PG_*`)
   designed *only* to exercise query patterns — cycles, self-loops, multi-edges,
   sparse/dense regions, optional relationships, dimension partitions.
2. **The Gridkin scenario corpus** and its backing graph fixtures. Gridkin is the
   scenario-driven test format for Gryphon; the format itself is specified
   separately in the companion [spec-gridkin-v0.md](spec-gridkin-v0.md).
3. **A pytest-discoverable Gridkin runner** that drives the scenarios.

Keeping the playground decoupled from real domain models (`lotr`, `aws_core`,
`samsite`) means Gridkin scenarios don't accidentally constrain real-world graph
shapes, and real-world graph evolution doesn't accidentally break Gridkin tests.

This spec is the **top-level, governing** specification for the plugin: its
purpose, scope, and playground vocabulary. The Gridkin scenario file format,
runner contract, oracle discipline, snapshot discipline, requirement traceability,
and JSON Schema are specified in [spec-gridkin-v0.md](spec-gridkin-v0.md). Where
the two specs touch the same surface, this spec governs *what the plugin
contains*; the Gridkin spec governs *the format of the files it contains*.

## Relationship to the Gryphon Wishlist

[`doc-dev-gryphon-wishlist.md`](../../../docs/misc/doc-dev-gryphon-wishlist.md) is the
operational companion to this spec and the Gridkin spec — a prioritized,
demand-shaped view of what Gryphon needs to grow into, plus the validation
discipline every Gryphon extension ships under. It is required reading before
extending Gryphon or adding scenarios.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Decoupled      | Playground node and edge types collide with no real domain plugin's vocabulary |
| 2. | Pattern-shaped | The vocabulary and fixtures are shaped to hit graph query-pattern corners deliberately |
| 3. | Corpus home    | The plugin is the single canonical home for the Gridkin scenario corpus and its runner |
| 4. | Eyeballable    | Playground graphs are small enough that a human can read one in full |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-gryphon-playground-scope | [Plugin Scope](#plugin-scope) | Implemented | What the plugin contains and what it does not |
| req-gryphon-playground-vocabulary | [Playground Node and Edge Types](#playground-node-and-edge-types) | Implemented | Bespoke `pg_*` / `PG_*` vocabulary for query-pattern testing |
| req-gryphon-playground-fixtures | [Two-Tier Fixture Structure](#two-tier-fixture-structure) | In Development | Tier-1 fixtures grow with features; the Tier-2 canonical playground fixture is pending |
| req-gryphon-playground-gridkin | [Gridkin Format Specified Separately](#gridkin-format-specified-separately) | Implemented | The scenario format, runner contract, and disciplines are governed by `spec-gridkin-v0.md` |

### Plugin Scope
----
RID: `req-gryphon-playground-scope`
Status: `Implemented`

The `gryphon_playground` plugin exists to host Gryphon test scenarios, their
backing graph fixtures, the playground vocabulary they use, and the runner that
drives them.

#### Implementation

The plugin contains:

- A bespoke set of playground node and edge types (see
  [req-gryphon-playground-vocabulary](#playground-node-and-edge-types)), used only
  by Gridkin fixtures
- A directory of shape-targeted GRIFT fixtures (`fixtures/<shape>.grift.json`) —
  each fixture seeds one specific graph topology corner
- One canonical multi-shape playground fixture (`fixtures/playground.grift.json`)
  — used for the `gryphon explain` demo surface and as a tutorial graph for the
  language
- A directory of Gridkin scenario files (`scenarios/<feature>.gridkin.json`) —
  each scenario set covers one Gryphon feature
- A directory of expected-envelope and expected-SQL side files (`expected/`)
- A pytest-discoverable Gridkin runner that drives all of the above

The plugin does **not** contain:

- The Gryphon executor, parser, or grammar source — Gridkin tests the executor, it
  does not implement it; that source lives in `tap_grid/gryphon/`
- A collector — the playground graph is seeded from committed GRIFT files, not
  collected
- Pages, panels, searches, layouts, or any user-facing surface — the playground is
  a developer artifact
- Domain vocabulary — playground node types are deliberately abstract (`pg_node`,
  `pg_hub`, etc.)

Because its models must be migrated and its scenarios run under pytest,
`gryphon_playground` IS registered in `INSTALLED_APPS` — unlike a standalone-repo
plugin awaiting integration. It is, alongside `lotr`, a load-bearing test-fixture
plugin: de-registering it would red the test suite.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gryphon-playground-scope-1 | Hosts Scenario Corpus | Implemented | The plugin is the canonical home for Gridkin scenario files and their expected side files. | |
| req-gryphon-playground-scope-2 | Hosts Playground Vocabulary | Implemented | The plugin registers playground node and edge types used only by Gridkin fixtures. | |
| req-gryphon-playground-scope-3 | Excludes Executor Source | Implemented | The plugin does not contain Gryphon executor, parser, or grammar source. | Lives in `tap_grid/gryphon/` |
| req-gryphon-playground-scope-4 | Excludes User-Facing Surface | Implemented | The plugin registers no pages, panels, searches, or layouts. | |
| req-gryphon-playground-scope-5 | Registered For Test Execution | Implemented | The plugin is in `INSTALLED_APPS` so its models migrate and its runner is collected by pytest. | |

### Playground Node and Edge Types
----
RID: `req-gryphon-playground-vocabulary`
Status: `Implemented`

Gridkin fixtures use a small, abstract vocabulary of node and edge types that
exist only to exercise query patterns.

#### Implementation

Initial node types:

- `pg_node` — generic playground node, no special semantics; the default building
  block
- `pg_hub` — semantically marked as a hub (graph patterns where one node has many
  neighbors)
- `pg_leaf` — semantically marked as a leaf (terminal in a chain)
- `pg_cycle_node` — used to construct cycles, self-loops, and multi-cycles

The semantic distinction between the four types is **convention expressed through
the `entity_type` slug**, not through differing fields — the executor does not
care, but a scenario can target a type to construct an intended shape, and
label / type-scan patterns need distinct labels to match against.

Initial edge types:

- `PG_LINKS` — generic directional edge
- `PG_NESTS` — used to construct compound / nested graph shapes
- `PG_LOOPS` — used to construct self-loops and small cycles
- `PG_OPTIONAL` — used to construct sparse fan-outs where some nodes have the edge
  and some don't (for `OPTIONAL MATCH` testing once that feature is implemented)

Playground edge types declare **no `sources` / `targets` constraints** (wildcard).
Fixtures must be free to build any topology — self-loops, multi-edges, cross-type
links — without fighting edge-constraint validation.

Naming convention: `pg_*` for node types, `PG_*` for edge types. The `pg_` prefix
is unambiguous against any real domain plugin (no production vocabulary starts
with `pg_`) and short enough to read in queries without noise.

**Field set.** Every playground node model carries an identical typed-field set,
chosen so that fixtures and scenarios can exercise each scalar predicate type the
executor supports. The fields are identical across all four node types so the
predicate surface is uniform regardless of which playground type a scenario
targets.

| Field | Type | Predicate surface exercised |
| --- | --- | --- |
| `description` | text | string predicates; absence (`""`) for blank-field corners |
| `kind` | string | string equality / prefix predicates, categorical filters |
| `severity_score` | integer | numeric comparison predicates, aggregation inputs |
| `is_open` | boolean | boolean predicates |
| `observed_at` | datetime (nullable) | datetime comparison predicates, `IS NULL` corners |
| `tags` | JSON | JSON-key access predicates (`data.tags.<key>`) |

The `name` field (the BaseModel display field) is also present. The exact Python
mechanism for sharing the field set across the four models (repetition vs. an
abstract mixin) is an implementation choice made in the scaffold change, not
fixed here.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gryphon-playground-vocabulary-1 | Decoupled From Domain Vocabulary | Implemented | No playground node or edge type collides with any production plugin's vocabulary. | `pg_*` / `PG_*` prefix |
| req-gryphon-playground-vocabulary-2 | Typed Fields Cover Predicate Surface | Implemented | Playground BaseModels carry typed fields covering each scalar predicate type the executor supports (string, int, bool, datetime, JSON). | |
| req-gryphon-playground-vocabulary-3 | Edge Types Are Wildcard | Implemented | Playground edge types declare no source / target constraints, so fixtures can build any topology. | |
| req-gryphon-playground-vocabulary-4 | Vocabulary Documented Inline | Implemented | The plugin README lists the playground node and edge types and their intended use, so scenario authors don't reinvent. | |

### Two-Tier Fixture Structure
----
RID: `req-gryphon-playground-fixtures`
Status: `In Development`

Fixtures come in two tiers, each serving a distinct role.

#### Implementation

**Tier 1 — shape-targeted fixtures** (`fixtures/<shape>.grift.json`):

Each fixture seeds one graph topology corner in isolation. Initial set (extended
as features land — when a new feature reveals a topology corner no Tier 1 fixture
covers, the same change adds the fixture):

- `cycles.grift.json` — 2-cycle, 3-cycle, self-loop
- `multi_edge.grift.json` — same node pair connected by multiple edges of different types
- `sparse_dense.grift.json` — one densely connected hub, plus isolated islands
- `soft_deletes.grift.json` — mix of live and soft-deleted entities (`deleted_at` not null)
- `polymorphic.grift.json` — multiple node types sharing edge types
- `nesting.grift.json` — parent / child compound structures
- `optional_relations.grift.json` — sparse fan-out: some nodes have the edge, some don't
- `dimensions.grift.json` — entities partitioned across dimension scopes
- `json_payloads.grift.json` — entities with rich JSON-backed `tags` fields

Tier 1 fixtures are loaded individually by individual scenarios — small, focused,
isolated. Each is small enough to read in full (≤ ~100 entities; in practice the
first fixtures are far smaller, because the oracle discipline depends on a human
being able to hand-enumerate the expected result).

**Tier 2 — the canonical playground fixture** (`fixtures/playground.grift.json`):

One larger GRIFT file that combines representative samples from every shape. Its
role is *not* test isolation — it is the demo and tutorial graph. The `gryphon
explain` surface (when built) defaults to loading the playground fixture so a
developer can paste a query and see it run against a known graph. It is also the
recommended graph for ad-hoc exploration in the shell.

Tier 2 has exactly one fixture file. It is **not** used by Gridkin scenario
assertions — keeping the demo graph separate from the test graphs means tweaking
the playground for tutorial clarity doesn't ripple into test failures.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gryphon-playground-fixtures-1 | Tier 1 Fixtures Isolated | Implemented | Each Tier 1 fixture seeds exactly one shape and is small enough to read in full. | |
| req-gryphon-playground-fixtures-2 | Tier 2 Playground Distinct | Proposed | The canonical playground fixture is not used by any Gridkin scenario's `background.grift_fixture` field. | Demo vs. test separation; the Tier-2 fixture is not built in v0 |
| req-gryphon-playground-fixtures-3 | Fixtures Validate As GRIFT | Implemented | Both tiers use the standard GRIFT format and pass standard GRIFT validation on load. | |

### Gridkin Format Specified Separately
----
RID: `req-gryphon-playground-gridkin`
Status: `Implemented`

The Gridkin scenario file format is governed by a companion spec, not by this one.

#### Implementation

The Gridkin scenario file format — the JSON shape of a `.gridkin.json` file, the
runner's discovery / loading / assertion contract, the oracle assertion
discipline, the snapshot regeneration discipline, the explain-SQL snapshot,
requirement traceability, the openCypher-TCK-as-inspiration workflow, and the
scenario-file JSON Schema — is specified in [spec-gridkin-v0.md](spec-gridkin-v0.md).

This plugin is the **home** of the Gridkin corpus; that spec is the **contract**
for the files in it. The split exists for two reasons:

1. The format has a plausible future as a public conformance contract for
   satellite query authors (per `project_satellite_system_vision`); keeping it in
   its own spec lets it evolve toward that independently of this plugin's
   internal structure.
2. A reader extending the *plugin* (new model, new fixture shape) and a reader
   extending the *format* (new scenario field, new assertion mode) are doing
   different work and benefit from different specs being authoritative.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-gryphon-playground-gridkin-1 | Format Spec Is Authoritative | Implemented | The Gridkin file format and runner contract are defined by `spec-gridkin-v0.md`; this spec does not restate them. | |
| req-gryphon-playground-gridkin-2 | Corpus Lives In Plugin | Implemented | All Gridkin scenario files, fixtures, expected side files, and the runner live under `plugins/gryphon_playground/`. | |

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
