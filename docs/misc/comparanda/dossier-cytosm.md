# Dossier — Cytosm

Clone: `41e786f600724358836629fc3f70787834c85270` (master), read 2026-07-04. License: Apache-2.0 (`LICENSE.txt:1-3`).
Repo: https://github.com/cytosm/cytosm — clone at `undefined/cytosm` (disposable; all `file:line` anchors are at the clone SHA).
Protocol: `docs/misc/doc-gryphon-comparative-eval-protocol.md` §4.4. **Lens E primary.**
Paper: Steer, Alnaimi, Lotz, Vaquero, Boden, Rivera — *"Cytosm: Declarative Property Graph Queries Without Data Migration"*, GRADES 2017, https://event.cwi.nl/grades/2017/04-Steer.pdf (linked from `README.md:31-32`).

## Snapshot

A Java library that transpiles openCypher into **plain SQL text** to run against an
*existing, unmodified* relational database, guided by a user-supplied schema-mapping
file ("gTop" — graph topology: which tables/columns realize which node/edge types)
(`README.md:5,55-59`). Pipeline: ANTLR parser (openCypher EBNF) → AST → a
**relational SQL-tree IR** transformed by ~14 named lowering passes → rendered SQL
string (`PassAvailables.java:50-140`; `cypher2sql/README.md`, "five major steps").
It is Gryphon's *pattern-for-pattern* cousin: same bet (graph query compiled onto a
trusted relational substrate, no graph storage), same read-only surface (the grammar
carries no write clauses — `grep -ri 'CREATE\|MERGE\|DELETE' cypher2sql/src/main`
hits nothing executable), plus the one thing Gryphon deliberately lacks: an explicit
logical IR between AST and the emitted relational artifact.

