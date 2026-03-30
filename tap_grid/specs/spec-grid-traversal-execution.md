# Grid Traversal Execution Specification

## Philosophy

Traversal text is compiled by TAP into an internal execution plan and does not execute directly
as raw backend code. This preserves the service-layer control TAP already wants for searches and
future AI-authored query definitions — and makes the traversal language useful as a safer trust
boundary than direct backend query execution.

## Goals

|    |              |                                                                          |
| :---: | ---       | ---                                                                      |
| 1. | Safe          | Execution is read-only and scoped to TAP-managed graph data              |
| 2. | Backend-agnostic | Traversal text does not commit to one execution engine at rest        |
| 3. | Auditable     | Grammar file is a readable, diffable spec artifact for the syntax        |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-grid-traversal-exec-pipeline | [Execution Pipeline](#execution-pipeline) | Approved for Development | Normalize → parse → validate → compile → execute → package |
| req-grid-traversal-exec-compiler | [Compiler Strategy](#compiler-strategy) | Approved for Development | lark as v1 parser; grammar.lark is the spec artifact |
| req-grid-traversal-exec-scope.sec | [Traversal Safety Scope](#traversal-safety-scope) | Approved for Development | Read-only, TAP-scoped, unsupported syntax rejected, inputs validated |


### Execution Pipeline
----
RID: `req-grid-traversal-exec-pipeline`
Status: `Approved for Development`

Traversal text passes through a defined pipeline before any backend query runs.

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
| req-grid-traversal-exec-pipeline-1 | Traversal Is Parsed Before Execution | Approved for Development | Traversal text is parsed into TAP-controlled structure before backend execution. | |
| req-grid-traversal-exec-pipeline-2 | Traversal Is Backend-Agnostic At Rest | Approved for Development | Stored traversal text is not itself backend-specific SQL or ORM code. | |
| req-grid-traversal-exec-pipeline-3 | Compilation Produces Tap-Controlled Plan | Approved for Development | TAP compiles validated traversal text into an internal execution plan. | |
| req-grid-traversal-exec-pipeline-4 | Results Are Normalized | Approved for Development | Execution results are normalized into the canonical envelope before return. | |

#### Future
Once execution backends stabilize, publish exact lowering rules from traversal syntax into
SQL or ORM plans in this spec.


### Compiler Strategy
----
RID: `req-grid-traversal-exec-compiler`
Status: `Approved for Development`

TAP uses `lark` as the v1 parser library. The grammar file (`grammar.lark`) is the authoritative
syntax specification for the traversal language.

#### Implementation

**Parser:** `lark` (pure Python, LALR(1) by default). Chosen over hand-rolling because the
grammar surface (MATCH/WHERE/RETURN, patterns, filters, combinators, bounded repetition, JSON
path access, `$vars`, `AS` aliases) is large enough that a grammar library pays for itself in
maintainability. Chosen over a full Cypher parser because a Cypher parser accepts `CREATE`,
`MERGE`, `SET`, `DELETE` — rejecting those semantically rather than at the grammar level
produces confusing errors for users writing valid Cypher that TAP does not support.

**Grammar file location:** `tap_grid/traversal/grammar.lark`

The grammar file is:
- the canonical, diffable record of what syntax TAP accepts
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
| req-grid-traversal-exec-compiler-1 | Lark Used As V1 Parser | Approved for Development | The v1 traversal parser is implemented with the lark library. | |
| req-grid-traversal-exec-compiler-2 | Grammar File Is Spec Artifact | Approved for Development | `grammar.lark` is the authoritative syntax specification, checked in alongside the implementation. | |
| req-grid-traversal-exec-compiler-3 | Parse Tree Transforms To Frozen AST | Approved for Development | Lark tree output is transformed into TAP frozen dataclasses, not consumed directly. | |
| req-grid-traversal-exec-compiler-4 | Parse Errors Raise TraversalParseError | Approved for Development | Failed parses surface as `TraversalParseError` with message and position information. | |

#### Future
If TAP later needs a richer query planner (query optimization, multiple backends, cost
estimation), consider whether the grammar-to-AST step should produce a logical plan IR before
lowering to a physical plan.


### Traversal Safety Scope
----
RID: `req-grid-traversal-exec-scope.sec`
Status: `Approved for Development`

Traversal execution is a security-sensitive read surface and must remain constrained to
TAP-approved graph data and read-only execution.

#### Implementation

Traversal execution must:

- remain read-only (all queries run on the `search_readonly` DB alias)
- stay scoped to TAP-managed graph data
- reject unsupported clauses or functions at parse time rather than runtime
- validate runtime inputs before backend execution
- preserve TAP control over result normalization and execution limits

Traversal text must not be treated as arbitrary SQL, arbitrary Python, or arbitrary
database-native graph syntax supplied by the caller.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-traversal-exec-scope.sec-1 | Read Only | Approved for Development | Traversal execution does not mutate persisted TAP state. | All queries run on `search_readonly` alias |
| req-grid-traversal-exec-scope.sec-2 | Tap Scope Only | Approved for Development | Traversal compilation and execution stay scoped to TAP-approved graph data. | |
| req-grid-traversal-exec-scope.sec-3 | Unsupported Syntax Rejected At Parse | Approved for Development | Unknown or disallowed traversal constructs are rejected at parse time, not runtime. | |
| req-grid-traversal-exec-scope.sec-4 | Inputs Validated Before Execution | Approved for Development | Runtime inputs are validated before the backend plan runs. | |

#### Future
Document backend-specific guardrails once TAP chooses its first concrete traversal compiler
target beyond ORM.


## Status Vocabulary

| Status States |  |
| --- | --- |
| Proposed |  |
| Approved for Development | Requirement is accepted and ready to be implemented |
| In Development |  |
| Implemented |  |
| Verified |  |
| Refactoring |  |
| Deprecating |  |
| Deprecated | Not part of the current architecture and should not be implemented |
