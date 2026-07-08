# gryphon Execution Specification

> **Development doctrine (standing filter).** Before any change to the Gryphon language, executor, or tests, consult [`doc-gryphon-commandments.md`](../../docs/doc-gryphon-commandments.md) — the standing thou-shalt/shalt-not doctrine for all Gryphon work (RFC-2119 commandments with Reason + Enforcement, plus a Forthcoming section). Requirements here SHOULD stay consistent with it; it cites requirements here as its Enforcement anchors.

## Philosophy

gryphon text is compiled by TAP into an internal execution plan and does not execute directly as
raw backend code. This preserves the service-layer control TAP already wants for searches and
future AI-authored query definitions — and makes gryphon useful as a safer trust boundary than
direct backend query execution.

**Gryphon commandment guidance.** Any change to Gryphon validation, lowering, executor dispatch,
SQL capture, result packaging, or lowering-ladder usage must read and apply
[`doc-gryphon-commandments.md`](../../docs/doc-gryphon-commandments.md). The
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
| req-grid-traversal-exec-row-materialization | [Row Materialization Backend](#row-materialization-backend) | Implemented | The **row-projection** half of the Package stage is one shared backend fed a resolved `MaterializationPlan`; every pattern shape dispatches to build a queryset + plan (Layer A) then feeds the *same* projection / DISTINCT / ORDER BY / LIMIT row tail (Layer B); JSON projection lowered to Postgres. Envelope serialization is out of scope |
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


### Row Materialization Backend
----
RID: `req-grid-traversal-exec-row-materialization`
Status: `Implemented`

The **row-projection half** of the Package stage (`req-grid-traversal-exec-pipeline`, step 6) is a **single shared backend**, not a per-dispatch reimplementation. Scope is deliberately bounded to **row projection only**: graph-envelope serialization is a *separate* concern with genuinely different needs (see [Scope boundary](#scope-boundary-rows-not-envelopes) below) and is **out of scope** for this requirement. The executor separates two concerns that today are fused inside every row-producing dispatch function:

- **Layer A — Pattern → (QuerySet + MaterializationPlan)** (shape-specific, dispatched): each MATCH shape builds a Django queryset with the right JOINs/filters, **and resolves its `RETURN` clause into a `MaterializationPlan`** — see the plan object below. A single-model scan, an `Edge`-rooted chain (`_build_chain_queryset`), and a LEFT-JOIN + `Count(filter=)` for `OPTIONAL MATCH` differ essentially and stay dispatched.
- **Layer B — MaterializationPlan → rows** (shape-agnostic): given the plan, produce the row-projection `rows` list. Logically identical regardless of how the queryset was built, and is **one** backend.

#### Background And Motivation

The row tail is currently re-implemented **four times**:

| Tail | Current site | Projection mechanism | ORDER BY / LIMIT |
| --- | --- | --- | --- |
| type-scan rows | `_execute_type_scan` | Python `_project_node` (walks JSON in Python) | `_apply_order_limit_typescan` |
| edge-chain non-aggregate | `_compute_rows` (non-agg branch) | `.values()` | `_resolve_order_cols` |
| edge-chain aggregate | `_compute_rows` (agg branch) | `.values().annotate(Count)` | `_resolve_order_cols` |
| OPTIONAL MATCH | `_execute_optional_match` | `.values().annotate(Count)` | `_resolve_order_cols` |

The uuid-stringify idiom (`str(val) if hasattr(val, "hex")`) is hand-copied into each. This is an **emergent** structure, not a designed one — dispatch functions that each grew a full row tail — and the duplication is a standing tax with a bug-generating signature: every cross-cutting row feature must be applied *N times* (`ORDER BY` landed in two tails, `LIMIT` in two, the `DISTINCT` design (`req-grid-gryphon-distinct`) had to touch three or four). Two silent-wrong-answer classes surfaced directly from this shape during the DISTINCT design review:

- a projection/aggregate path (the OPTIONAL MATCH tail) that a new row-flag does not know about and **silently drops** it (`GRY-ARCH-3`);
- a per-tail ordering detail (the type-scan's inherited `order_by("entity__name")`) that **poisons** a downstream operation (`SELECT DISTINCT`) in one tail but not the others.

The fix is structural, and it is the comparative study's central prescription (`doc-gryphon-comparative-findings.md`): **shrink the Python glue between the pattern and the trusted plan; reliability is structure, not another careful feature.** Collapsing the four tails into one backend makes both bug classes *inexpressible* (`GRY-ARCH-4`) rather than test-caught: a row feature lands in one place and reaches every shape, and a per-tail ordering divergence has nowhere to live.

This is **not** a new IR (`GRY-ARCH-6`): the Django QuerySet plus the PostgreSQL plan remains the borrowed IR; the `MaterializationPlan` is a thin *resolved-projection* descriptor, not a logical-plan layer. The target already substantially exists — `_execute_advanced` already factors Layer A into `_build_clause_queryset` and Layer B into `_compute_rows`, and `_resolve_order_cols` is already shared — so the work is largely *routing the two non-conforming shapes (type-scan, OPTIONAL MATCH) through the existing seams*, not inventing them.

#### The MaterializationPlan (why not just `(queryset, bindings)`)

A loose `(queryset, bindings)` contract is **insufficient**, because two shapes carry state that bindings alone do not:

- **OPTIONAL MATCH's zero-preserving COUNT is local state.** The correct count is `Count(edge_path, filter=opt_q)` — where `edge_path` and `opt_q` are computed inside `_execute_optional_match`, not derivable from `COUNT(g)` plus `g`'s binding. A generic backend that only sees `COUNT(g)` would build the wrong (non-filtered) count.
- **Path resolution is shape-relative.** Type-scan resolves field paths model-relative (`_typescan_orm_path` → `tags__Project`); the advanced path resolves `Edge`-chain-root-relative (`_resolve_orm_path`). The backend must not have to know which.

So Layer A hands Layer B a resolved **`MaterializationPlan`**: the queryset plus an ordered list of **projection descriptors**, each one either

- a **group-by column** — a fully-resolved ORM expression (the builder has *already* applied its shape's path resolver) + user alias + declared field type (for JSON type fidelity); or
- an **aggregate column** — a fully-built annotation expression (edge-chain `Count(g_id)`; OPTIONAL MATCH `Count(edge_path, filter=opt_q)`, carrying its hidden local state *into* the plan) + user alias —

plus the `distinct` flag, `order_by`, and `limit`. The backend applies the plan uniformly (annotate group expressions → `.values(group_internals)` → `.annotate(agg_expressions)` → DISTINCT → tiebroken ORDER BY → LIMIT → uuid-stringify → rows) and never inspects pattern shape or resolves a path itself. Concretely this is a `Binding.resolve(field_path)`-style typed resolver per shape (not loose dicts), so the contract is explicit and the wrong-count / wrong-prefix traps are structurally closed.

Two contract details are made explicit rather than left implicit — both preserved **byte-identically** by this refactor:

- **`distinct` + aggregate is rejected in the backend, before execution.** When `plan.distinct` is set *and* any aggregate descriptor is present, `materialize_rows` raises `SearchExecutionError` rather than letting a generic `.distinct()` drift onto an annotated (GROUP BY) queryset. Placing the rejection in the backend makes it the **single structural home** for the aggregate-return-DISTINCT rejection (`req-grid-gryphon-distinct-14`) across every shape — including OPTIONAL MATCH, whose plan always carries a `Count`. (During this refactor `plan.distinct` is always `False`, since DISTINCT is unbuilt; the rule is specified now so the DISTINCT feature inherits it for free — `GRY-SEC-4`, lay the edge while the surface is open.)
- **Output key order and duplicate user-aliases follow current behavior.** Row-dict key order follows the RETURN projection order (insertion order); two RETURN items resolving to the same user alias collapse **last-write-wins** (the current `row[user] = …` overwrite). The plan preserves both exactly; tightening duplicate aliases into a parse/exec rejection is named in Future, not taken here.

#### Scope boundary: rows, not envelopes

Graph-envelope serialization is **explicitly out of scope** and stays on its current sites, because it needs state the row plan does not carry: `_collect_graph_envelope` takes the original `PathPattern` and recovers **anonymous structural edges** that are not in `bindings` at all. Unifying envelopes would require a richer plan carrying structural hop descriptors — a larger design that is deferred until (a) the row backend has proven the plan object and (b) there is demand. Folding "rows-vs-envelope shaping" into this backend now would be the exact over-reach this requirement avoids; the earlier draft's claim that the backend owns envelope shaping is retracted.

#### Implementation

- **One `materialize_rows(plan)` entry point** owns the whole row tail: annotate group/aggregate expressions, `.values()`, `DISTINCT`, `ORDER BY` (tiebroken), `LIMIT`, uuid-stringify. It is a generalization of today's `_compute_rows`, reached by **every** row shape via the plan.
- **Layer A stays three shape-builders**, each producing a `MaterializationPlan`; the type-scan and OPTIONAL MATCH paths are refactored to build a plan and call `materialize_rows`, as `_execute_advanced` already does. The four inlined tails (`_project_node`'s projection loop, `_apply_order_limit_typescan`, the OPTIONAL MATCH inline tail, the duplicate uuid-stringify loops) are **deleted** (`GRY-ARCH-4`).
- **JSON projection is lowered to PostgreSQL, not walked in Python.** The type-scan tail walks nested `data`-lane fields in Python (`_resolve_envelope_path`'s `dict.get`) only because it was written independently of the WHERE lowering — which already resolves `n.data.tags.Project` to a Postgres JSON path via `_typescan_orm_path`. The plan's group-by descriptor reuses that same resolver, so a JSON scalar sub-key is projected in SQL through `.values(...)`. **Operator precision:** projection uses the **JSON-returning** transform (`->` / `#>`, Django `KeyTransform`) so the decoded Python type is preserved, *not* the text-returning `->>` / `#>>` (`KeyTextTransform`) that WHERE uses for string comparison — a live Django probe confirms `.values("tags__team")` lowers through `->`. Two behaviors are reproduced exactly (byte-identical), each pinned by a **new** scenario (below):
  - **Type fidelity:** a JSON number projects as `int`, not `"10"`; the declared schema (`GRY-SEM-1`) drives the expected type.
  - **Absent-key vs JSON-null:** the `dict.get` walk collapses missing-key and stored-JSON-`null` both to `None`; the `.values()` projection reproduces that collapse. The finer `GRY-SEM-3` distinction is **deferred** (Future), not smuggled into this refactor.
- **JSON RETURN-projection parity scenarios are authored *before* the code change** (`GRY-TEST-5`, the reproduce-first discipline). The existing JSON Gridkin scenarios are **WHERE-focused**; there is no RETURN-projection coverage, so "byte-identical" has no teeth until it exists. New scenarios pin the *current* executor's behavior for the **conformant** cases — a scalar sub-key projection, an absent key, a stored JSON `null`, and "walk into a scalar gives `None`" — as expected-correct, held invariant across the refactor.
- **The nested-container projection case is a *preserved non-conformance*, not blessed parity.** The type-scan Python path today returns a nested object/array for `RETURN n.data.tags` (a container value), which **violates `req-grid-gryphon-rows-5`** ("row values are primitives only") — a pre-existing spec-vs-code divergence this design surfaced. A parity scenario for the container case therefore **documents preserved current behavior explicitly labelled as a `req-grid-gryphon-rows-5` non-conformance**, not as endorsed semantics; the refactor keeps it byte-identical (it does not fix *or* worsen it), and reconciling the contract (enforce primitives-only by rejecting a container projection, or relax `rows-5`) is a separate, opt-in change named in Future. Canonizing the violation as "correct" is explicitly avoided.
- **The five lowering-ladder invariants (`req-grid-traversal-exec-lowering-2`) hold unchanged** — read-only alias, bind-parameterized values, dimension scoping, canonical-envelope normalization, capture visibility — the backend stays at rung 1. Deterministic-SQL discipline (`GRY-ARCH-9`, sorted `pk__in`, tiebroken `ORDER BY`) is applied once in the backend.
- **Behavior is byte-identical.** This changes *structure*, not results: every existing Gridkin expected-envelope (plus the new JSON-projection scenarios) stays green with **zero** oracle edits; captured-SQL snapshots may shift only where a tail emitted needlessly-different SQL, and each shift is eyeballed and oracle-confirmed before regeneration (`GRY-TEST-1/6`).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-traversal-exec-row-materialization-1 | Single Row Backend | Implemented | One `materialize_rows(plan)` backend owns projection, DISTINCT, ORDER BY, LIMIT, and uuid-stringify for row projections; no dispatch function reimplements the row tail. | Rows only; envelopes out of scope |
| req-grid-traversal-exec-row-materialization-2 | Every Row Shape Routes Through It | Implemented | Type-scan, edge-chain (single- and multi-hop), and OPTIONAL MATCH reach row results through `materialize_rows`; each Layer-A builder produces a `MaterializationPlan`. | |
| req-grid-traversal-exec-row-materialization-3 | Plan Carries Resolved Descriptors | Implemented | The plan carries fully-resolved group-by expressions and aggregate expressions — including OPTIONAL MATCH's zero-preserving `Count(edge_path, filter=opt_q)` — so no shape-local state (filtered count, path prefix) bypasses the backend. | Closes the loose-`(queryset, bindings)` trap |
| req-grid-traversal-exec-row-materialization-4 | Old Row Tails Deleted | Implemented | `_project_node`'s projection loop, `_apply_order_limit_typescan`, the OPTIONAL MATCH inline tail, and the duplicate uuid-stringify loops are removed, not left as dead alternates. | `GRY-ARCH-4` |
| req-grid-traversal-exec-row-materialization-5 | Envelopes Explicitly Out Of Scope | Implemented | Graph-envelope serialization is unchanged and not routed through this backend; it needs structural (anonymous-edge) state the row plan does not carry. | Deferred to Future |
| req-grid-traversal-exec-row-materialization-6 | JSON Projected In Postgres | Implemented | Nested `data`-lane scalar projection compiles to a Postgres JSON extraction via the shared resolver using the JSON-returning transform (`->`/`KeyTransform`), not a Python `dict.get` walk and not the `->>` text transform. | |
| req-grid-traversal-exec-row-materialization-7 | JSON Type Fidelity Preserved | Implemented | A JSON scalar sub-key projects with its declared type (a JSON number is an `int`, not text), pinned by a new scenario. | |
| req-grid-traversal-exec-row-materialization-8 | Absent-Key vs JSON-Null Unchanged | Implemented | The Postgres projection reproduces the current collapse (missing key and stored JSON `null` both → `None`); the finer `GRY-SEM-3` distinction is deferred. | Keeps the refactor byte-identical |
| req-grid-traversal-exec-row-materialization-9 | JSON RETURN Parity Scenarios Authored First | Implemented | New Gridkin scenarios pin the *current* executor's RETURN-projection JSON behavior for the **conformant** cases (scalar sub-key, absent key, stored null, walk-into-scalar→None) **before** the code change, extending the regression net that "byte-identical" depends on. | Reproduce-first, `GRY-TEST-5` |
| req-grid-traversal-exec-row-materialization-10 | Cross-Cutting Feature Lands Once | Implemented | A row-level feature (DISTINCT, ORDER BY, LIMIT, a future SKIP / numeric aggregate) is implemented in the backend once and reaches every shape; a path cannot silently omit it. | Forecloses the DISTINCT-review P1a class |
| req-grid-traversal-exec-row-materialization-11 | Byte-Identical Behavior | Implemented | Every existing Gridkin expected-envelope, plus the new JSON-projection scenarios, stays green with zero oracle edits; SQL-snapshot diffs are audited one by one and oracle-confirmed before regeneration. | The refactor safety bar |
| req-grid-traversal-exec-row-materialization-12 | Rung-1 Invariants Hold | Implemented | The backend stays at rung 1; read-only alias, bind-parameterization, dimension scoping, canonical envelope, capture visibility, and deterministic SQL are preserved. | `req-grid-traversal-exec-lowering-2`, `GRY-ARCH-9` |
| req-grid-traversal-exec-row-materialization-13 | Container Projection Is Preserved Non-Conformance | Implemented | The nested-container projection case is pinned as *preserved current behavior labelled a `req-grid-gryphon-rows-5` non-conformance*, not blessed parity; the refactor neither fixes nor worsens it, and reconciliation is deferred to Future. | Does not canonize the violation |
| req-grid-traversal-exec-row-materialization-14 | DISTINCT Flag Fails Closed In Backend | Implemented | `materialize_rows` never silently ignores `plan.distinct`: an aggregate-bearing plan rejects with the aggregate message (`req-grid-gryphon-distinct-14`, the single structural home across every shape incl. OPTIONAL MATCH); a non-aggregate plan rejects "not implemented yet" until `req-grid-gryphon-distinct` wires the real `.values().distinct()`. Both fire before execution. | `plan.distinct` is unreachable via a query today (`ReturnClause` has no `distinct` field) but fails closed if set — never a silent no-op (`GRY-ARCH-3`); pinned by a below-service-layer backend test |
| req-grid-traversal-exec-row-materialization-15 | Output Key Order And Duplicate Aliases Preserved | Implemented | Row-dict key order follows projection order; duplicate user aliases collapse last-write-wins — both preserved byte-identically. A future rejection of duplicate aliases is named, not taken. | Made explicit in the plan contract, not left implicit |
| req-grid-traversal-exec-row-materialization-16 | RETURN Projection Boundary Not Widened | Implemented | The shared resolver (`_typescan_orm_path`) is deliberately more permissive than a v1 RETURN projection — it accepts bracket-key steps (`data.tags["k"]`) and multi-step walks into JSON-typed spine fields (`dimensions.<k>`), both valid in a WHERE predicate. Routing RETURN through it MUST NOT widen the projectable surface: a RETURN-side guard (`_reject_non_projectable_return_path`) reproduces the pre-unification `_resolve_envelope_path` acceptance set (data lane admits dot-steps only; spine fields are not walked into), so the reject→accept boundary is byte-identical too, not only accepted results. | Byte-identical covers rejections, not just results; `GRY-ARCH-3`. Widening RETURN to match WHERE is Future. |

#### Future

- **Envelope-serialization unification.** Fold the ~5 envelope sites into a shared backend once there is demand — and only behind a richer plan that carries **structural hop descriptors** (the anonymous-edge state `_collect_graph_envelope` needs), proven first on the row plan.
- **Reconcile the `req-grid-gryphon-rows-5` container non-conformance.** The type-scan path returns nested containers for a container-valued projection, violating the primitives-only row contract. Resolve it deliberately — either enforce the contract (reject a container projection loudly) or relax `rows-5` — as a separate change with its own behavior-change budget, not inside this byte-identical refactor. (This is the reconciliation the DISTINCT container boundary, `req-grid-gryphon-distinct-6`, also points at.)
- **Duplicate user-alias rejection.** Today duplicate RETURN aliases collapse last-write-wins; a future tightening may reject them at parse or in the backend, once a demand or a footgun report warrants it.
- **Widen RETURN projection to match WHERE.** RETURN projection is intentionally narrower than WHERE in v1 (dot-step `data` lane only; no multi-step walk into JSON-typed spine fields like `dimensions`). The unification revealed the asymmetry — WHERE and RETURN now share one resolver but RETURN gates the extra surface off (`req-grid-traversal-exec-row-materialization-16`). Aligning RETURN's accepted surface with WHERE's (bracket keys, `dimensions.<k>` projection) is a deliberate future capability with its own spec + Gridkin scenarios, not a side effect of this byte-identical refactor.
- **Absent-key vs JSON-null distinction** (`GRY-SEM-3`): a later, opt-in, oracle-first change to distinguish a missing key from a stored JSON `null` (via `#>` + `jsonb_typeof`), deliberately *not* bundled into this byte-identical refactor.
- Once `WITH` pipelining lands (`GRY-F-5`), the backend is the natural seam for per-stage `WHERE` attachment and value carry-through — designed toward, not built ahead of demand (`GRY-ARCH-6`).
- `req-grid-gryphon-distinct` lands as the first row feature *added into* this backend rather than across the four tails — the worked proof that the structure holds.


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
