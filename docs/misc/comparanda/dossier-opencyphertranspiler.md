# Dossier — openCypherTranspiler (Microsoft)

Clone: `6c778b99926a8be22833879cc901624e00634176` (master), read 2026-07-04. License: MIT.
Repo: https://github.com/microsoft/openCypherTranspiler — clone at `undefined/opencyphertranspiler` (disposable; all `file:line` anchors are at the clone SHA).
Protocol: `docs/misc/doc-gryphon-comparative-eval-protocol.md` §4.4. **Lens E primary.**

## Snapshot

A C#/.NET library that transpiles a read-only openCypher subset into **SQL text**
(reference renderer: T-SQL), built at Microsoft to query Windows 10 telemetry in Azure
Data Lake as a property graph (`README.md:5-7`). Three-stage pipeline: ANTLR4 parser
over the official openCypher grammar → AST → **explicit relational-algebra logical
plan** → SQL renderer (`README.md:9-17`, `src/LogicalPlanner/LogicalPlan.cs:20-24`).
It is the roster's *purest* Cypher→SQL cousin (protocol §2.1) and — like Gryphon —
**read-only by construction**: every updating clause is rejected at the visitor
(`src/openCypherParser/AST/CypherVisitor.cs:488,889`).

Inclusion score (§2.2): relational-lowering relevance **maximal** (literal SQL-text
transpiler); source availability/readability **high** (MIT, ~6k LOC of core, clean);
history richness **low** — 28 commits total, active July–November 2019, then only two
2022 compliance commits (`git log --oneline`, 6c778b9..be9679e); semantics
documentation **low-medium** (README roadmap is an honest non-goals list,
`README.md:57-66`; no RFC trail). Verdict: deep on Lens E, thin-but-real Lens H.

## Lens E — Execution ★ PRIMARY

### Pipeline shape / IR count

Two IRs between text and SQL: (1) an AST of `QueryNode`/`PartialQueryNode`/
`QueryExpression` trees built by `CypherVisitor` (`src/openCypherParser/AST/`), and
(2) a **logical plan**: a DAG of exactly **five relational operator types** —
`DataSourceOperator`, `JoinOperator`, `SelectionOperator`, `ProjectionOperator`,
`SetOperator` (`src/LogicalPlanner/Logical/*.cs`; worked example of a MATCH/WITH/
OPTIONAL MATCH/WHERE/RETURN query as an operator tree in the code comment at
`LogicalPlan.cs:119-142`). Physical "execution" is delegated entirely to the target
RDBMS; the renderer is a pure plan→text function.

### Bottom-turtle question 1 — is there a logical-plan IR, and what does it buy?

**Yes — and it is the invariant choke point, not an optimizer.** `LogicalPlan
.ProcessQueryTree` runs a fixed sequence of whole-plan passes (`LogicalPlan.cs:49-82`):

1. **Build** the operator DAG from the AST (`CreateLogicalTree`, recursive).
2. **Bind** every `DataSourceOperator` against the graph schema — unknown label or
   edge type throws `TranspilerBindingException` (`src/LogicalPlanner/Logical/
   DataSourceOperator.cs:49-52,85-88`).
3. **Propagate data types top-down** through every operator
   (`PropagateDataTypes`, `LogicalPlan.cs:1025-1040`) — every field in every
   operator's schema gets a concrete .NET type, with **nullability as part of the
   type** (see OPTIONAL MATCH below).
4. **Propagate referenced fields bottom-up**
   (`UpdateActualFieldReferencesForEntityFields`, `LogicalPlan.cs:1047-1058`) —
   column pruning: only properties actually referenced by RETURN/WHERE/ORDER BY are
   carried, and a reference to a nonexistent alias/property throws
   `TranspilerBindingException` at this stage
   (`src/LogicalPlanner/Logical/LogicalOperator.cs:90-134`).

What the IR buys them, concretely: (a) **one place** where alias resolution, schema
binding, type legality, join-direction legality (`JoinOperator.cs:136-160` validates
that a directed relationship actually connects the bound node types) and column
pruning happen for *every* query shape — no per-shape re-assertion; (b) **plan-level
testability** — `tests/LogicalPlanner.Test/LogicalPlannerTest.cs` (545 lines) asserts
on plan structure via `DumpGraph()` (`LogicalPlan.cs:88-110`) independent of SQL; (c)
**typed nullability flow** (below). What it does *not* buy: optimization — the README
names this openly: "Logical plan is not further optimized and currently offloaded to
underlying RDBMS query engine" (`README.md:63`). A thin transpiler with an IR but *no
optimizer* is a coherent, shipped design point — the IR earns its keep purely as the
invariant-enforcement and bookkeeping layer.

