# gryphon Execution Specification

> **Development doctrine (standing filter).** Before any change to the Gryphon language, executor, or tests, consult [`doc-gryphon-commandments.md`](../../docs/doc-gryphon-commandments.md) — the standing thou-shalt/shalt-not doctrine for all Gryphon work (RFC-2119 commandments with Reason + Enforcement, plus a Forthcoming section). Requirements here SHOULD stay consistent with it; it cites requirements here as its Enforcement anchors.

## Philosophy

gryphon text is compiled by TAP into an internal execution plan and does not execute directly as
raw backend code. This preserves the service-layer control TAP already wants for searches and
future AI-authored query definitions — and makes gryphon useful as a safer trust boundary than
direct backend query execution.

**Gryphon commandment guidance.** Any change to Gryphon validation, lowering, executor dispatch,
SQL capture, result packaging, or lowering-ladder usage must read and apply
[`doc-gryphon-commandments-codex.md`](../../docs/doc-gryphon-commandments-codex.md). The
commandments are not a substitute for this spec; they are the standing development discipline for
preserving read-only execution, bind-parameter safety, semantic conservation, and validation.

## Goals

|    |              |                                                                          |
| :---: | ---       | ---                                                                      |
| 1. | Safe          | Execution is read-only and scoped to TAP-managed graph data              |
| 2. | Backend-agnostic | gryphon text does not commit to one execution engine at rest        |
| 3. | Auditable     | Grammar file is a readable, diffable spec artifact for gryphon syntax   |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-grid-traversal-exec-pipeline | [Execution Pipeline](#execution-pipeline) | Implemented | Normalize → parse → validate → compile → execute → package |
| req-grid-traversal-exec-compiler | [Compiler Strategy](#compiler-strategy) | Implemented | lark as v1 parser; grammar.lark is the spec artifact |
| req-grid-traversal-exec-lowering | [Lowering Ladder](#lowering-ladder) | Implemented | Graduated rung order for lowering a query below the ORM; rung 1 (ORM) is the live backend, rungs 2–5 the sanctioned escalation path |
| req-grid-traversal-exec-scope.sec | [gryphon Safety Scope](#gryphon-safety-scope) | Implemented | Read-only, TAP-scoped, unsupported syntax rejected, inputs validated |
| req-grid-traversal-exec-sql-capture | [SQL Capture Seam](#sql-capture-seam) | Implemented | `execute_wrapper`-based SQL capture for Gridkin snapshots and `gryphon explain` |


### Execution Pipeline
----
RID: `req-grid-traversal-exec-pipeline`
Status: `Implemented`

gryphon text passes through a defined pipeline before any backend query runs.

#### Implementation

Execution flow:

1. **Normalize** — join `list[str]` to a single string; strip leading/trailing whitespace
2. **Parse** — run lark parser against the grammar; produce a TAP AST
3. **Validate** — check node labels and edge types against the registry; validate required
   `$var` names are present in `inputs`; reject unsupported clauses or functions
4. **Compile** — lower the validated AST into a TAP execution plan (v1: ORM query structure)
5. **Execute** — run the plan through a TAP-controlled backend using the read-only DB alias
6. **Package** — normalize results into the consumer's expected format (graph envelope or
   row projection per `RETURN` semantics)

The compiler backend is intentionally unspecified at the storage level. TAP may target:

- ORM for simple cases (v1)
- SQL for richer graph walks
- another future read-only execution backend

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-traversal-exec-pipeline-1 | gryphon Is Parsed Before Execution | Implemented | gryphon text is parsed into TAP-controlled structure before backend execution. | |
| req-grid-traversal-exec-pipeline-2 | gryphon Is Backend-Agnostic At Rest | Implemented | Stored gryphon text is not itself backend-specific SQL or ORM code. | |
| req-grid-traversal-exec-pipeline-3 | Compilation Produces Tap-Controlled Plan | Implemented | TAP compiles validated gryphon text into an internal execution plan. | |
| req-grid-traversal-exec-pipeline-4 | Results Are Normalized | Implemented | Execution results are normalized into the canonical envelope before return. | |

#### Future
Once execution backends stabilize, publish exact lowering rules from traversal syntax into
SQL or ORM plans in this spec.


### Compiler Strategy
----
RID: `req-grid-traversal-exec-compiler`
Status: `Implemented`

TAP uses `lark` as the v1 parser library. The grammar file (`grammar.lark`) is the authoritative
syntax specification for gryphon.

#### Implementation

**Parser:** `lark` (pure Python, LALR(1) by default). Chosen over hand-rolling because the
grammar surface (MATCH/WHERE/RETURN, patterns, filters, combinators, bounded repetition, JSON
path access, `$vars`, `AS` aliases) is large enough that a grammar library pays for itself in
maintainability. Chosen over a full Cypher parser because a Cypher parser accepts `CREATE`,
`MERGE`, `SET`, `DELETE` — rejecting those semantically rather than at the grammar level
produces confusing errors for users writing valid Cypher that TAP does not support.

**Grammar file location:** `tap_grid/traversal/grammar.lark`

The grammar file is:
- the canonical, diffable record of what gryphon syntax TAP accepts
- checked in alongside the implementation
- referenced in tests as the parsing source of truth
- updated whenever the language surface changes; a grammar change is a spec change

**AST:** Lark tree is transformed into frozen Python dataclasses (defined in
`tap_grid/traversal/ast_nodes.py`) via a `lark.Transformer` subclass. The transformer is
the only place that interprets lark tree node names.

**Error surface:** Parse failures raise `TraversalParseError` (a `tap_grid.exceptions` subclass)
with a human-readable message and line/column information from lark.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-traversal-exec-compiler-1 | Lark Used As V1 Parser | Implemented | The v1 gryphon parser is implemented with the lark library. | |
| req-grid-traversal-exec-compiler-2 | Grammar File Is Spec Artifact | Implemented | `grammar.lark` is the authoritative gryphon syntax specification, checked in alongside the implementation. | |
| req-grid-traversal-exec-compiler-3 | Parse Tree Transforms To Frozen AST | Implemented | Lark tree output is transformed into TAP frozen dataclasses, not consumed directly. | |
| req-grid-traversal-exec-compiler-4 | Parse Errors Raise TraversalParseError | Implemented | Failed parses surface as `TraversalParseError` with message and position information. | |

#### Future
If TAP later needs a richer query planner (query optimization, multiple backends, cost
estimation), consider whether the grammar-to-AST step should produce a logical plan IR before
lowering to a physical plan. The physical-lowering step such an IR would target is governed by
the [Lowering Ladder](#lowering-ladder) (`req-grid-traversal-exec-lowering`) — the IR is the
structural seam, the ladder is the per-node lowering choice.


### Lowering Ladder
----
RID: `req-grid-traversal-exec-lowering`
Status: `Implemented`

When a query shape outgrows the Django ORM, the compiler escalates through a fixed,
graduated set of lowering mechanisms — the *lowering ladder*. The ladder exists so that
"reach for raw SQL" is a deliberate, ordered, reviewable decision rather than an ad-hoc one,
and so that every rung keeps the guarantees the ORM provides for free.

#### Background

gryphon does not compile to SQL directly — it compiles to Django ORM `QuerySet`s, and Django
renders the SQL (see `req-grid-traversal-exec-sql-capture`). The ORM is doing load-bearing work
beneath every query: bind-parameter safety, the `search_readonly` alias, dimension scoping, and
returning model instances the envelope serializers understand. Any mechanism that leaves the
ORM has to re-earn each of those by hand. The ladder makes the cost of each step explicit.

This requirement does not pre-build rungs 2–5. It records the *order to climb in* and the
*invariants that hold at every rung*, so that the variable-length-path (`WITH RECURSIVE`) and
`WITH`-pipelining work — both of which will need rung 4 — has a documented contract to lower
against. It is the future-seam discipline applied to compilation strategy: name the seams and
the selection order; build a rung only when a query shape forces it.

#### Implementation

**The lowering principle.** The compiler lowers a query to the **lowest rung that can express
it**. Each step up the ladder is a deliberate escalation that should be visible and justified in
review — never reached for as a convenience when a lower rung would do.

**The rungs.**

| Rung | Mechanism | Reach for it when | Cost |
| :---: | --- | --- | --- |
| 1 | Django ORM `QuerySet` composition (`.filter`, `.annotate`, `Count(filter=Q)`, `Exists`, `Subquery`, `Window`) | The query is expressible as ORM queryset composition. The default, and the only rung the current executor uses. | None beyond the ORM's own. |
| 2 | ORM + a `Func` / `Expression` subclass wrapping a PostgreSQL function | A built-in or custom PG function must appear in a `SELECT` expression (`jsonb_path_query`, a window function, a custom aggregate). | A small, reviewed `Func` subclass. Stays inside the ORM — no guarantee is lost. |
| 3 | A `RawSQL` expression embedded in an otherwise-ORM `QuerySet` | Exactly one expression cannot be said in the ORM, but the surrounding query can. | The raw fragment must be hand-parameterized; the rest of the query keeps the ORM's guarantees. |
| 4 | A hand-written SQL template executed via `connection` | The query *shape* is beyond the ORM — chiefly `WITH RECURSIVE` for variable-length paths, and `WITH`-clause pipelining with intermediate materialization. | The whole statement is hand-authored: parameterization, the read-only alias, and dimension scoping become the compiler's responsibility, not the ORM's. |
| 5 | A persistent stored **function** created by a migration, invoked from rung 2–4 | A rung-4 SQL body is genuinely reused across many queries and benefits from being parsed and planned once by PostgreSQL. | A second implementation language (PL/pgSQL or SQL) and a persistent schema object with its own migration lifecycle. See preconditions below. |

**Invariants — preserved at every rung, regardless of how low the query is lowered:**

1. **Read-only.** Execution runs on the `search_readonly` alias and mutates no persisted state
   (`req-grid-traversal-exec-scope.sec-1`).
2. **Parameterized values.** Caller and `$param` values are passed as bind parameters — never
   string-interpolated into SQL. A hand-written rung-4 CTE still parameterizes.
3. **Dimension scoping** is applied as it would be at rung 1.
4. **Canonical envelope.** Results still normalize to the canonical `{nodes, edges, rows}`
   envelope (`req-grid-traversal-exec-pipeline-4`).
5. **Capture-seam visibility.** The statement is still issued through `connection`, so
   `capture_sql()` records it (`req-grid-traversal-exec-sql-capture`). This is why the Gridkin
   expected-SQL snapshot discipline carries over unchanged to a raw-SQL backend — the snapshot
   simply grows; the validation harness does not care which rung produced the SQL.

The rung table is the memorable part; the invariant list is the load-bearing part. A rung is
only correctly used when all five invariants still hold.

**Rung 5 preconditions.** Rung 5 is the highest-cost rung and is gated, not forbidden:

- It is a stored **function**, never a stored **procedure**. A read-only language emits
  `SELECT`s, and a procedure cannot be `CALL`ed inside a `SELECT`; the read-only contract
  excludes procedures by construction, not by preference.
- The function body must be genuinely reused across multiple query shapes — a body used by one
  query belongs at rung 4.
- The function is managed as a first-class tracked artifact: created/altered by a Django
  migration, described by a spec requirement, and covered by a Gridkin (or equivalent)
  snapshot. A stored function that is tracked, specced, and tested is consistent with TAP's
  data-object-management posture; an untracked one is not.
- The residual cost — a second implementation language, and a persistent schema object whose
  migration lifecycle must order correctly against table migrations — is accepted explicitly in
  the requirement that introduces the function.

**Current state.** The executor uses **rung 1 exclusively**. Rungs 2–5 are the documented,
sanctioned escalation path; none is exercised yet. The first rung-4 use is anticipated when
variable-length paths or `WITH` pipelining land (Gryphon wishlist E1 / F1).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-traversal-exec-lowering-1 | Lowest-Rung Rule | Implemented | The compiler lowers a query to the lowest ladder rung that can express it; a higher rung is a deliberate, review-visible escalation. | |
| req-grid-traversal-exec-lowering-2 | Invariants Hold At Every Rung | Implemented | Read-only alias, bind-parameterized values, dimension scoping, canonical-envelope normalization, and capture-seam visibility are preserved at every rung. | The contract that keeps Gridkin valid across backends |
| req-grid-traversal-exec-lowering-3 | Rung 1 Is The Current Backend | Implemented | The current executor lowers exclusively to rung 1 (ORM querysets); rungs 2–5 are documented but unexercised. | |
| req-grid-traversal-exec-lowering-4 | Rung 5 Is A Stored Function, Gated | Implemented | If rung 5 is reached it is a PostgreSQL function (never a procedure) and satisfies the rung-5 preconditions: cross-query reuse, first-class tracked-artifact management, explicit cost acceptance. | |

#### Future

- Publish per-construct lowering rules (which gryphon shape lowers to which rung) once rung 4
  is first exercised — this dovetails with the `req-grid-traversal-exec-pipeline` Future note.
- When a logical plan IR is introduced (`req-grid-traversal-exec-compiler` Future), each plan
  node's lowering step selects a rung against this ladder; the ladder becomes that step's
  contract.
- Revisit whether a PostgreSQL graph extension (e.g. Apache AGE) belongs as a distinct backend
  rather than a sixth rung, if reachability queries outgrow hand-written recursive CTEs
  (Gryphon wishlist E3).


### gryphon Safety Scope
----
RID: `req-grid-traversal-exec-scope.sec`
Status: `Implemented`

gryphon execution is a security-sensitive read surface and must remain constrained to
TAP-approved graph data and read-only execution.

#### Implementation

gryphon execution must:

- remain read-only (all queries run on the `search_readonly` DB alias)
- stay scoped to TAP-managed graph data
- reject unsupported clauses or functions at parse time rather than runtime
- validate runtime inputs before backend execution
- preserve TAP control over result normalization and execution limits

gryphon text must not be treated as arbitrary SQL, arbitrary Python, or arbitrary
database-native graph syntax supplied by the caller.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-traversal-exec-scope.sec-1 | Read Only | Implemented | gryphon execution does not mutate persisted TAP state. | All queries run on `search_readonly` alias |
| req-grid-traversal-exec-scope.sec-2 | Tap Scope Only | Implemented | gryphon compilation and execution stay scoped to TAP-approved graph data. | |
| req-grid-traversal-exec-scope.sec-3 | Unsupported Syntax Rejected At Parse | Implemented | Unknown or disallowed gryphon constructs are rejected at parse time, not runtime. | |
| req-grid-traversal-exec-scope.sec-4 | Inputs Validated Before Execution | Implemented | Runtime inputs are validated before the backend plan runs. | |

#### Future
Document backend-specific guardrails once TAP chooses its first concrete traversal compiler
target beyond ORM.


### SQL Capture Seam
----
RID: `req-grid-traversal-exec-sql-capture`
Status: `Implemented`

The executor exposes a read-only seam that records the SQL a gryphon run issues,
for snapshot testing and the `gryphon explain` developer surface.

#### Implementation

A gryphon query compiles to one or more Django ORM `QuerySet`s — a type scan
produces one; multi-stage patterns (hub-and-spoke, edge-type scan, the advanced
aggregation path) produce several, because a later stage is built from an earlier
stage's results. There is no single `QuerySet.query` that represents "the query",
so capture happens during execution rather than as a pure compile step.

The seam lives in `tap_grid/gryphon/capture.py`:

- `capture_sql(*db_aliases)` — a context manager that installs a
  `connection.execute_wrapper` for the block and yields a `SqlCapture`. Every
  `SELECT` / `WITH` statement executed inside the block is recorded, in execution
  order, with its bound parameters. Transaction-management statements (SAVEPOINT,
  RELEASE, ...) are filtered out.
- `gryphon_stage(label)` — a context manager the executor wraps each dispatch
  branch with, tagging that branch's statements (`type-scan`, `hub-and-spoke`,
  `edge-type-scan`, `advanced`). A no-op beyond a context-var set when no capture
  is active.
- `explain_gryphon_raw(query, inputs, ...)` — runs a query and returns
  `{"envelope": <canonical envelope>, "sql": <SqlCapture>}`.

The seam is read-only and changes no execution behavior; with no capture active
it costs only a context-var set per dispatch branch.

For the captured SQL to be stable across processes, the executor sorts the
entity-id collections it filters with `pk__in` / `entity_id__in` before building
those querysets — Python set iteration order is hash-randomized per process and
would otherwise vary the emitted `IN (...)` list without changing results.

This seam is the basis of the Gridkin expected-SQL snapshot (`spec-gridkin-v0.md`,
`req-gridkin-explain-snapshot`) and the future `gryphon explain` developer surface
(Gryphon wishlist H3).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-traversal-exec-sql-capture-1 | Captures Executed Reads | Implemented | `capture_sql()` records every `SELECT` a gryphon run executes inside the block, in execution order. | |
| req-grid-traversal-exec-sql-capture-2 | Stage Labelled | Implemented | Each captured statement carries the executor dispatch stage that produced it. | |
| req-grid-traversal-exec-sql-capture-3 | Deterministic SQL | Implemented | The executor sorts `pk__in` / `entity_id__in` id collections so the captured SQL is byte-stable across processes. | |
| req-grid-traversal-exec-sql-capture-4 | Read-Only And Inert | Implemented | The seam changes no execution behavior and is inert when no capture is active. | |
| req-grid-traversal-exec-sql-capture-5 | Explain Entry Point | Implemented | `explain_gryphon_raw()` returns both the canonical envelope and the captured SQL. | |

#### Future
Extend the seam with PostgreSQL `EXPLAIN ANALYZE` for query-plan and timing
inspection (Gryphon wishlist P2), and surface it as a `gryphon explain` CLI /
management command (wishlist H3). Both reuse this capture, not a parallel one.


## Status Vocabulary

| Status States |  |
| --- | --- |
| Proposed |  |
| Implemented | Requirement is accepted and ready to be implemented |
| In Development |  |
| Implemented |  |
| Verified |  |
| Refactoring |  |
| Deprecating |  |
| Deprecated | Not part of the current architecture and should not be implemented |