It is also a **cautionary tale**: an academic prototype (GRADES'17) abandoned six
months after the paper — 41 commits, last on 2017-10-31 (`git log --oneline | wc -l`;
`git log -1 --format=%ci` = 2017-10-31), with real-user correctness issues (#21,
#23, #30) filed afterward and never answered. The IR did not save it; *how* it did
not is the most instructive read in this dossier.

Inclusion score (§2.2): relational-lowering relevance **maximal** (a literal
Cypher→SQL-text transpiler, the purest class); source availability/readability
**high** (Apache-2.0, ~10k LOC, heavily commented — including brutally honest
FIXMEs); history richness **low** — development history squashed into the initial
commit (`4d34a2d`, 2016-12-13, contains most of the code), so in-repo archaeology is
thin, but the issue tracker and in-code FIXME/TODO stream partly substitute;
semantics documentation **low** (README Known Issues is honest, `README.md:62-79`,
but there is no NULL/ordering/type semantics writeup at all). Verdict: deep on
Lens E; Lens H mined from issues + in-code fossils.

## Lens E — Execution ★ PRIMARY

### Pipeline shape / IR count

Three representations between Cypher text and SQL text — one of them a mistake they
themselves flag:

1. **Cypher strings again** (the mistake): before any parsing, `ExpandCypher`
   splits the *query string* with regex/substring surgery, enumerates concrete
   routes for anonymous nodes and variable-length edges against the gTop
   (PathFinder module), and emits a **list of new Cypher strings** — one per
   concrete route combination (`expandpaths/ExpandCypher.java:69-125`;
   `pathfinder/README.md`, "Top Level Algorithm"). Each is re-parsed from scratch.
   The README's own wishlist: "Improve `CypherConverter` and `PathFinder` to
   generate AST nodes instead of using intermediary string representations"
   (`README.md:78`).
2. **Cypher AST** — ANTLR-built, spanned, visitor-walked
   (`cypher/parser/ASTBuilder.java`, `cypher/ast/*`).
3. **SQL-tree IR** — `ScopeSelect` (one per Cypher scope) holding a list of
   `WithSelect`-wrapped `SimpleSelect`s (one per MATCH pattern part / WITH clause)
   plus a `ret` select; `UnionSelect` for multi-table label expansion
   (`lowering/sqltree/*.java`; structure documented in `cypher2sql/README.md`).
   Every MATCH becomes a SQL `WITH` subquery; variable scope/dependency analysis
   (`typeck/VarDependencies.java`) wires which subquery feeds which.

The per-query lowering is a fixed **named-pass pipeline** over the SQL tree
(`PassAvailables.java:50-140`): `VarDependencies` → `ComputeAliasVarType` →
`SelectTreeBuilder` → `NameSubqueries` → `ComputeFromItems` →
`MoveRestrictionInPattern` → `ExpandNodeVarWithGtop` → `PopulateJoins` →
`ComputeExports` → `TransformFunctions.convertCypherCountFn` →
`UnwrapPropertyAccess` → `convertPathLength` → `UnwrapAliasVar.unwrapConstants` →
`removeUnusedVariables` → `markPropertiesAsUsedWhenEncountered` →
`UnwrapAliasExpr` → render. Then the N per-route trees are merged
(`MergeExpandedCyphers.java:22-46`) into one `UNION ALL`
(`sqltree/UnionSelect.java:30`) and rendered via `toSQLString()` methods living
*on the IR node classes themselves* (`typeck/expr/ExprTree.java:28-73`).

### Bottom-turtle question 1 — is there a logical-plan IR, and what does it buy?

**Yes — a real relational IR — and it buys exactly two things while failing to buy
the third.**

What it buys:

- **Named, separately-testable lowering steps.** Each semantic concern (predicate
  placement, FROM derivation, join population, aggregate rewriting, dead-variable
  elimination) is one pass with one file and one test file asserting on **IR
  shape**: e.g. `MoveRestrictionTests.java:20-58` lowers a query halfway, then
  asserts the WHERE condition is an `Eq(PropertyAccess("id"), LongVal(0))` — a
  *plan-level* assertion Gryphon structurally cannot write today because there is
  no plan to assert on.
- **A place where cross-cutting rewrites are tractable.** The COUNT-over-UNION
  rewrite (leaf scopes → `COUNT`, enclosing scopes → `SUM`,
  `TransformFunctions.java:96-108`, `PassAvailables.java:105-108`) is a whole-tree
  transformation that would be near-unwritable as string manipulation and painful
  as AST-time special-casing.

What it fails to buy — **the IR is not an invariant choke point**:

- Passes communicate through **mutable shared state** and ordering convention.
  The pipeline orchestrator itself contains: "TODO: can this pass be moved sooner
  or later? Why would it need to be done here?? It seems that it should be run
  after Populate joins..." (`PassAvailables.java:80-81`) — pass order is
  load-bearing and *not understood by its own authors*, with nothing enforcing it.
- "Apply exactly once" is enforced by **mutating the input**:
  `MoveRestrictionInPattern` nulls the predicate after moving it ("Make sure we
  will never move the predicate again", `MoveRestrictionInPattern.java:65-67`) —
  the invariant lives in a side effect, and *which* select receives the predicate
  is whatever the walk visits first.
- Ordering/pagination handling is a **known casualty of the pass structure**:
  "TODO: Add a pass here that copy the latest ORDER BY..."
  (`PassAvailables.java:128-129`), "TODO: ORDER BY, LIMIT and SKIP needs to be
  handled here" at the union-merge site (`PassAvailables.java:164-165`), and the
  README's Known Issue: "`SKIP`, `LIMIT` and `ORDER BY` are not propagated
  appropriately on 'wide' query — that is queries involving at least one UNION in
  the generated SQL" (`README.md:67`).

**Reading for Gryphon:** an IR is necessary but not sufficient. Cytosm proves the
IR's *testability* payoff is real (their only good tests are the IR-shape ones)
and simultaneously proves that an IR whose passes coordinate via mutation and
implicit ordering just relocates the translation-fidelity bug surface into
pass-interaction space. The openCypherTranspiler dossier shows the same IR concept
with invariants enforced at plan-build time; Cytosm is the control group.

### Bottom-turtle question 2 — dispatch shape; did they collapse it?

**One uniform per-query lowering — with the special-casing exiled to a pre-compiler
macro layer.** Inside the compiler there is no shape-dispatch at all: every MATCH
pattern part becomes a `SimpleSelect`, every query walks the same 14 passes,
single-hop and multi-hop and aggregation all take the same path
(`SelectTreeBuilder.java:162-183`, `PassAvailables.java:50-140`). Where Gryphon
routes across type-scan / bare-scan / single-hop / advanced / NOT-EXISTS /
OPTIONAL-MATCH executor functions, Cytosm has *one* pipeline and pushes variation
into two structural places instead:

- **IR node type**: OPTIONAL MATCH does not get its own lowering path — `foldMatch`
  builds a `SimpleSelectWithLeftJoins` instead of a `SimpleSelectWithInnerJoins`
  (`SelectTreeBuilder.java:172-176,197-201`), and every later pass that
  materializes a join derives INNER vs LEFT *polymorphically from the node type*,
  failing closed otherwise (`PopulateJoins.java:createJoin`, throws `Unreachable`
  for an unknown select type). Optionality is data, not a code path.
- **The string-expansion macro layer**: variable-length paths, anonymous nodes and
  multi-table labels are compiled out *before* the compiler runs, into a UNION of
  concrete queries (`ExpandCypher.java:69-125`, `MergeExpandedCyphers.java:22-46`,
  `ExpandNodeVarWithGtop.java:42-79` for the label→UNION case). Uniformity inside
  is bought by combinatorial explosion outside — and by re-entering the pipeline
  through the weakest possible interface, strings ("FIXME: This code is plain
  wrong" on the regex-based validity check that gates which expansions survive,
  `ExpandCypher.java:133`).

History note: the join machinery is itself "a port of the old JoinPostProcessor by
James Brook. Most of the logic has been preserved" (`PopulateJoins.java:31-33`) — a
pre-open-sourcing rewrite of the hardest pass, but the squashed history
(`4d34a2d`, initial commit carries the codebase) erased the pain that motivated it.

### Bottom-turtle question 3 — where are invariants enforced?

**Nowhere structural — and this is the dossier's sharpest negative lesson.**

- **Parameterization: absent.** Rendering is string concatenation distributed
  across ~30 `toSQLString()` methods on IR nodes; a string literal renders as
  `"'" + literal + "'"` with *no escaping whatsoever*
  (`rendering/RenderingHelper.java:39-42`) — a Cypher literal containing `'` is a
  SQL injection by construction. There are no bind parameters anywhere in the
  repo. Because rendering has no choke point, there is no single place where
  escaping *could* be enforced; the fix would touch every node class.
- **Read-only: by grammar accident, not by contract.** No write clauses parse, but
  nothing equivalent to Gryphon's `search_readonly` alias exists because Cytosm
  never executes — the emitted string's blast radius is the caller's problem.
- **Emission validity: checked ad hoc, per node, at render time.**
  `FromItem.toSQLString` throws "No table associated with this FROM !!"
  (`sqltree/from/FromItem.java:71`) — an invariant ("every FROM is bound") asserted
  at the *last possible moment*, in one node class, as a `RuntimeException`. Issue
  #30 is that exception escaping to a user for the everyday query
  `MATCH (a:guild)-[r:registered_in]->(k:kingdom)` — a *relationship variable*
  binds a var to the join table and no pass ever taught FROM-binding about it.

The one genuinely good invariant pattern: a dedicated fail-closed exception family
for the lowering — `BugFound`, `Unreachable`, `Unimplemented`, `TypeError`
(`lowering/exceptions/*.java`) — thrown by passes when the gTop lookup is ambiguous
("More than one source!! This is a bug.", `PopulateJoins.java:145`), missing ("No
edge found between...", `PopulateJoins.java:147-151`), or a walk reaches an
unmodeled shape. Where it is used, silent-wrong-SQL becomes a loud refusal — the
same posture as Gryphon's `OracleUnmodeled` and rejection scenarios. The failure is
coverage: it is a *convention* each pass opts into, not a property of the
architecture, so the gaps (next section) are exactly where the silent bugs live.

### Bottom-turtle question 4 — where does fail-closed live; can a path accept input it silently ignores?

**Fail-open at both ends of the pipeline, fail-closed only in the middle.** Four
anchored instances of the envelope-WHERE bug shape (input accepted, silently
ignored or mangled):

1. **Edge direction is parsed, schema-declared, and ignored.** The gTop abstraction
   level declares `directed: true/false` per edge type
   (`common/.../AbstractionEdge.java:27-29`), the Cypher arrow parses — and the
   join builder uses neither: "FIXME: This code totally ignore directions..."
   (`PopulateJoins.java:158`), README Known Issue #1 (`README.md:63`). A directed
   query silently returns undirected matches — extra rows, no error. Root cause is
   *structural and below the executor*: the implementation-level gTop format
   carries no direction on traversal hops — "always assume that the edge is
   undirected. The implementation also has no information [about direction]"
   (`common/.../GTopInterface.java:221`). **The schema seam dropped the semantics,
   so no lowering pass *could* be correct.** (Compare Gryphon: `Edge` spine rows
   carry direction as first-class columns — this class is inexpressible.)
2. **Schema field accepted and ignored:** gTop's `abstractionLevelName` (the
   graph-side property name → column mapping) is documented, parsed, and unused —
   issue #22 ("Currently, cypher2sql ignore the abstractionLevelName ... and use
   the property name provided in the Cypher"). Queries written against the
   *graph* vocabulary silently read the wrong (or no) column.
3. **Renderer emits SQL with holes.** For a gTop edge with no join table, the
   output contains `JOIN  AS __src5 ON ((__src2.guild = __src5.))` — empty table
   name, empty column, dangling dot — handed to the caller as a "successful"
   translation (issue #23, reporter's verbatim output). Nothing validates the
   rendered artifact; the emit path cannot refuse.
4. **Entry point swallows its own errors.** `SelectTreeBuilder.createQueryTree`
   catches its exception, `printStackTrace()`s, and **returns `null`**
   (`SelectTreeBuilder.java:38-45`); the expansion layer `println`s when a path
   expands to zero routes and carries on (`ExpandCypher.java:96-98`).

### Join / traversal lowering specifics

- **k-hop:** each hop is an inner join through the gTop-declared join table; a
  chain `(a)-[:X]-(b)` becomes `FROM a JOIN edge_table JOIN b` with equality
  conditions from the gTop `TraversalHop` (`PopulateJoins.java:160-240`). Only the
  *first* path/hop of an edge implementation is ever consulted —
  `edge.getPaths().get(0).getTraversalHops().get(0)` (`PopulateJoins.java:135,160`,
  "FIXME: Manage arbitrary hops", `:156`) — multi-hop edge implementations are
  silently truncated to hop one.
- **Variable-length (`*1..k`):** macro-expanded to fixed-length disjuncts at the
  string layer, one query per length per route, `UNION ALL`-merged
  (`pathfinder/README.md` "route dilatation"; `UnionSelect.java:30`). No recursive
  CTE anywhere. Unbounded `*` has no lowering. Note for Gryphon's E1 seam: with
  `UNION ALL` and no path-uniqueness handling (no relationship-isomorphism code
  exists — verified by `grep -rni 'unique|isomorph'` finding only variable-naming
  plumbing), Cypher's no-repeated-edge path semantics are silently violated on any
  cyclic data.
- **OPTIONAL MATCH:** LEFT-join-ness carried as IR node type (see Q2) — the
  cleanest idea in the codebase.
- **Aggregation:** `count(x)` is rewritten tree-wide — leaf `ScopeSelect`s render
  `COUNT(id_col)`, enclosing scopes `SUM` the branch counts
  (`TransformFunctions.java:96-108`) because the UNION-of-routes shape makes a
  naive COUNT double-count per branch; the arg is force-rewritten to the gTop id
  column with "FIXME: We should make sure that we always have *exactly* one node
  returned here" (`TransformFunctions.java:141`). README: "Proper handling of the
  COUNT function (we only support limited use cases)" (`README.md:66`). **This is
  Gryphon's multi-hop COUNT-inflation scar, met from the other side**: they
  correctly identified that aggregation-over-unioned-disjuncts must be computed
  per-branch-then-combined, and still couldn't finish it.

### Predicate placement

Inline pattern predicates (`{id: 0}`) ride the `NodeVar` until
`MoveRestrictionInPattern` ANDs them into a `whereCondition` "as SQL simply ignore
those restriction" (`MoveRestrictionInPattern.java:53-77`) — their own comment
acknowledging that un-moved predicates would be *silently dropped*; the pass is the
only thing standing between the pattern and the drop, with pass-order uncertainty
(`PassAvailables.java:80-81`) directly underneath it. Clause-level WHERE on a
multi-pattern MATCH is placed in its own `SimpleSelect` scoped by variable
reachability (`SelectTreeBuilder.java:186-208`). No *documented* predicate-drop bug
in the tracker — but with no execution layer and no answer-checking tests, a
dropped predicate had no way to be observed (see Lens T).

### NULL / 3VL

**Total punt, unexamined.** Cypher `=`/`<>`/`IN` render as SQL `=`/`<>`/`IN`
(`ExprTree.java:43-47`), `IS [NOT] NULL` as postfix (`ExprTree.java:72-73`);
there is no null-literal handling, no 3VL reasoning, no comment anywhere in the
repo acknowledging that openCypher null semantics and SQL null semantics differ
(e.g. Cypher `null IN [...]`, `null = null` in different contexts). Whatever the
backend does is what you get. Bonus portability bugs in the same table: `XOR`
renders as infix `XOR` (`ExprTree.java:48`) — not PostgreSQL SQL — and `NOT(x)` as
a function call (`ExprTree.java:70`). Contrast: Gryphon's discriminated
2VL-literal/3VL-field boundary is *specified and differentially tested*
(`doc-dev-gryphon-vs-cypher.md` Ledger B).

### Type handling

A vestigial type lattice exists (`typeck/types/*.java`) and `ComputeAliasVarType`
runs early, but the README concedes: "Improve the type-checker to compute verify
the correctness of any expressions before rendering. The current version is
incomplete" (`README.md:68-69`; commit `424473f` exists solely to add that
warning). Constant folding had cast bugs fixed in `af9d477` ("Fix a few cast bugs").
Nothing rejects a mistyped literal; it renders and the RDBMS does whatever it does.
(Gryphon credit: `req-grid-traversal-lang-type-strictness`, schema-as-oracle
rejection.)

### Row-inflation defenses

Two known-and-lost fronts: (a) the COUNT-over-UNION rewrite above — built, admitted
incomplete (`README.md:66`); (b) direction-ignoring joins (Q4.1) inflate every
directed traversal with reverse matches. Plus the `UNION ALL` merge with no
path-uniqueness semantics. No DISTINCT discipline; `WITH DISTINCT` maps to
`isDistinct` on the select (`SelectTreeBuilder.java:137`) and nothing else defends.

### Determinism / ordering

`ORDER BY`/`SKIP`/`LIMIT` lower per-select (`SelectTreeBuilder.java:112-153`,
LIMIT/SKIP must const-fold to integers — a small fail-closed win), but ordering is
**dropped on any query wide enough to involve a UNION** (`README.md:67`,
`PassAvailables.java:128-129,164-165`) — i.e. on exactly the queries the expansion
architecture makes common. No tiebreak or stable-order discipline exists.

### ★ Transferable to Gryphon

1. **Optionality/variation as IR-node *type*, dispatched polymorphically with a
   fail-closed default** (`SelectTreeBuilder.java:172-176` +
   `PopulateJoins.createJoin`'s `Unreachable`) — the structural pattern for
   collapsing Gryphon's OPTIONAL MATCH / NOT EXISTS forks into the chain path.
2. **Pass-level IR-shape tests** (`MoveRestrictionTests.java:20-58`) — the
   testability dividend an IR pays; the concrete new rung Gryphon gains the day a
   logical plan exists.
3. **The `BugFound`/`Unreachable`/`Unimplemented` exception family as a named,
   grep-able fail-closed vocabulary** for a lowering — Gryphon has the posture but
   not the uniform vocabulary across executor helpers.
4. **Negative transfer (avoid):** never re-enter the pipeline through strings; never
   let pass order be an unstated convention; never distribute rendering/emission
   across node classes without a validating choke point; never let the schema
   layer drop semantics (direction) the lowering needs — audit TAP registry
   surfaces for lossy seams whenever a new lowering consumes them.

## Lens T — Testing

- **Oracle model: none.** There is no execution layer at all — no JDBC, no
  driver, no test database (verified: `grep -ril 'jdbc\|DriverManager'` over the
  repo returns nothing). Correctness of the *answer* is untestable in-repo by
  construction; benchmarking lived in a sibling repo (`README.md`, "Benchmarks").
- **End-to-end tests assert nothing.** Self-described: "Rendering tests don't
  assert anything. Instead they pass if and only if the code doesn't rise any
  exception" (`RenderingTests.java:8-9`). The e2e suite is a crash detector —
  every silent-wrong-SQL bug in this dossier sails through it green.
- **Pass-level tests are the one real rung.** IR-shape assertions per pass:
  `ComputeFromItemsTests` (45 asserts), `VarDependenciesTest` (46),
  `MoveRestrictionTests` (30), `PopulateJoinsTests` (20), parser
  `FullStructureTests` (51) (assert counts via `grep -c assert`). This is genuine
  plan-level testability — but with no answer-level rung above it, a pass can be
  faithfully wrong (direction-ignoring joins pass their tests; the tests encode
  the same misunderstanding).
- **Differential/metamorphic/fuzzing/TCK/mutation: none of each.** No TCK usage
  despite parsing openCypher's grammar; no generator; the closest artifact is
  `StressTests.java` — two hand-written WITH-chain queries, zero assertions
  (`StressTests.java:26-52`).
- **Answer-vs-artifact posture:** the purest artifact-only regime in the study —
  and its false-green is total: issue #23's hole-ridden SQL and the
  direction-ignoring joins were *invisible* to a suite that never runs the SQL.
  Cytosm is the limiting case of the SQL-scrape lesson
  (`doc-gryphon-testing-philosophy.md` §4): checking that an artifact *exists and
  didn't crash* verifies nothing about meaning.
- **Regression capture:** partial at pass level only — e.g. fix `4d220a3` ("Keep
  AliasVar when used only in RETURNs", PR #11) lands with a locking test in
  `UnwrapAliasVarTests.java`; the crash issues (#21, #30) died unfixed, untested.
- **★ Transferable to Gryphon:** nothing to import — this lens is a pure credit
  mirror. Gryphon's ladder (model oracle, fuzzer, TLP, snapshots, coverage gates)
  is precisely the set of mechanisms whose absence let Cytosm ship every bug in
  Lens E. The one forward note: when a Gryphon IR lands, add the pass-level
  IR-shape rung *underneath* the existing answer-level rungs, not instead of them
  — Cytosm shows pass-level-only inverts into false confidence.

## Lens H — History

- **Scale:** 41 commits, 2016-12-13 → 2017-10-31 (`git log`); contributors:
  Nemikolh 17, alzindiq 11, Marco Aurelio Lotz 7, + 4 minor (`git shortlog -sn`).
  Real development history pre-dates the repo and was squashed into `4d34a2d`
  ("Initial commit", 2016-12-13, carrying most of the codebase) — the
  holes-and-climbs record Lens H wants was destroyed at open-sourcing. The
  fossil that survives: "port of the old JoinPostProcessor by James Brook"
  (`PopulateJoins.java:31-33`, also `ExpandNodeVarWithGtop.java:23-25`) — the
  join/lowering core was rewritten at least once before publication, and the
  post-rewrite code *still* carries nine FIXMEs.

- **Bug taxonomy** (fixed + known-open, class → count → representative anchor):

  | Class | Count | Representative | Gryphon analog |
  | --- | :---: | --- | --- |
  | Silent semantic widening (direction ignored) | 1 systemic | `PopulateJoins.java:158`, `README.md:63`, `GTopInterface.java:221` | row inflation / wrong-edge-type matches (multi-hop far-node scar) |
  | Silent wrong/invalid SQL from schema-mapping gaps | 2 | issue #23 (no-join-table edge → SQL with holes); issue #22 (`abstractionLevelName` ignored) | envelope-WHERE shape: input accepted, ignored |
  | Crash on unmodeled shape | 2 | issue #30 (relationship variable → `FromItem.java:71` RuntimeException); issue #21 | loud, therefore the *good* outcome |
  | Pass drops a still-needed element | 1 | `4d220a3` — `removeUnusedVariables` deleted vars used only in RETURN | predicate/projection drop class |
  | Aggregation over union incomplete | 1 systemic | `README.md:66`, `TransformFunctions.java:141` | COUNT inflation |
  | Ordering/pagination dropped on wide queries | 1 systemic | `README.md:67`, `PassAvailables.java:164-165` | ordering/determinism class |
  | Type/cast errors | 2 | `af9d477` ("Fix a few cast bugs"); `README.md:68` | type-coercion class (Gryphon rejects) |
  | Parser gaps | 2 | issue #16 (`IN ['foo','bar']` parse error) → fixed `d79cdd1`/PR #17 | grammar-surface class |
  | Rendering/alias bugs | 2 | `5f98af0` ("Fix the rendering issues for AliasVars"), PR #3 | serialization class |

- **Turning-point commits:** the record is mostly pre-repo, but `4d220a3` is a
  perfect miniature — a *cleanup pass* (dead-variable elimination) silently
  deleting live variables because "used" was computed against the wrong scope set;
  the fix threads a `defaultCountValue` flag through the use-counting visitor.
  Lesson: every optimization pass over a mutable IR is a fresh chance to drop
  something the query still needs, and only an answer-level check catches it
  authoring-independently.

- **Design-doc trail:** the GRADES'17 paper plus unusually candid in-repo docs —
  `cypher2sql/README.md` (five-pass design), `pathfinder/README.md` (expansion
  algorithm + Neo4j plan-cost comparison), and a README Known Issues section that
  honestly lists correctness defects most projects would hide
  (`README.md:62-79`). The FIXME/TODO stream *is* their open reasoning.

- **Lifecycle lesson:** paper-driven prototype, abandoned at paper+6mo; the
  post-abandonment issues (#21 2018, #23 2019, #30 2021 — real users trying real
  schemas) all hit the same wall: the lowering was ~80% built with the last 20%
  (direction, FK-edges, relationship vars) documented-but-unfixed, and with no
  execution-level validation there was no pressure gradient pushing those last
  20% to completion. A transpiler that never runs its own output has no feedback
  loop; "Known Issues" stayed known until the project died. RedisGraph died of
  architecture cost; Cytosm died of **unclosed correctness debt made painless by
  artifact-only testing**.

- **★ Predicted Gryphon hotspots** (from where Cytosm bled): (1) the future
  var-length/E1 lowering — aggregation, ordering, and path-uniqueness over
  unioned/expanded disjuncts is where Cytosm left three systemic Known Issues;
  pre-register gridkin scenarios for COUNT-over-var-length, ORDER-BY+LIMIT-over-
  var-length, and cyclic-fixture edge-reuse *before* rung-4 lowering lands.
  (2) Any registry/schema seam a lowering consumes: audit that it carries *all*
  the semantics the query language can express (Cytosm's gTop dropped direction
  and the lowering could never win it back). (3) Cleanup/normalization passes, if
  an IR is introduced — the `4d220a3` class.

## Net read

Biggest thing to steal: the **shape** of the lowering — one uniform pipeline where
per-query variation (optionality) is carried as typed IR data dispatched
polymorphically with a fail-closed `Unreachable` default, plus pass-level IR-shape
tests — this is the concrete sketch of what Gryphon's anticipated logical IR
(`req-grid-traversal-exec-compiler` Future) should look like, and it directly names
Gryphon's next dispatch-collapse candidates (OPTIONAL MATCH and NOT EXISTS folded
into the chain path as node attributes, not executor forks). Biggest thing to
avoid: Cytosm is the proof that an IR without structural invariant enforcement —
mutable pass state, convention-ordered passes, rendering distributed across node
classes with no validating choke point, strings as a mid-pipeline representation —
merely relocates the silent-wrong-answer surface into pass-interaction space; and
that artifact-only testing (their e2e suite literally asserts nothing,
`RenderingTests.java:8-9`) removes the feedback loop that would ever surface it.
Credits: Gryphon's bind-parameterization invariant (Cytosm string-concatenates
literals unescaped, `RenderingHelper.java:39-42`), typed-lane rejection (their
type-checker is admittedly incomplete), first-class edge direction on the spine
(their schema seam dropped it and doomed the join lowering), and the model-oracle/
fuzzer ladder (every silent bug in this dossier would have been loud on day one
under a Gridkin-style differential) — four whole Cytosm bug classes are
inexpressible or already-caught in Gryphon's architecture.