**Is the IR itself a bug source? Yes — that's the honest price.** The correctness-fix
stream (Lens H) concentrates almost entirely in the IR's *propagation passes*, not in
the join lowering: `cc5a531` ("bug fixes handling extra refs from orderby/where" —
149 lines churned in `LogicalOperator.cs` alone) and `9e01425` ("bug fixes on field
type propagation" — filter-expression properties weren't type-bound during
propagation; fixed by binding them in `SelectionOperator.PropagateDateTypesForOutSchema`,
diff adds `SelectionOperator.cs:141-149`). The trade the history shows: an IR
forecloses per-shape executor divergence, and the bugs that remain are
bookkeeping-pass bugs that fail **loud** (binding exceptions), not silent wrong rows.

### Bottom-turtle question 2 — dispatch shape

**One uniform lowering; born unified.** Every query — type scan, k-hop, multi-pattern,
aggregation, UNION, OPTIONAL MATCH, WITH pipeline — becomes the same five operators,
and the renderer is a **single five-case switch** (`src/SQLRenderer/SQLRenderer.cs:
1066-1083`), each case a nested-`SELECT` template; unknown operator type throws
`TranspilerInternalErrorException` (`SQLRenderer.cs:1081`). A bare type scan is just
the degenerate plan `DataSource → Projection`; a 3-hop pattern is `DataSource ⋈ … ⋈
DataSource → Projection`. There are **no shape-special-cased execution paths at all**
— the special cases live at *parse time* as rejections (next section), never as
parallel lowerings. Consequently there is no "we unified the executor" refactor in
the history: the initial check-in (`5ec98d8`, 2019-07-25) already contains the
three-project parser/planner/renderer pipeline. The only refactors are readability
splits (`0d95c8e` "break operaters source file to improve readability", `b39032e`).

### Bottom-turtle question 3 — where are invariants enforced?

At the **plan construction/binding boundary**, once, for all shapes: alias-exists
(`LogicalOperator.cs:96`), property-exists-on-entity (`LogicalOperator.cs:126-130`),
schema-bind-or-throw (`DataSourceOperator.cs:49-52,85-88`), relationship-direction
legality (`JoinOperator.cs:143-153`), operand type legality via exhaustive tables
(`src/openCypherParser/AST/Expressions/QueryExpressionBinary.cs:47-104`), duplicate
relationship-alias rejection (`LogicalPlan.cs:660-667`), conflicting-traversal
detection (`LogicalPlan.cs:859-870`). The renderer *assumes* a validated plan and
guards its own assumptions with `Debug.Assert` + internal-error throws.

**The invariant they never had:** parameterization. Literals are string-interpolated
into the SQL text with only quote-escaping (`SQLRenderer.cs:312-315` `EscapeStringLiteral`;
`SQLRenderer.cs:740-752` renders values inline). A text-transpiler decoupled from
execution *cannot* own bind parameters, the connection, or a read-only role — Gryphon's
lowering-ladder invariants 1-2 (`spec-grid-traversal-execution.md`,
`req-grid-traversal-exec-lowering-2`) simply have no home in this architecture.
**Credit to Gryphon's compile-to-ORM bet**, recorded in Net read.

### Bottom-turtle question 4 — where does fail-closed live?

Pervasively at the **front door**, and structurally in the **lookup-table style** of
the back end:

- The visitor rejects ~20+ unsupported surfaces with `TranspilerNotSupportedException`:
  updating clauses (`CypherVisitor.cs:488,889`), `CALL` (`:614`), `UNWIND` (`:920`),
  variable-length/`*` ranges (`:1575`), multiple labels (`:1124`), inline property
  maps on patterns (`:1096,1175,1339`), returning whole entities (`:784` and
  `LogicalPlan.cs:324-328`), `CASE <expr> WHEN` form (`:1781`), unknown functions
  (`:1740`); a **`null` literal is itself unsupported** — `VisitOC_Literal` accepts
  only string/bool/number/list and throws on everything else
  (`CypherVisitor.cs:1922-1965`).
- Rendering is lookup-table-driven: operator→pattern (`SQLRenderer.cs:31-52`),
  aggregation→pattern (`:92-102`), cast-legality matrix with explicit `Invalid`
  entries that **throw** (`:112-236`, consumed at `:349-362`), function switch with
  throwing default (`:626-628`), expression-node switch with throwing else
  (`:763-766`). "No entry" is structurally an exception, never a silent skip.
