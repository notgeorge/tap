# Dossier — RedisGraph   (clone `5784cb8bfe4e61a82776630398ed429d1002d6ea`, 2026-07-04, license RSALv2 / SSPLv1 / AGPLv3 tri-license per current file headers)

> Protocol: `docs/misc/doc-gryphon-comparative-eval-protocol.md` §4.4. Role in study: **contrast + lifecycle**
> (§2.1 roster) — the system that made the *opposite* architectural bet (bespoke linear-algebra execution
> substrate instead of lowering to a mature relational engine), read birth-to-EOL. All `file:line` anchors
> are at the clone SHA above. IP posture: ideas mined, no code copied (protocol §6; SSPL-family license —
> concepts only, nothing derived ships as copied structure).

## Snapshot

RedisGraph (2018-02-23 → final commit 2025-07-21; 1,705 commits on HEAD, 3,758 across refs) is a Redis
module implementing openCypher over **GraphBLAS sparse boolean matrices**: a MATCH pattern becomes an
*algebraic expression* — a tree of matrix multiplications/transposes over per-label and per-relationship
adjacency matrices — evaluated inside a Volcano-style physical operator tree (`src/execution_plan/ops/`,
41 operator types). The architecture is described in Cailliau et al., "RedisGraph GraphBLAS Enabled Graph
Database" (arXiv:1905.01294). Redis EOL'd the product (announced mid-2023, module EOL 2025-01-31;
redis.io/blog/redisgraph-eol) citing that graph required too much graph-specific expertise; the GraphBLAS
bet survives only in the FalkorDB fork. Inclusion score (§2.2): **zero relational-lowering relevance**
(the anti-cousin), but top-decile history richness (7.5 years, a real bug stream, a lifecycle ending) and
strong readability. It is in the study to answer: what does the executor of a *non*-relational bet look
like structurally, what did that structure cost, and which of its correctness scars are architecture-
independent and therefore predict Gryphon's.

Pipeline in one line: Cypher text → **libcypher-parser** full-Cypher AST (external, swapped in at
`6ab1f5f2`, PR #488) → AST rewriters + a visitor-table validation pass (`src/ast/ast_validations.c`, 2,332
lines) → three specialized logical IRs — **QueryGraph** (pattern), **FilterTree** (predicates),
**AlgebraicExpression** (traversal algebra) — → one physical **ExecutionPlan op tree** → ~14 in-place
rewrite passes (`src/execution_plan/optimizations/optimizer.c:13-66`) → pull-based execution.

## Lens E — Execution  ★ PRIMARY

### E.1 Bottom-turtle Q1 — Is there a logical-plan IR between AST and physical execution?

**Not one — three, each specialized, feeding a single physical op tree that doubles as the optimization
IR.** There is no textbook unified logical-relational-algebra layer; instead:

- **QueryGraph** (`src/graph/query_graph.c`) — the pattern as a graph of QGNode/QGEdge with labels,
  reltype IDs, var-length bounds. Built per MATCH clause from the AST
  (`build_match_op_tree.c:211-217`), split into connected components (`build_match_op_tree.c:32`).
- **FilterTree** (`src/filter_tree/filter_tree.c`) — every WHERE compiled to one predicate tree,
  decomposable into minimal AND-legal subtrees (`FilterTree_SubTrees`,
  `execution_plan_construct.c:136`), each of which becomes a *uniform Filter operator* placed by a
  generic algorithm (E.3).
- **AlgebraicExpression** (`src/arithmetic/algebraic_expression/`) — the traversal-specific algebra:
  each connected component's edges become a tree of matrix-multiply/transpose operations
  (`AlgebraicExpression_FromQueryGraph`, `build_match_op_tree.c:66`), reordered for cost
  (`orderExpressions`, `build_match_op_tree.c:70`, `optimizations/traverse_order.c`) and *optimized as
  an expression tree* (`AlgebraicExpression_Optimize`, `op_conditional_traverse.c:63`).

