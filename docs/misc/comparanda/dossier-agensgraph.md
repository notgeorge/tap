# Dossier — AgensGraph (clone `e12933a7c836bb8db95ed94b8a32fbc068a464a3`, 2026-07-04, license Apache-2.0 over the PostgreSQL license)

> Produced under `doc-gryphon-comparative-eval-protocol.md` (§4.4 template). Repo:
> `github.com/bitnine-oss/agensgraph` (README now badges the SKAI-maintained v2.16.0
> line, PG17 base — `README.md:1-10`, license `README.md:136-137`). Blobless clone,
> full commit history. All `file:line` anchors are at the clone SHA above. IP posture:
> ideas mined, no code copied.

## Snapshot

AgensGraph is a **fork of the PostgreSQL kernel** (not an extension) that adds Cypher
as a first-class query language beside SQL. Its architectural bet is the deepest form
of the relational-lowering thesis in the study: Cypher is translated **at parse-analysis
time** into PostgreSQL's own `Query` trees — one `Query` per Cypher clause, each clause
wrapping its predecessor as a FROM-subquery (`src/backend/parser/analyze.c:3650`
`transformCypherStmt`, `:3732` `transformCypherClause`;
`src/backend/parser/parse_graph.c:6931` `transformClauseImpl` →
`addRangeTableEntryForSubquery`). From there the **stock Postgres planner and executor
do everything**: join ordering, subquery pull-up, predicate pushdown, EXPLAIN, ACLs,
parameterization. Vertices/edges live in per-label inheritance tables with `jsonb`
properties; graph values are composite types (`vertex`, `edge`, `graphid`).

History: first Cypher-transform commit 2016-06-27 (`ad4f315dc9`); ~10 years of
continuous development; 348 commits on the core graph lowering files, of which ~120
are fixes (git log over `parse_graph.c`, `parse_cypher_expr.c`, `execGraphVle.c`,
`execCypher*.c`, `nodeModifyGraph.c`, `nodeShortestpath.c`, `nodeDijkstra.c`,
`graph.c`, `graphmeta.c`). Top knowledge-holders: Junseok Yang (104 commits on those
files), Muhammad Taha Naveed (48), Alex Kwak (33) (`git shortlog -sn` on those paths).

**Inclusion score (§2.2): deep — the highest relational-lowering relevance in the
roster.** It is the "Cypher compiled into the relational planner" data point: pure
lowering into a mature relational algebra layer, huge history richness, moderate
semantics documentation (design intent lives in code comments and commit messages,
not standalone docs).

---

## Lens E — Execution ★PRIMARY

### E.1 Is there a logical-plan IR between AST and physical execution?

**They did not build one — they borrowed the best one in existence.** There is no
AgensGraph-specific logical-plan layer. The Cypher AST (`CypherClause` chain) is
lowered *during parse analysis* directly into PostgreSQL's `Query` tree — which *is*
a battle-tested logical-relational IR with a full optimizer behind it. Each clause
transform (`parse_graph.c:861` `transformCypherMatchClause`, `:531`
`transformCypherProjection`, etc.) emits a `CMD_SELECT` (or `CMD_GRAPHWRITE`) `Query`;
the previous clause becomes a subquery RTE (`parse_graph.c:6931-6985`), and the
projection un-nests where scoping demands it (commit `dc817b3b7b`, 2026-06-17). The
planner then flattens, reorders joins, picks scan methods, and enforces permissions
(`rteperminfos`) uniformly.

What the borrowed IR buys them, concretely:

- **Join optimization for free.** MATCH connectivity is emitted as plain equality
  quals over a flat FROM list — `vertex.id = edge.start` — not as fixed join syntax
  (`parse_graph.c:3928` `addQualNodeIn`), so hash/merge/nestloop choice and join
  *order* belong to the Postgres planner, not the Cypher layer.
- **A single invariant choke point.** Parameterization, ACLs, collation, snapshot
  rules, EXPLAIN — asserted once, in the host pipeline, for every Cypher query,
  because every Cypher query *is* a `Query`.
- **Plan-level testability.** Their newest test corpus asserts on EXPLAIN output
  (85 EXPLAINs in `src/test/regress/sql/cypher_graphmeta_prune.sql`, 1274 lines).