- Even a semantics they couldn't implement safely is *blocked rather than
  approximated*: directionless traversal between same-typed endpoints throws with a
  "specify the direction" message instead of guessing a join
  (`LogicalPlan.cs:603-612`).

Can a path accept input it silently ignores (the envelope-WHERE shape)? At the plan
layer, essentially no: a `WHERE` always becomes a `SelectionOperator` node in the DAG
(`LogicalPlan.cs:439-446`), and the renderer either renders a Selection's
`FilterExpression` (`SQLRenderer.cs:1032-1036,943-947`) or the expression tree hits a
throwing default. The one genuine silent-wrongness seam they *do* have is ordering
(below) — and, tellingly, it is exactly the property their test harness never asserts
(Lens T).

### Join & traversal lowering (k-hop, var-length, OPTIONAL, aggregation)

- **MATCH → join planning.** Each pattern element gets a `DataSourceOperator`; the
  planner builds an alias adjacency matrix of join types, takes its transitive
  closure, and materializes `JoinOperator`s in three passes — **inner first, left
  second, cross last** — walking each pattern (`LogicalPlan.cs:680-967`; worked
  example in comment `:804-836`). Node⟷edge joins are equijoins on declared
  source/sink key fields with direction resolved by `GetJoinKeyPairInProperOrder`
  (`LogicalPlan.cs:596-637`). A k-hop pattern is k chained equijoins — no CTEs, no
  recursion.
- **Variable-length:** not supported; parse-time rejection (`CypherVisitor.cs:1575`)
  and named on the roadmap (`README.md:60`). A transpiler that cannot say
  `WITH RECURSIVE` in its target refuses the feature rather than approximating it.
- **OPTIONAL MATCH:** lowered to LEFT JOIN, with two structural protections:
  (1) *predicate placement* — `OPTIONAL MATCH ... WHERE ...` forks the plan: the
  filter is applied to the optional-side subplan **first**, then LEFT-joined back to
  the piped data on the shared entity aliases (`LogicalPlan.cs:370-393`). This is the
  textbook fix for the classic mis-scope where a WHERE rendered after the left join
  silently degrades it to an inner join. (2) *typed nullability* — the LEFT join's
  schema pass rewrites every right-side field to its nullable type variant
  (`JoinOperator.cs:163-216`), so downstream type checking sees `bool?`/`long?` and
  `EvaluateType` propagates nullability through expressions
  (`QueryExpressionBinary.cs:44,57,69,101`). OPTIONAL-induced nullness is a static
  plan fact, not a runtime surprise.
- **Aggregation:** no explicit GroupBy operator — a `ProjectionOperator` whose
  expressions contain aggregation functions renders `GROUP BY` over all
  non-aggregated output expressions (`SQLRenderer.cs:955-965`). `COUNT(entity)`
  counts the entity's **join-key surrogate** — node id, or edge source id
  (`SQLRenderer.cs:667-689`; `SelectionOperator.cs:190-199` wires the key field into
  the referenced set). `COUNT(DISTINCT relationship)` is blocked as unsupported
  (`SQLRenderer.cs:675-679`). Nested aggregates and non-COUNT DISTINCT are blocked
  (`SQLRenderer.cs:693-711`).
- **WITH pipelining:** each query part becomes a projection stage; DISTINCT is
  modeled as an implicit extra scope boundary that restricts what ORDER BY/WHERE may
  reference, while the non-DISTINCT case *widens* the projection with implicit
  fields so ORDER BY/WHERE can reference unprojected upstream fields, then trims them
  with a second projection (`LogicalPlan.cs:203-288`, design comment `:216-234`).
  This widen-then-trim dance is precisely where their bugs lived (`cc5a531`).

### Predicate placement + documented drop/mis-scope bugs

`WHERE` is a first-class `SelectionOperator` node placed by clause position:
MATCH-WHERE after the pattern's joins (`LogicalPlan.cs:395-400`), WITH-WHERE after
that stage's projection (`:418-427`), OPTIONAL-MATCH-WHERE inside the fork
(`:370-393`). Documented mis-scope/mis-binding bugs, both in the IR bookkeeping (not
in join logic): `cc5a531` (2019-08-18) — mishandled *extra field references* arising
from ORDER BY/WHERE referencing fields outside the explicit projection; `9e01425`
(2019-11-12) — properties inside `FilterExpression` never got data types bound during
schema propagation (fix: `SelectionOperator.cs:141-149`), plus a broken
boolean-operand check (`leftType != bool || leftType != bool?` — a tautology; fixed
diff in `QueryExpressionBinary.cs:52-54`) and a mis-typed `IN`-list operand.