**What the IRs bought them.** (a) *Plan-level testability*: 1,822 lines of unit tests assert the
**structure** of built/rewritten algebraic expressions with zero execution
(`tests/unit/test_algebraic_expression.c:283-299`, `compare_algebraic_expression`) — mis-lowerings are
caught as wrong expression trees before any data is touched. (b) *A choke point for pattern-level
invariants*: the `:R|R` duplicate-rows bug (H, `f5779ce9`) was fixed **once, in the QueryGraph
constructor** — dedup reltype IDs at IR build (`src/graph/query_graph.c:80-115` post-fix) — rather than
in every consumer. (c) *Optimization as IR rewrite*, not as alternative executors (E.2).

**Is its absence-elsewhere a bug source?** Their long-lived correctness bleeds cluster exactly where
semantics were NOT centralized in an IR: null logic lived in scattered comparison code until 2022 (E.5),
and the transpose bookkeeping lived in hand-maintained derived matrices outside the expression tree for
three years (H.3). Where an IR existed, the fix pattern is one-line-at-the-choke-point; where it didn't,
the fix pattern is a multi-year commit saga. That asymmetry is the strongest pro-IR evidence in this
system.

### E.2 Bottom-turtle Q2 — Dispatch shape: one uniform lowering or special-case paths?

**One clause-conversion switch, one op tree; specialization exists only as (a) leaf-operator choice
driven by IR properties and (b) optimizer rewrites of the uniform tree — never as forked pipelines.**

- The entire clause dispatch is `ExecutionPlanSegment_ConvertClause`
  (`execution_plan_construct.c:340-377`): MATCH/CALL/CREATE/UNWIND/MERGE/SET/DELETE/RETURN/WITH/
  FOREACH/CALL-subquery each append ops to *the same tree*. There is no "simple path" bypass.
- Traversal operator choice is a property test on the IR, not a separate executor:
  `QGEdge_VariableLength(edge) || !QGEdge_SingleHop(edge)` selects `CondVarLenTraverse` vs
  `CondTraverse` (`build_match_op_tree.c:120-143`); both consume the same AlgebraicExpression.
- Scan choice (AllNodeScan vs NodeByLabelScan vs id-seek vs index scan) starts uniform
  (`build_match_op_tree.c:77-106`) and is *narrowed by optimizer passes* (`reduceScans`,
  `utilizeIndices`, `seekByID`, `optimizeLabelScan` — `optimizer.c:27-37`), i.e. the specialized fast
  paths are **rewrites of the general plan**, so they inherit its filters and scoping instead of
  re-implementing them.
- **One shared sub-pattern builder**: `ExecutionPlan_BuildOpsFromPath`
  (`execution_plan_construct.c:284-338`) builds the op subtree for *any* embedded pattern — OPTIONAL
  MATCH streams, MERGE match streams, and WHERE pattern-filters all reuse it via a mocked MATCH clause
  (`ast_mock.c`). OPTIONAL MATCH is then pure composition: `Apply(left, Optional(match_stream))`
  (`build_match_op_tree.c:169-203`), where `Optional` merely emits one empty Record if its child
  produced none (`op_optional.c:28-43`). Pattern predicates (`WHERE (a)-[:R]->(b)`) become Apply-family
  ops over the same builder (`ExecutionPlan_ReduceFilterToApply`, `execution_plan_construct.c:37-52`).
- **"We unified it" refactors in history**: the frontend was wholesale replaced
  (flex/lemon → libcypher-parser, `6ab1f5f2` #488, 2019 — a full parser rewrite to stop maintaining a
  bespoke grammar), and plan construction was split into per-clause builders over one shared modify API
  (`4898fded` #1352, "Separate ExecutionPlan op construction logic into different files"). They never
  needed a "collapse the executors" refactor **because there was only ever one op-tree executor** —
  the Gryphon-style multi-executor shape never existed here.

**Gryphon's next dispatch-collapse candidates, by analogy** (this system's shape → ours):

1. `_execute_optional_match` and `_apply_not_exists` → the RedisGraph move is *one shared sub-pattern
   lowering* (`ExecutionPlan_BuildOpsFromPath`) composed under tiny semantics-only wrappers
   (Optional/SemiApply). Ours should both compose over `_build_chain_queryset` +
   `_apply_predicate_to_qs` rather than owning bespoke lowering.