The honest cost: **forking the kernel means a permanent upstream-merge tax.** The
expression evaluator had to be wholesale rewritten when upstream changed expression
evaluation (`6e80a5a3e0`, 2018-03-06: "PostgreSQL totally changed the way it
initializes and evaluates expressions… Cypher expression evaluation has been
rewritten"), and the log is punctuated by giant merge commits ("Merge with Upstream
PG", "Merge skai/main into PG17 checkpoint" `108cc44853`). Gryphon's ORM-level
lowering pays a far smaller version of this tax.

**Read for Gryphon:** the thin-transpiler-without-own-IR design is *validated* here,
with one condition — it works because they lower **early and completely** into a
mature relational layer that then owns all semantics. AgensGraph's bugs (E.7, Lens H)
cluster precisely where execution *leaves* that layer. Gryphon's analog of "the
borrowed IR" is the ORM QuerySet; the analog of "leaving the layer" is every place
the executor runs multiple querysets glued by Python (envelope merging, staged
scans). The lesson is not "build an IR"; it is "shrink the glue."

### E.2 How is dispatch structured — one lowering or many special-case paths?

**Hybrid: a uniform clause→Query lowering core, plus a small ring of special-case
physical paths — and the bug history lives almost entirely on the ring.**

Uniform core: every read clause goes through the same
`transformCypherClause` switch (`analyze.c:3732-3777`) into the same Query/planner
pipeline. There is exactly one MATCH lowering (`transformComponents`,
`parse_graph.c:2548`) regardless of pattern shape, anchor, or hop count.

The special-case ring:

| Path | Mechanism | Anchor |
| --- | --- | --- |
| Variable-length edges (VLE) | custom executor node (today `GraphVLE`, a DFS over index scans) | `src/backend/executor/execGraphVle.c:1-60`, `:402` `ExecGraphVLEDFS` |
| shortestpath / dijkstra | dedicated parse + plan nodes | `src/backend/parser/parse_shortestpath.c` (1516 lines), `nodeShortestpath.c`, `nodeDijkstra.c` |
| graph writes | `CMD_GRAPHWRITE` + `ModifyGraph` node with eager/command-id machinery | `nodeModifyGraph.c`, commits `32acddf6f2`, `734266048c` |
| planner scan-pruning | hand-rolled arc-consistency pre-pass | `src/backend/optimizer/util/inherit.c:77-92` |

**Did their history have a "we unified/rewrote the executor" refactor? Twice, on the
same path.** VLE was first *moved* from a transform-level lowering into a custom
executor node (`6c5afdae87`, 2017-02-08 "Move VLE implementation from transform level
to execution level"), then that node (`NestLoopVLE`) accumulated a five-year
correctness tail — "VLE produeces invalid results" (`87c1b78148`, 2017-10),
"VLE returns incorrect result with sequential scan" (`b168d96d5d`, 2018-05),
"ExecNestLoopVLE crashes on match" / "hangs on some match queries" (`eb1a3964d4`,
`2c20d8d1ab`, 2019-12), LIMIT crashes (`47f55467bb`, `70109a67e4`), rescan bugs
(`017fb393f3`) — until it was **rewritten again** in 2022 (`daf2dd4395` /
cherry-pick `24e443c593`, "Refactor VLE Logic (#598)": *"NestLoopVLEJoin was strongly
combined with other executors. This makes it difficult to identify PG's own code and
AgensGraph code"*), deleting `nodeNestloopVle.c`. Fixes continued into 2025
("Columns not visible when using a VLE" `a706a3966f`, 2025-04-30). One special-case
execution path ⇒ two rewrites and a decade of correctness fixes.

### E.3 Where are invariants enforced?

At **one structural choke point — the host pipeline — for everything that stays on
the uniform path**: bind parameters, ACLs (`rteperminfos` set per clause-Query,
`parse_graph.c:970-975`), collations (`assign_query_collations` in every transform),
MVCC. The clause transforms only *construct*; Postgres's analyzer/planner/executor
*enforce*.

Where a path leaves the uniform lowering, invariants had to be **re-earned by hand**,
visibly and painfully: ACL logic had to be re-added to ModifyGraph (`3d2ee30ccc`
"Fix: ACL logic to the ModifyGraph"); intra-statement write-visibility needed a
bespoke command-id-window protocol that was still being fixed in the final week of
this history (`734266048c` 2026-06-27, `32acddf6f2` 2026-06-28 — the invisible-tuple
class first appears 2018-07-11, `4b61203dce`). This is the protocol's
"re-asserted per path" anti-pattern, empirically costed: ~15 write-visibility fixes
over 8 years on a path the uniform pipeline could not protect.

### E.4 Where does fail-closed live? Can a path accept input it silently ignores?

The transform layer generally **fails loud**: unknown constructs `ereport` at
analysis (`analyze.c:3683-3685` "Cypher query must end with RETURN…"; `elog` on
unrecognized clause tags `analyze.c:3771`), and unknown columns/types are caught by
the host analyzer because everything must typecheck as a real `Query`
(`transformClauseImpl` even hard-fails on an unexpected command type,
`parse_graph.c:6968-6972`).

The **silent-wrong surface is hand-rolled optimizations and the type boundary**, not
clause dispatch:

- A "remove unnecessary joins" optimization (`3ced8823`) silently returned wrong
  results for self-join/unnamed-path patterns and was rolled back (`c05c235c03`,
  2022-12-15 "Includes necessary JOINs of vertices (#599)"). This is AgensGraph's
  envelope-WHERE: an optimization that dropped relational work it believed
  unnecessary.
- `id(u) IN [1.1, …]` **silently never matched** — LHS rewritten to `to_jsonb()` and
  compared as a jsonb string against jsonb numbers (`0f0cbf521d`, 2026-07-02 commit
  message). A textbook silent-wrong-answer at the coercion boundary.
- The 2026 graphmeta scan-pruning pre-pass is the new hand-rolled optimization, and
  notably it ships with an explicit *written soundness argument* — "Narrowing-only +
  a complete ag_graphmeta … make this sound: a removed label has no connectivity
  support, so it cannot contribute a matched row" (`optimizer/util/inherit.c:87-91`) —
  plus explicit fail-closed sentinels (a `*0..` VLE keeps the pruning barrier via a
  `-1` sentinel, `parse_graph.c:2534-2541`), defensive bounds checks (`ab775cb88b`),
  and a dedicated 1274-line regression file. They learned the `c05c235c03` lesson:
  a skip-work optimization now carries its proof and its own corpus. Even so, its
  soundness rests on a catalog-completeness invariant that has already needed three
  maintenance-edge fixes (`d476935807` COPY + BEFORE-INSERT triggers, `8a0c9f3cfc`
  relcache invalidation on DROP LABEL, `36f4fd367f` snapshot rules under
  RR/SERIALIZABLE).

### E.5 The join/traversal lowering

- **Fixed-length patterns**: each label a table (inheritance children under
  `ag_vertex`/`ag_edge`); each pattern element becomes an RTE; connectivity is
  equality quals `vertex.id = edge.start_id|end_id` accumulated over the chain walk
  (`transformComponents` `parse_graph.c:2548-2800`, `addQualNodeIn` `:3928`,
  `addQualRelPath`). Undirected/typed-edge unions are generated as subselects
  (`genEdgeUnion`, decl `:192`). Join order is entirely the planner's.
- **k-hop / variable-length (`*n..m`)**: lowered to a generated subselect
  (`genVLESubselect` `parse_graph.c:3420`) whose scan is the custom `GraphVLE`
  executor node — a depth-first expansion preferring a btree index scan on
  start/end with a filtered heap-scan fallback (`execGraphVle.c:57-60`), emitting
  `ids`/`edges`/`vertices` array columns consumed by path projection. Since 2026-06
  it expands via index scan rather than full table scan (`6daa8fc824`).
- **OPTIONAL MATCH**: *the same MATCH transform, run recursively, wrapped in a
  LEFT LATERAL join with qual TRUE* — `transformMatchOptional`
  (`parse_graph.c:1985-2049`) temporarily sets `detail->optional = false`, re-invokes
  the standard transform via `transformClauseImpl` with `p_lateral_active = true`,
  then `incrementalJoinRTEs(JOIN_LEFT, …)`. The pattern's WHERE stays **inside** the
  optional side ("since WHERE clause is part of MATCH, transform OPTIONAL MATCH with
  its WHERE clause", `parse_graph.c:877-879`) — the correct Cypher placement, gotten
  structurally rather than per-path. Optionality is a *combinator over the one
  lowering*, not a second lowering.
- **Aggregation**: Cypher's implicit grouping is generated at transform time —
  non-aggregate RETURN items become the GROUP BY (`generateGroupClause`,
  `parse_clause.c:3931`, called at `parse_graph.c:622`), then
  `parseCheckAggregates` (host machinery) validates. Aggregates then ride the stock
  Agg node.

### E.6 Predicate placement + documented drop/mis-scope bugs

`WHERE` is transformed inside the owning MATCH's Query (`transformCypherWhere` at
`parse_graph.c:916-919`) and property-map constraints `{k: v}` become quals via
`transform_prop_constr` (`:4237-4282`), with a GIN-containment rewrite when a GIN
index exists (`ginAvail`/`hasGinOnProp`, decls `:240-242`). After that, *placement*
is the planner's problem — the Cypher layer never re-decides where a predicate runs.
Documented mis-scope/drop incidents are concentrated in the composition machinery,
not the predicate lowering: `dc817b3b7b` (ORDER BY couldn't see non-returned vars
because the projection was wrapped in a subquery — fixed by un-nesting and resolving
sort items SQL-style with resjunk entries), `c40f1100b0` (variable reuse across
clauses), `e5f2ae16f8` (cannot refer to vertex in the same clause), `7c2e03fe3b`
(CALL subquery name collision with outer binding), and the join-drop rollback
`c05c235c03` (E.4).

### E.7 NULL / 3VL in the lowering

Design rule, stated at the top of the expression transformer: all Cypher values are
`jsonb`, except comparisons return SQL `bool` — and **"We use SQL NULL instead of
`'null'::jsonb`. This makes it easy to implement 'operations on NULL values return
NULL'"** (`src/backend/parser/parse_cypher_expr.c:11-19`). I.e., they deliberately
map Cypher null onto SQL NULL so the host's 3VL does the work. They also normalize
nulls out of storage by default (`allow_null_properties` GUC, default false,
`parse_cypher_expr.c:112`; SET-to-null removes the property, `b01ee96456`), so
missing-property access → SQL NULL uniformly.

**And yet the JSON-null/SQL-NULL boundary bled for the entire life of the project:**
"Handle null values properly" (`48a640b9b4`, 2017-08-31) → "Return null value on
first optional match" (`946ef7ebb4`, 2018-04) → and in the final three days of this
history: list-comprehension iteration variables bound JSON `null` elements as jsonb
`'null'` instead of SQL NULL, so `x IS NULL` was false and `all([null,…] WHERE x IS
NOT NULL)` returned true (`acc77d6cbe`, 2026-07-03 — the fix had to *decouple* the
"iteration exhausted" signal from element null-ness, which shared one `resnull`
flag); and ALL/ANY/NONE/SINGLE were lowered as a *count of TRUE results* — "which
cannot distinguish FALSE from NULL and so never returned NULL" — requiring a full
Kleene-3VL re-lowering with dedicated short-circuiting C reducers (`e12933a7c8`,
2026-07-03, HEAD). **A decade in, with the design rule written at the top of the
file, 3VL retrofits were still landing at HEAD.** The class hides wherever a new
*value context* (list element, predicate reducer, comprehension binding) is added
without re-deriving the null story for that context.

### E.8 Type handling: coerce, reject, or defer?

**Coerce-and-defer, and it is their largest single bug class.** Everything funnels
through `jsonb` (`coerce_to_jsonb`, `coerce_all_to_jsonb`,
`parse_cypher_expr.c:99-102`); comparisons use jsonb operators whose cross-type
behavior is jsonb's total order — so a wrong-typed literal *silently never matches*
rather than erroring (`0f0cbf521d`: jsonb string vs jsonb number), and equality
via jsonb containment diverged from identity `=` once a collected element was
mutated (same commit). The taxonomy (Lens H) counts ~19 fixes at this boundary,
from `e239da247d` (2017, TRUE/FALSE were jsonb not bool) through `bb755a7200`
(`min(jsonb)` "is not unique"), `94095e1d27` (coerce return values to jsonb),
`3e6e7f30d2` (coerce jsonb in list predicates), to `ad533eaa18` (2026-07-03,
unknown-typed `collect()` argument). This is the AGE lesson (arXiv:2408.07525's
agtype crash cluster) reproduced in a sibling codebase: **a universal value type
straddling the SQL type system is a permanent bug magnet at cast/null boundaries.**
Gryphon's schema-as-oracle rejection (`req-grid-traversal-lang-type-strictness`) is
the opposite pole — credit, see Net read.

### E.9 Row-inflation defenses

Two, both *structural* (emitted into the one Query at lowering time, enforced by the
relational engine — never post-hoc Python/dedup):

1. **Edge-uniqueness quals** (Cypher relationship-isomorphism): for every pair of
   fixed edges in a MATCH component, a pairwise `graphid <> graphid` qual; between a
   fixed edge and a VLE, `array_position(vle.ids, eid) IS NULL`; between two VLEs,
   `NOT arrayoverlap(ids1, ids2)` (`addQualUniqueEdges`,
   `parse_graph.c:4083-4155`; collected per component at `:2712-2726`). Duplicate-edge
   row inflation is *inexpressible* — the rows never exist.
2. **Implicit grouping** at projection (`generateGroupClause`, E.5) pins aggregate
   cardinality to the projected keys.

Where they *did* inflate/deflate wrongly, it was a hand optimization removing joins
(`c05c235c03`) and aggregate implementations (`525a43a6de`, 2025-03-17 "incorrect
results returned by agg functions" — collect/min/max) — not the pattern lowering.

### E.10 Determinism / ordering

RETURN target entries are coerced to `jsonb` (`resolveItemList`,
`parse_graph.c:663`), and sort operators are then *re-pointed* at the jsonb
operators so ordering matches the returned values (`updateSortOperatorsForJsonb`,
`parse_graph.c:455-505`) — giving a **total, deterministic cross-type order**
(jsonb's btree order) at the cost of jsonb, not Cypher-spec, orderability.
ORDER BY over non-returned variables is resolved SQL-style via resjunk entries
(`dc817b3b7b`). LIMIT without ORDER BY inherits Postgres's arbitrary order — same
open posture as Gryphon's one permanent oracle skip.

### ★ Transferable to Gryphon (Lens E)

1. **Optionality as a combinator, not a sibling path** (`transformMatchOptional`):
   run the *one* lowering, wrap the result in a left-join extension. Model for
   collapsing `_execute_optional_match` (and `NOT EXISTS` as an anti-join
   combinator) onto `_build_chain_queryset`.
2. **Row-identity constraints emitted at the single chain choke point**
   (`addQualUniqueEdges`): decide Gryphon's multi-hop edge-repetition semantics
   explicitly, then emit the uniqueness qual inside `_build_chain_queryset` so
   inflation-by-duplicate-edge cannot reach an aggregate.
3. **Skip-work optimizations carry a written soundness argument + their own corpus
   + fail-closed sentinels** (`inherit.c:77-92`, `parse_graph.c:2534-2541`,
   `cypher_graphmeta_prune.sql`) — the discipline they adopted after `c05c235c03`.
4. **Shrink the glue**: their quiet zone is "everything in one Query"; their bug
   zone is every custom path outside it. Gryphon's analog: prefer one queryset per
   query over Python-side staging/merging.

---

## Lens T — Testing (what's missing from Gryphon's ladder: little — this peer is
mostly a *negative* example)

- **Oracle model: none.** Validation is `pg_regress` golden files — committed
  expected output diffed textually (`src/test/regress/sql/cypher_*.sql`, ~10,039
  lines across the cypher/graph files; e.g. `cypher_expr.out` asserts literal result
  tables). Self-consistent snapshots only: the exact "ratchet, not an oracle" posture
  Gryphon's §2 identifies. No independent reference implementation anywhere in-tree.
- **Differential/metamorphic: none in-repo.** No TLP/NoREC/PQS/SQLancer harness; no
  fuzzing, generation, or shrinking infrastructure (no hits for any of these in
  `src/test`). The openCypher TCK is not used (no TCK reference in the test tree;
  the only `opencypher` mentions are semantics comments in `parse_graph.c` /
  `nodeModifyGraph.c`).
- **Answer-vs-artifact posture: mixed, deliberately.** DML corpora assert answers
  (golden result tables); the graphmeta-pruning corpus asserts *plans* (85 EXPLAINs
  in `cypher_graphmeta_prune.sql`) — an appropriate artifact assertion there, since
  the property under test is "which scans got pruned," and wrong pruning also shows
  up in the answer-asserting files.
- **Regression capture: strong.** The fix stream routinely lands with regression
  cases in the cypher_* corpora (e.g. `dc817b3b7b` updates
  `cypher_shortestpath2` expected plans; `e12933a7c8`/`acc77d6cbe` extend expression
  tests; issue-numbered fixes reference AG-/AGV2- trackers).
- **What their history says such a suite misses:** every headline silent-wrong bug
  (join drop `c05c235c03`, jsonb never-match `0f0cbf521d`, agg wrongness
  `525a43a6de`, 3VL-in-list-predicates `e12933a7c8`) survived years under a large
  golden corpus — because golden files only pin authored shapes. This is
  empirical confirmation of Gryphon's intent-vs-path lesson from an independent
  10-year dataset.

★ Transferable to Gryphon: nothing to import as a rung (Gryphon's ladder strictly
dominates this suite). Two targeted scenario imports, mined from their bug classes:
(a) ORDER BY over a non-projected field (their `dc817b3b7b` scoping class);
(b) nulls injected into every *new value context* the language grows (their list
comprehension / list-predicate 3VL tail) — as a standing fuzz-generator rule, not a
one-off scenario.

---

## Lens H — History (the archaeology)

**Scale:** repo carries the full upstream Postgres history (59,482 commits total);
the AgensGraph graph layer proper is 348 commits / ~120 fixes on the core lowering
files, 2016-06-27 (`ad4f315dc9`) → 2026-07-03 (`e12933a7c8`), across the
Bitnine → SKAI Worldwide maintainership arc (`README.md`).

### Bug taxonomy (fix stream over the graph lowering files, clustered)

| Class | ~Count | Representative SHAs | Years active |
| --- | :---: | --- | --- |
| jsonb type-boundary (coercion, jsonb-vs-bool, silent non-match, function resolution) | 19 | `e239da247d`, `bb755a7200`, `94095e1d27`, `0f0cbf521d`, `ad533eaa18` | 2017→2026 (full life) |
| Write-path / MVCC visibility / eager evaluation | 15 | `4b61203dce`, `1ff9528642`, `8e2e6ca09f`, `734266048c`, `32acddf6f2` | 2017→2026 (full life) |
| VLE (custom executor node) | 15 | `87c1b78148`, `b168d96d5d`, `2c20d8d1ab`, `47f55467bb`, `24e443c593`, `a706a3966f` | 2017→2025 |
| Variable scoping across clause-subqueries | 9 | `e5f2ae16f8`, `c40f1100b0`, `dc817b3b7b`, `c856e24289`, `7c2e03fe3b` | 2017→2026 |
| NULL / 3VL semantics | 8 | `48a640b9b4`, `946ef7ebb4`, `adb13cdbd7`, `acc77d6cbe`, `e12933a7c8` | 2017→2026 (fixes at HEAD) |
| shortestpath / dijkstra (dedicated nodes) | 6 | `5693d9c2b2`, `104b8b9374`, `f130419786`, `32a521f00c`, `5884b6cc69` | 2018→2019 |
| Join structure / predicate & join drop | 4 | `c05c235c03`, `946ef7ebb4`, `ad7f89b5f6` | 2018→2022 |
| Aggregates | 3 | `525a43a6de`, `e1afc9f839`, `ad533eaa18` | 2025→2026 |
| Graphmeta-pruning maintenance edges (new, 2026) | 5 | `d476935807`, `8a0c9f3cfc`, `36f4fd367f`, `ab775cb88b`, `8b382ccf73` | 2026 |

The signal: **the uniform clause→Query→planner core is nearly silent in the fix
stream. The bleeding concentrates on (a) the universal jsonb value type's boundary,
(b) the custom execution paths (VLE, shortestpath, ModifyGraph), and (c) the
composition/scoping seams between clause-subqueries.**

### Turning-point commits

- `ad4f315dc9` (2016-06-27) — clause piping established: the recursive
  clause-as-subquery composition that defines the architecture.
- `6c5afdae87` (2017-02-08) — VLE moved *out* of the uniform transform into a custom
  executor node: the birth of the hottest bug path.
- `6e80a5a3e0` (2018-03-06) — Cypher expression evaluation wholesale rewritten to
  follow upstream: the fork tax made visible.
- `daf2dd4395` / `24e443c593` (2022-12-15, #598) — second VLE rewrite; deletes
  `nodeNestloopVle.c`; motivation explicitly maintainability/upstream-mergability.
- `c05c235c03` (2022-12-15, #599) — rollback of the join-removal optimization that
  silently broke results: their envelope-WHERE moment.
- `dc817b3b7b` (2026-06-17) — projection un-nesting for ORDER BY scoping: the
  clause-nesting architecture itself corrected.
- `819d11e54e` + `713434f192` + `e156c2a2e3` (2026-07-01/02) — graphmeta
  arc-consistency scan pruning: the new hand-rolled optimization, this time shipped
  with a written soundness argument and a dedicated corpus.
- `e12933a7c8` (2026-07-03, HEAD) — full Kleene 3VL for list predicates, ten years
  in.

### Design-doc / RFC trail

Thin. Reasoning lives in code comments (the jsonb/NULL design statement
`parse_cypher_expr.c:11-19`; the graphmeta soundness argument `inherit.c:77-92`;
the VLE edge-uniqueness idea note `execGraphVle.c:47-54`) and in unusually good
recent commit messages (`32acddf6f2`, `e12933a7c8` read like mini-postmortems).
No standalone design docs in-tree.

### Lifecycle lesson

Forking the kernel bought the deepest possible planner reuse — and a permanent
merge tax (expression-evaluator rewrite `6e80a5a3e0`; PG17 checkpoint merges), a
maintainership handoff (Bitnine → SKAI), and a sibling project (Apache AGE) that
re-did the idea as an extension to escape exactly that tax. For Gryphon: lowering
via the ORM keeps the "borrowed planner" benefit at a fraction of the coupling.

### ★ Predicted Gryphon hotspots (mapped from this taxonomy)

1. **Null semantics in every newly added value context** — their 3VL tail ran the
   project's whole life and was still landing at HEAD. Gryphon's 2VL/3VL boundary is
   specified and TLP-probed for WHERE, but each new operator/aggregate/list surface
   re-opens the question. (Maps to hotspot: null 2VL/3VL boundary.)
2. **The JSON lane** — Gryphon's open-blob `data` sub-paths are coercion-tolerant
   (doc-dev-gryphon-vs-cypher, Ledger B note), i.e. exactly the jsonb boundary that
   is AgensGraph's class #1. Expect silent never-match bugs there first.
3. **Any future skip-work optimization** (scan pruning, join elision, envelope
   short-circuits) — their only pattern-lowering wrong-results bug in a decade was
   an optimization (`c05c235c03`).
4. **Multi-hop row identity** — they foreclosed duplicate-edge inflation
   structurally; Gryphon's findings ledger says row inflation recurs. Until the
   equivalent constraint lives in `_build_chain_queryset`, that class stays
   expressible.
5. **Credits (classes their history bleeds on that Gryphon forecloses):** the
   entire write-path/MVCC/eager class (~15 fixes over the full life, two in the
   final week — `32acddf6f2`, `734266048c`) is *inexpressible* in read-only Gryphon;
   and the jsonb coerce-and-defer class is largely foreclosed on the typed lane by
   schema-as-oracle rejection (`req-grid-traversal-lang-type-strictness`) — their
   `0f0cbf521d` silent never-match is precisely the bug Gryphon converts into a
   loud `SearchExecutionError`.

---

## Net read

**Biggest thing to steal:** the composition discipline — one uniform lowering into a
mature relational layer, with OPTIONAL MATCH as a left-join *combinator over the
same transform* (`transformMatchOptional`) and row-identity (edge-uniqueness)
constraints emitted structurally at lowering time (`addQualUniqueEdges`); both are
direct models for Gryphon's next dispatch collapses. **Biggest thing to avoid:** a
universal coerce-everything value type — the jsonb boundary is their largest,
longest-lived bug class, with silent never-match semantics, and 3VL fixes still
landing at HEAD after ten years; plus custom execution paths outside the uniform
lowering, which cost them two VLE rewrites and the deepest fix tail. **Credit:**
Gryphon's read-only bet deletes their second-largest class outright (~15
write-visibility fixes, still active in 2026), and typed-lane rejection converts
their class-#1 silent wrong answers into loud errors — while Gryphon's testing
ladder (model oracle, fuzzer, TLP, path-coverage gates) strictly dominates their
golden-file-only suite, which demonstrably let every headline silent-wrong bug
survive for years.