### NULL / 3VL lowering

Their posture: **shrink the null surface at parse time, then defer wholesale to SQL
3VL.**

- `null` literal: rejected (`CypherVisitor.cs:1922-1965` fall-through). Gryphon's
  entire 2VL-null-literal boundary rule (`doc-dev-gryphon-vs-cypher.md` Ledger B) is
  a question they refuse to be asked.
- `IS NULL`/`IS NOT NULL`: supported as functions, rendered directly
  (`SQLRenderer.cs:622-625`).
- Comparisons/logic over nullable *fields*: rendered as bare SQL operators
  (`SQLRenderer.cs:44-52`) — SQL 3VL applies. `XOR` is expanded to AND/OR/NOT
  (`:42`), which under SQL 3VL propagates UNKNOWN correctly.
- **One real 3VL divergence:** when a comparison appears in *value* position (e.g.
  projected), it is wrapped `CASE WHEN <cmp> THEN 1 ELSE 0 END`
  (`SQLRenderer.cs:645-649` via `ExpressionRenderingContext.ExpectLogicalExpression`,
  `:239-264`) — UNKNOWN silently becomes `0`/false, where Cypher would return
  `null`. Nothing in their harness would catch it (ordering/nulls comparison gaps,
  Lens T). This is the exact bug shape Gryphon's TLP rung exists to catch.

### Type handling

**Reject, don't coerce — with the legality knowledge held as data, not code.** Three
exhaustive generated tables in `src/openCypherParser/AST/LookupTables/
TypeCoersionTables.cs` (1599 lines): operator × left-type × right-type → result type,
where `default(Type)` means *illegal* and `EvaluateType` throws
`TranspilerNotSupportedException` on it (`QueryExpressionBinary.cs:61-70,96-100`).
The renderer has its own SQL-side cast-legality matrix with `Invalid` →throw
(`SQLRenderer.cs:112-236,349-362`). Nullable-ness is carried orthogonally
(`TypeHelper`, unbox/re-box around table lookup). Same bet as Gryphon's
schema-as-oracle type strictness (`req-grid-traversal-lang-type-strictness`) — but
expressed as one auditable, exhaustive table rather than per-branch checks. Literal
typing had its own bug: integer literals were all `long.Parse`d until `bc9fcc6`
introduced a smallest-fitting-type ladder (`CypherVisitor.cs:533-584`).

### Row-inflation defenses

- **Automatic edge-uniqueness injection** — the standout mechanism. For any two
  relationship aliases of the *same* type appearing in one MATCH, the planner
  auto-injects pairwise `src≠src OR sink≠sink` predicates as a plan-level
  `SelectionOperator` (detection and grouping `LogicalPlan.cs:969-1017`; expansion
  into an expression tree after binding, `SelectionOperator.cs:76-140`). This is
  Cypher's relationship-isomorphism semantics ("no edge bound twice in one pattern")
  implemented as a **plan rewrite** — it kills both the duplicate-edge row-inflation
  class and the "path that ping-pongs back over the same edge" class, and it is
  differentially tested against Neo4j (`tests/SQLRenderer.Test/SQLRendererTest.cs:
  374-389`, `AdvancedPatternMatchTest`).
- `COUNT(entity)` by key surrogate (above) keeps entity counts anchored to identity
  even when the joined row set carries duplicated property columns.
- Where dedup semantics would have been genuinely hard (directionless traversal of a
  self-referencing type requires a UNION of both directions), they **block** instead
  of inflating (`LogicalPlan.cs:603-612`).

### Determinism / ordering

Their weakest surface. ORDER BY/LIMIT ride the `SelectionOperator`
(`SelectionOperator.cs:28-35,44-61`) and render as `TOP n` + `ORDER BY` inside a
derived table (`SQLRenderer.cs:867,967-971,986-990,1038-1042`) — in T-SQL an inner
`ORDER BY` only governs the `TOP` selection, not outer result order, so final
ordering is at the mercy of the outer plan. No NULLS FIRST/LAST policy, no
tiebreaks, and `TOP` without ORDER BY is expressible. Crucially the test harness
**never verifies order** (Lens T). Gryphon's captured-SQL determinism discipline
(`req-grid-traversal-exec-sql-capture-3`) and the oracle's Postgres NULLS-ordering
model have no counterpart here.