2. `_execute_type_scan` vs `_execute_bare_type_scan` → scan variants as *narrowing rewrites of one scan
   lowering* (their `reduceScans`/`optimizeLabelScan` posture), not sibling paths with separately
   maintained predicate/order/limit application (`_apply_order_limit_typescan` vs
   `_apply_order_limit_typescan_envelope` is exactly the duplicated-per-path shape they avoid).
3. Envelope vs row-projection (`_execute_advanced`/`_compute_rows` fork) → in RedisGraph, RETURN is a
   *tail* (`op_project`/`op_aggregate` + `op_results` appended by `buildReturnOps`,
   `execution_plan_construct.c:364-366`) over the same match tree; projection mode never changes how
   the pattern lowers. Gryphon's fork of the whole pipeline on RETURN-shape is the analog of a path
   RedisGraph structurally cannot express.

### E.3 Bottom-turtle Q3 — Where are invariants enforced?

**At two structural choke points: the validation visitor (front) and the generic filter-placement
algorithm (middle). Null-tolerance, by contrast, is re-asserted per operator — and that is where they
bled.**

- **Predicate placement is one algorithm for every filter in every query**:
  `ExecutionPlan_PlaceFilterOps` decomposes the FilterTree and, per subtree, walks the op tree to the
  earliest point where **all variables the predicate references are resolved**
  (`ExecutionPlan_RePositionFilterOp` → `ExecutionPlan_LocateReferencesExcludingOps`,
  `execution_plan_construct.c:54-130`), with a recursion blacklist so a filter can't be pushed into a
  Merge/Apply subtree where it would change semantics (`execution_plan_construct.c:60-71,83`). Predicate
  pushdown is therefore an emergent property of one placement routine, not a per-path responsibility.
- **Filter evaluation is one operator**: `op_filter.c:41` — a row passes only on `FILTER_PASS`;
  `FILTER_NULL` and `FILTER_FAIL` both drop. The Cypher "WHERE null drops the row" rule exists in
  exactly one line of the executor.