### ★ Transferable to Gryphon

1. The **born-unified plan shape**: five operators + one throwing-default renderer
   switch; every query shape flows through the same lowering; special cases exist
   only as *rejections*, never as parallel execution paths.
2. **Plan-level automatic edge-uniqueness** for repeated same-type relationships —
   a row-inflation defense Gryphon does not currently have (no
   uniqueness/isomorphism handling found in `spec-grid-gryphon-multihop-aggregation.md`
   or `spec-grid-traversal-language.md`, grep 2026-07-04).
3. **Typed nullability propagation** through OPTIONAL MATCH (left-join schema pass
   rewrites right-side fields nullable) — makes the 2VL/3VL boundary a static plan
   fact.
4. **Legality-as-data**: exhaustive operator/type tables where absence-of-entry is
   structurally a rejection — auditable by a human and queryable by Player 3.
5. The **OPTIONAL MATCH WHERE fork** (filter the optional side, then left-join back)
   as the reference predicate-placement discipline for our F-series work.

## Lens T — Testing

- **Oracle model: a real second implementation — Neo4j itself.** Every renderer test
  runs the Cypher text on a Dockerized Neo4j *and* the transpiled T-SQL on a
  Dockerized SQL Server 2017, then diffs the two result tables
  (`tests/SQLRenderer.Test/SQLRendererTest.cs:266-360`; container orchestration
  `:148-182`; documented in `README.md:46-49`). This is genuine differential testing
  with zero shared lowering — the strongest possible independence, rented rather
  than written. It was present essentially from the initial check-in.
- **Answer-vs-artifact posture: answers.** `CompareDataTables` compares values, with
  an approximate type-unification (int widths → Int64, float→double) and relative
  float tolerance 1e-4 (`tests/SQLRenderer.Test/DataTableComparisonHelper.cs:19-100`).
  No assertions on generated SQL text and no SQL snapshots at all — the plan/SQL is
  only asserted structurally in `LogicalPlannerTest`/`OpenCypherParserTest`.
- **Honesty gaps (the negative lessons):**
  1. **Order is never checked.** `compareOrder` defaults false at every call site,
     and the ordered path is literally `throw new NotImplementedException("Ordered
     comparison is not implemented")` (`DataTableComparisonHelper.cs:115-118`;
     `SQLRendererTest.cs:351-360`). The five `OrderByLimitClauseTest` queries
     (`SQLRendererTest.cs:777-843`) therefore assert **multiset equality only** — an
     ORDER-BY-shaped test suite that cannot see an ordering bug. Given their
     subquery-ORDER-BY rendering (Lens E), this is a false-green-shaped hole sitting
     exactly over their weakest lowering.
  2. **null and "" are deliberately blurred** in the comparator ("our test data
     creation tool cannot handle \"\" vs null", `DataTableComparisonHelper.cs:53-65`)
     — the oracle is structurally blind to the null/observed-empty distinction that
     Gryphon treats as a first-class spec convention.
  3. Neo4j column types are inferred by scanning result rows
     (`SQLRendererTest.cs:266-306`) — untyped-oracle fuzz at the comparison boundary.
- **No generation, no metamorphic, no mutation, no TCK.** ~15 hand-authored
  `[TestMethod]`s over one fixed MovieGraph fixture (`SQLRendererTest.cs`,
  `TestData/MovieGraph.json`). No fuzzing, no shrinking, no TLP/NoREC/PQS lineage,
  no coverage gates. Sampled testing at its most manual.
- **Regression capture:** the four late fixes each landed with new tests
  (`git show --stat 24608bf bc9fcc6 d27ce77 9e01425` — every one touches a test
  file); the early `cc5a531` only adjusted existing tests.
- **★ Transferable to Gryphon:** mostly *negative* lessons — (a) an unimplemented
  assertion in a differential comparator is a standing false-green (our
  model-oracle's loud `OracleUnmodeled`-and-skip is the correct opposite; keep it);
  (b) don't let the comparator blur distinctions the language spec makes (null vs
  ""). The one positive idea — renting a mature engine (Neo4j/Memgraph) as a *third*
  opinion for the Cypher-overlapping subset — is weighed and **rejected** below
  (OPP-6): Gryphon's deliberate divergences (Ledger B) make a stock-Cypher engine a
  noisy oracle, and the zero-shared-code model oracle already fills the independence
  role.