- **Frontend invariants**: unsupported Cypher constructs are rejected by an explicit visitor table —
  every unsupported AST node type is mapped to `_visit_break` → `Error_UnsupportedASTNodeType`
  (`ast_validations.c:1985-2100`). Full-Cypher parser + explicit deny-table, vs Gryphon's
  narrower-grammar rejection (a credit to us: our unsupported surface can't even parse).
- **Re-asserted per path (the weak spot)**: every operator individually handles "this record slot may
  be missing/null" — e.g. `CondTraverseConsume` must remember to skip records whose source node is
  absent after a failed OPTIONAL MATCH (`op_conditional_traverse.c:163-169`), `ValueHashJoin` had to be
  separately taught to ignore NULLs (`5618d0d1` #1262), aggregate functions each skip nulls themselves
  (`agg_count.c:23`, `agg_sum.c:23`). Distributed null discipline is their per-path re-assertion tax,
  and its bug stream (E.5, H) is the evidence for centralizing ours.

### E.4 Bottom-turtle Q4 — Where does fail-closed live?

**In the filter-placement choke point — with a documented evolution from crash to clean refusal.** A
predicate whose references cannot all be resolved anywhere in the plan is *impossible to silently
drop*: placement fails loudly. Originally `assert(op)` (a crash in debug builds), converted in
`4f26566f` (#1319, 2020-09) to a build-time query error ("Unable to place filter op for entities: …"),
today `Error_InvalidFilterPlacement` (`execution_plan_construct.c:83-90`, `errors.c:127`). Because a
WHERE always *becomes an op that must find a home*, the envelope-WHERE bug shape — a path that accepts
a predicate and never applies it — is structurally inexpressible: the failure mode is "can't place →
error", never "didn't look → wrong rows". FilterTree structure itself is validated at compile time
(`c776aa7f` #804).

The one fail-open crack found: the clause-conversion fallback is `assert(false && "unhandeled clause")`
(`execution_plan_construct.c:375`) and `ASSERT` compiles to a no-op in release builds (`RG.h:77`) — so
an AST type that leaks past the validation table would silently build nothing in production. Their real
guard is the upstream visitor table; the backstop is decorative in release. Lesson: a fail-closed
backstop must be always-on (Gryphon's Python `raise` paths are; keep them so).

### E.5 The protocol's standing Lens-E questions

- **k-hop lowering**: a fixed-length chain is a product of adjacency matrices — conceptually
  friends-of-friends = F² (arXiv:1905.01294). At runtime, `CondTraverse` batches up to 16 source rows
  into a filter matrix F, prepends F to the algebraic expression, and evaluates F·(expression) so only
  reachable rows for the batch are computed (`op_conditional_traverse.c:29-73`); result tuples are
  iterated and re-joined to their source records by row index (`op_conditional_traverse.c:128-199`).
  The historical `42c3c7b3` (#537, "wrong row index within expand-into") shows the row-identity
  bookkeeping of this batching is itself a bug surface — when the join back from a set-oriented
  substrate to per-row records is manual, the row-correlation index is load-bearing state.
- **Variable-length**: a separate leaf op (`CondVarLenTraverse`) backed by an explicit DFS
  (`algorithms/all_paths.c:237-292`), *not* matrix powers. Uniqueness: a frontier node already on the
  path is not expanded further — node-cycle limiting (`all_paths.c:253`, `Path_ContainsNode`) rather
  than Cypher's relationship-uniqueness. Predicates on var-len edges are *migrated into the traversal*
  by an optimizer pass (`filterVariableLengthEdges`, `optimizer.c:40`; `92046602` #1657) — the
  var-len seam Gryphon's E1 work will face: a filter that can't remain a post-hoc op must be
  *explicitly handed* to the recursive machinery, and that handoff is where scope bugs live
  (`e084bb6e` #1668 reordered path filters after all other filters).
- **OPTIONAL MATCH**: composition (`Apply` + `Optional` over the shared sub-pattern builder, E.2). The
  COUNT-inflation trap is avoided because `Optional` emits exactly one empty record on empty child
  (`op_optional.c:33-40`) and downstream ops must tolerate the missing slot (the per-op tax, E.3).
- **Aggregation**: `op_aggregate` hash-groups on XXH64 of the group-key values
  (`op_aggregate.c:84-153`); aggregate functions skip NULL inputs individually (`agg_count.c:23`).
- **Predicate placement + documented mis-scope bugs**: placement is centralized (E.3) but *scoping
  across pipeline stages* still produced bugs: `f2de97a4` (#1361, WITH filter scoping), `c65aecfa`
  (#1397, redundant filter construction and placement), `2d069a11` (#2220, WHERE predicates not
  properly cloned in `WITH *` projections). Prediction transfer: Gryphon's future `WITH` pipelining
  will bleed at stage-boundary predicate scoping even if single-stage placement is sound.
- **NULL / 3VL**: no SQL to emit into — 3VL is implemented directly. `FT_Result` is an explicit
  ternary (`FILTER_NULL/-1, FILTER_FAIL/0, FILTER_PASS/1`, `filter_tree.h:21-24`); AND/OR/XOR/NOT carry
  inline truth tables (`filter_tree.c:274-400`); comparisons detect null operands via a
  `COMPARED_NULL` out-parameter of the single comparator (`value.c:584-651`). **The scar**: until
  2022-11 — 4.5 years in — a null comparison returned plain `false` (2VL collapse); `01d60592` (#2699)
  retrofitted `FILTER_NULL`, and the same commit had to fix the *compile-time constant-folding pass*
  (`_FilterTree_Compact_Pred`) which had separately duplicated (and separately broken) the null rule.
  Two implementations of one truth table drifted — inside one engine, where drift is a bug, not a
  differential.
- **Type handling**: schema-optional coercion-tolerance. Disjoint-type comparisons don't error — they
  return DISJOINT and the filter passes only for `<>` (`filter_tree.c:227-230`); cross-type numerics
  coerce and compare (`value.c:630-638`); ordering across mixed types falls back to a global type-order
  (`value.c:648-650`). Silent plausible answers instead of rejections — the exact posture Gryphon's
  schema-as-oracle strictness (`req-grid-traversal-lang-type-strictness`) rejects. **Credit.**
- **Row-inflation defenses**: cardinality is an *explicit, inspectable property of the lowering*: an
  unreferenced edge yields one row per endpoint pair (boolean semiring dedups parallel edges by
  construction); referencing the edge variable switches the same op into per-edge expansion
  (`EdgeTraverseCtx_CollectEdges`/`SetEdge`, `op_conditional_traverse.c:133-137,189-194`). Their
  inflation bug happened *upstream of that contract*: `:R|R` produced duplicate reltype IDs in the
  QueryGraph → duplicate result rows (`f5779ce9` #2674) — fixed by normalizing the IR once. Where the
  multiplicity contract is explicit, inflation bugs become IR-normalization bugs with single-point
  fixes.
- **Determinism / ordering**: one total-order comparator (`SIValue_Compare` with type-order fallback,
  `value.c:584-651`) serves filters and ORDER BY (`op_sort.c:39`), so mixed-type and null ordering are
  globally consistent. Unordered results follow matrix iteration order; LIMIT-without-ORDER-BY is not
  semantically pinned (same posture as Gryphon's one permanent oracle skip).

### ★ Transferable to Gryphon (Lens E)

1. **Predicate-residue accounting with fail-closed placement** (their filter-op + placement-error
   design, reimagined for a QuerySet lowering): every WHERE subtree must be *consumed* by exactly one
   lowering site or execution refuses. Generalizes the single-hop collapse's apply-or-reject to every
   current and future path. — OPP-1.
2. **One shared sub-pattern lowering** under thin semantic wrappers for OPTIONAL MATCH / NOT EXISTS /
   future WITH. — OPP-2.
3. **Cardinality as a declared property of each hop** (edge-referenced → multiplying; unreferenced →
   deduped), assertable per stage. — OPP-3.
4. **Ternary predicate-evaluation result as a first-class type** at one choke point (their 4.5-year 2VL
   collapse is the cautionary tale for distributed null handling). — OPP-4.
5. **Plan/IR-structure unit testing** the day Gryphon grows a logical IR (their
   `test_algebraic_expression.c` pattern). — OPP-5 (deferred, trigger-bound).

## Lens T — Testing (lighter — hunting only what our ladder lacks)

- **Oracle model**: none. No independent reference implementation anywhere in the tree; flow tests
  (~96 files, `tests/flow/`) assert hand-authored expected result sets — self-consistent assertions,
  the trap our ladder is built against. **Credit to Gryphon's model oracle.**
- **Differential/metamorphic**: one genuine metamorphic relation we lack — **pattern-direction
  reversal**: `tests/flow/reversepattern/__init__.py` mechanically flips every arrow in a MATCH and
  `test_imdb.py:32-43` asserts the reversed query returns the identical result set (and similar
  runtime). This directly ground their transpose machinery — the hotspot where they bled most (H.3).
  Gryphon has TLP (predicate partition) but nothing probing *pattern orientation*, and we own real
  direction-handling code (`_single_hop_directed` / `_redirect_single_hop`, executor.py:510-534).
  No TLP/NoREC/PQS/CERT anywhere in their tree.
- **Fuzzing**: grammar-based via grammarinator over a Cypher grammar (`tests/fuzz/process.py:29-50`),
  but **crash-only**: `ResponseError`s are printed and ignored; only a `ConnectionError` (server died)
  fails the run. No result checking, no shrinking, no seed-replay discipline. It did find real crashes
  (`e73b8ef6` #1408, `ebfc5078` #1429) — and could never have found their 4.5-year silent 2VL bug.
  The clearest external validation of our differential-fuzzer posture. **Credit.**
- **Corpus/TCK**: the openCypher TCK is **ported wholesale** (behave runner,
  `tests/tck/test_tck.py:13-24`) with known-failing scenarios excluded by `@crash`/`@skip` tags — a
  tag-based known-broken manifest with no ratchet pinning when a tag may be removed (contrast our
  mine-not-port discipline + machine-checked coverage ledger). Unit layer: acutest C tests incl. the
  IR-structure suite (`tests/unit/test_algebraic_expression.c`). No mutation testing found. Property
  churn generators exist for storage round-trips (`tests/flow/random_graph.py`, used by
  `test_encode_decode.py` / `test_effects.py`) — write-path focused, not query-semantics.
- **Answer-vs-artifact posture**: mostly answers (result sets); plan-text artifact assertions exist
  (`tests/flow/test_execution_plan_print.py`, `execution_plan_util.py`) for optimizer placement — the
  same "artifact proxy" trap our SQL-scrape lesson names, mitigated here because placement *is* the
  property under test.
- **★ Transferable**: the reversal metamorphic (OPP-6) — cheap, authoring-independent, and it
  exercises a Gryphon dispatch surface (direction redirect) our TLP does not touch.

## Lens H — History (archaeology)

**Scale**: 1,705 commits (HEAD), 2018-02-23 → 2025-07-21; knowledge concentrated in four people
(Jeffrey Lovitz 409, Roi Lipman 352, Avi Avni 252, DvirDukhan 142 — `git shortlog -sn`). 604 commits
match the correctness-fix grep (`fix|bug|wrong|incorrect|inflat|null|predicate|dedup|regress`).

### Bug taxonomy (class → approx. count → representative SHA)

| Class | ~Count | Representative | Note |
| --- | :---: | --- | --- |
| Crashes (message says "crash") | 44 | `c18b4397` (#2327 NULL FT root) | crash-heavy profile matches Dinkel (arXiv:2408.07525): RedisGraph bugs skew to crashes over silent-wrong |
| Memory leaks | 106 | `47d1de7c` (#2207) | manual-memory tax of the C substrate |
| Transpose / algebra maintenance | ~14 | `c9079df2` (#1842 "Maintain transpose"), `1f27fbcc` (#657 wrong semiring), `90351f26` (#1942), `f882ad94` (#54) | see H.3 |
| Filter placement / predicate scoping | ~10 | `4f26566f` (#1319), `f2de97a4` (#1361), `2d069a11` (#2220), `e084bb6e` (#1668) | scoping across WITH stages, not single-stage placement |
| NULL semantics (read side) | ~6 | `01d60592` (#2699 2VL collapse), `5618d0d1` (#1262), `0b8753cc` (#1902) | distributed null discipline |
| Deleted-entity / ID-reuse state | ~5 | `a9ccd3ec` (#3163), `9a709f2d` (#2232), `b0ecf0c8` (#2431) | the Dinkel headline class (entity-ID reuse → stale-liveness crashes) |
| Row duplication / row-identity | ~3 | `f5779ce9` (#2674 `:R|R`), `42c3c7b3` (#537 expand-into row index) | IR normalization + batch row-correlation |
| Special-path divergence (optimized ≠ general) | ~3 | `87a68bb6` (#794 reduce_count missing-relation), `9ba69907` (#3034 optimize-label-scan) | answer-from-metadata fast paths drifting from the general path |

### Turning-point commits

- `6ab1f5f2` (#488, 2019) — **frontend rewrite**: bespoke flex/lemon parser replaced with
  libcypher-parser. Buy-don't-build for the parse layer after maintaining their own; the validation
  visitor table (E.3) is the compensating fail-closed layer a too-permissive parser then requires.
- `4f26566f` (#1319, 2020) — **fail-closed hardening**: unplaceable filter goes from assert-crash to
  clean build-time error. The commit *is* the "no path may silently ignore input" doctrine arriving.
- `3f8e2506` (#1860, 2021) + `c9079df2` (#1842) — **delta-matrix era**: pending-change buffering and
  maintained transposes; performance machinery whose consistency became a standing correctness surface.
- `01d60592` (#2699, 2022) — **3VL retrofit**, 4.5 years in (E.5).
- `4898fded` (#1352, 2020) — plan construction modularized over one shared modify API.

### H.3 The signature saga: hand-maintained derived representations

The single longest correctness thread (2019→2021, ~14 commits: #54, #657, #877, #1032, #1102, #1111,
#1148, #1295, #1523, #1830, #1842, #1869, #1942) is **transpose maintenance**: traversing right-to-left
needs Áµ€, so they progressively moved from transposing on demand → one-time transposes → persistently
maintained transposed matrices per relation type — every step a new way for the derived copy to drift
from the primary (wrong semiring, wrong dimensions, un-transposed delta). The general lesson is not
about matrices: **every hand-maintained derived representation of the data is a standing invariant the
executor must re-prove forever.** Gryphon currently has none (the ORM/SQL substrate maintains its own
indexes); the lowering ladder's rung-4/5 warnings (`req-grid-traversal-exec-lowering`) are exactly the
fence against acquiring one casually. Recorded as validation of the ladder discipline, not an opportunity.

### Lifecycle lesson

Born on a radical substrate bet, EOL'd citing expertise cost (redis.io/blog/redisgraph-eol; Bloor
Research "A eulogy for RedisGraph", 2023): the algebra bought sub-millisecond in-RAM traversal
(arXiv:1905.01294) and forfeited every piece of correctness scaffolding a mature relational engine
inherits — no query optimizer lineage, no battle-tested 3VL, no storage/consistency layer, all rebuilt
by four people. Knowledge concentration + bespoke substrate = unmaintainable at company scale. The
opposite pole of DuckPGQ's "minimize technical debt by riding the relational engine" thesis (CIDR 2023,
cidrdb.org/cidr2023/papers/p66-wolde.pdf) — and of Gryphon's compile-to-ORM bet, which this history
strongly validates.

### ★ Predicted Gryphon hotspots (from their recurring classes)

1. **Stage-boundary predicate scoping** when `WITH` pipelining lands (their #1361/#2220 class) — our
   single-global-WHERE model defers, not removes, this class.
2. **Row-correlation state in batched/multi-stage execution** (their #537 class) — Gryphon's
   multi-stage queryset paths (`_compute_rows`, staged id-collection) carry the same
   join-back-by-index bookkeeping.
3. **Var-len filter handoff** (their #1657/#1668 class) when bounded repetition grows toward rung-4
   recursive CTEs: the predicate must be explicitly threaded into the recursion.
4. **Special-path divergence** (their reduce_count class): any future Gryphon fast path answering from
   metadata (counts, EXISTS shortcuts) must be differentially pinned against the general path.

**Foreclosed for us (credits, not opportunities)**: the entire deleted-entity/ID-reuse class
(read-only executor, UUID entity ids, MVCC substrate — half their crash stream is write-path); the
memory-leak class (GC runtime); the coercion class (schema-as-oracle rejection vs their
DISJOINT-tolerance); the crash-only-fuzzer blind spot (our fuzzer is differential by construction).

## Net read

The foil did its job twice over. First, the bet-level read: a bespoke execution substrate bought
latency and cost them the correctness inheritance Gryphon gets from Postgres for free — their
seven-year fix stream re-earns, by hand, guarantees we never have to prove (3VL, join semantics,
memory safety), which is the strongest external validation yet of compile-to-ORM and of the lowering
ladder's resistance to hand-maintained representations. Second, and more unexpected: **on executor
internal shape, the "opposite" system is architecturally ahead of us** — one clause-conversion
dispatch, one op tree, a single generic fail-closed predicate-placement algorithm, one shared
sub-pattern builder, and IR-structure unit tests mean the envelope-WHERE bug shape was inexpressible
in RedisGraph from day one. Biggest steal: predicate placement as fail-closed accounting at one choke
point, plus the shared sub-pattern lowering for OPTIONAL/NOT-EXISTS. Biggest avoid: distributed
per-operator null discipline (their 4.5-year 2VL collapse) and derived-representation maintenance.
One credit: Gryphon's typed-lane rejection and differential fuzzer each individually foreclose bug
classes this system shipped for years.