## Lens H — History

- **Scale:** 28 commits; real activity 2019-07-22 → 2019-11-12; two Microsoft-
  compliance commits in 2022; effectively **dormant since Nov 2019**. Knowledge held
  by ~2 people: Jerry Liang (bulk) + Huinan Liu (`git shortlog -sn`). No issue-tracker
  archaeology worth mining (frozen repo, activity moved nowhere visible).
- **Bug taxonomy** (all correctness fixes in the four-month window):

  | Class | Count | Representative | Where it lived |
  | --- | :---: | --- | --- |
  | IR schema/field-reference propagation (WHERE/ORDER-BY extra refs; filter-expr type binding) | 2 | `cc5a531`, `9e01425` | the logical plan's bookkeeping passes |
  | Label/type inference for aliases across query parts | 1 | `d27ce77` | AST finalization (`CypherVisitor.cs:649-690` area) |
  | Literal typing (int width ladder) | 1 | `bc9fcc6` | parser literals |
  | Built-in function param validation | 1 | `4a661c7` | AST function checks |
  | Test-harness/schema fixture | 1 | `24608bf` | JSONGraphSchema |

  **Zero recorded predicate-drop, join-inflation, or null-logic executor bugs.** Two
  readings, both instructive: the uniform IR lowering + Neo4j differential harness
  (both present from initial check-in `5ec98d8`) left little room for the classic
  silent-wrong-row classes; *and* the denominator is tiny — four months, one fixture,
  ~15 tests, low uptake. Per the AGE lesson in the study's literature notes, low
  surface/usage masks executor defects rather than proving robustness; treat the
  clean record as weak-positive evidence, not proof.
- **Turning-point commits:** none of the "unify the executor" species — the
  architecture never needed the medicine because it never had parallel paths. The
  only structural churn is readability (`0d95c8e`, `b39032e`).
- **Design-doc trail:** README pipeline diagram + an unusually honest roadmap of
  named non-goals (`README.md:52-66`: no plan optimization, no var-length, no
  multi-label inference, read-only). Boundaries stated as choices — the same
  courtesy Gryphon's Ledger C pays.
- **Lifecycle lesson:** a transpiler-only library with no living execution surface
  and an internal-need origin went dormant in four months despite NuGet prep
  (`f71141c`). Emitting SQL *text* — decoupled from parameterization, connection
  control, and result normalization — also caps what the tool can ever guarantee.
  Gryphon owning execution end-to-end (compile → bind → read-only alias → envelope)
  is what makes its invariants enforceable at all.
- **★ Predicted Gryphon hotspot:** if/when Gryphon grows a logical-plan IR
  (`req-grid-traversal-exec-compiler` Future), expect the bug mass to migrate into
  the IR's **propagation/bookkeeping passes** (reference pruning, type/nullability
  propagation, alias mapping across projection renames — see the alias-map
  contortions at `LogicalOperator.cs:219-256`), exactly where this peer bled. Those
  bugs failed loud (binding exceptions), which is the acceptable failure mode — plan
  for Gridkin-style coverage of the passes themselves from day one, and keep the
  model oracle as the behavior-preservation net for the migration (as it was for the
  single-hop collapse).

## Net read

The biggest thing to steal is the **shape**: a five-operator relational-algebra DAG
where *every* query shape flows through one lowering and one throwing-default
renderer, with unsupported surface rejected at parse — the "born unified" version of
the architecture Gryphon reached for single-hop by collapse and still lacks for
scan/advanced/OPTIONAL/NOT-EXISTS. Second steal: the plan-level **automatic
edge-uniqueness rewrite** (`LogicalPlan.cs:969-1017`), a structural row-inflation
defense aimed at Gryphon's single most recurrent bug class. The biggest things to
avoid: SQL-text emission with string-embedded literals (no binds — Gryphon's
ORM/parameterization invariant is a genuine architectural credit); a differential
harness whose ordering assertion is `NotImplementedException` and whose comparator
blurs null vs "" — proxies for the answer that false-green exactly where the lowering
is weakest; and the `CASE WHEN` boolean materialization that silently collapses
UNKNOWN→FALSE. Credits for Gryphon: enforced-at-the-alias read-only (theirs is
parse-time only), deterministic captured SQL, an oracle that models ordering and
null-vs-empty, and TLP probing the exact 3VL seam this peer left silently divergent.
