# Dossier — Apache AGE   (clone `9fb7df8c668f0ffb5607f8ecf99953fc5cebfb48`, 2026-07-04, license Apache-2.0)

> Produced under `doc-gryphon-comparative-eval-protocol.md` (template §4.4, lenses §3,
> IP posture §6: ideas mined, no code copied; every claim anchored). Clone is blobless
> (`--filter=blob:none`, full history); all `file:line` anchors are against the clone SHA
> above. GitHub issue numbers (`#NNNN`) refer to apache/age issues/PRs as cited in commit
> subjects and in-source comments — they are anchored via the commits that carry them.

## Snapshot

Apache AGE ("A Graph Extension") embeds openCypher into PostgreSQL as a loadable
extension: a `cypher('graph', $$ ... $$)` set-returning function in a `FROM` clause is
intercepted at parse-analysis time and replaced, in-place, with a native Postgres
subquery tree (`post_parse_analyze_hook` → `convert_cypher_walker`,
`src/backend/parser/cypher_analyze.c:53-143`). It began 2019-03-17 as Bitnine's
AgensGraph-Extension (first commit `bef50e5` "Implement dummy cypher(text) function";
second commit `789f4ca` already "Convert cypher(text) calls to corresponding
subqueries" — the architecture was the first decision). Scale: 1,834 commits across all
branches, 878 on master, HEAD 2026-07-03; knowledge concentrated in one maintainer (John
Gemignani 284 commits, next 81 — `git shortlog -sn HEAD`). All values flow through
`agtype`, a JSONB-derived custom type (`src/backend/utils/adt/agtype.c`, 13,260 lines —
the single largest file in the tree, larger than the whole clause transformer).

**Inclusion score (§2.2):** Core roster member. Relational-lowering relevance: partial —
it lowers Cypher into Postgres *Query trees* (not SQL text) inside the kernel, so the
join/plan layer is genuinely relational, but values ride a custom type and
variable-length paths escape the relational plan entirely (see Lens E). History richness:
high (7 years, a dense correctness-fix stream, in-source postmortem notes). Semantics
documentation: weak-to-recent (null/type decisions mostly discoverable only from code and
fix commits; a 2026 practice of committing design notes at the enforcement site is the
exception — `9f9d0f3`). The protocol's stated purpose for this dossier — "test the
'bolt Cypher onto PG' kludge instinct against the code" (§8) — is answered in the Net
read: the *lowering* half of the bet is better than the instinct suggests; the *value
type* half is worse.

## Lens E — Execution  ★PRIMARY

### Pipeline shape / IR count — the bottom-turtle question 1

Pipeline: Cypher text → own bison AST (`cypher_gram.y`, 3,785 lines; nodes are PG
`ExtensibleNode`s) → **hand-written transform to PostgreSQL `Query` trees**
(`cypher_clause.c`, 9,511 lines) → standard PG planner → standard PG executor (plus
custom scan nodes for writes). That is: **AGE has a logical-plan IR, but by adoption,
not construction** — the target of its lowering *is* Postgres's logical representation
(`Query`/jointree), consumed by a mature optimizer it did not have to write.

What the borrowed IR buys them, concretely observed:

- **Join planning for free.** MATCH lowering emits no join order at all — connectivity
  is an AND'ed qual list handed to the planner as a `FromExpr`
  (`cypher_clause.c:4624-4707` `transform_match_pattern`); index selection, join
  strategy, `EXPLAIN` all inherited.
- **An invariant choke point for free.** Permissions ride PG's `RTEPermissionInfo`
  (`add_rte_permissions`, `cypher_clause.c:424-514`); Row-Level Security arrived as a
  bolt-on that mostly *reused* kernel machinery (`1702ae0`, #2309).
- **Where the bugs then live:** almost never in join execution. The correctness-fix
  stream (Lens H) concentrates in (a) the hand-written AST→Query transforms and (b) the
  `agtype` value boundary. The external validation literature agrees: Dinkel et al.'s
  state-aware GDB testing found 11 AGE bugs skewed 8-parser / 1-executor
  (arXiv:2408.07525) — with the caveat, flagged in the study's own literature notes,
  that AGE's low clause coverage *masks* executor surface rather than proving it robust.

**Reading for Gryphon:** this is the same bet Gryphon made one layer up — lower into
Django ORM QuerySets and let PG plan. AGE is 7 years of evidence that the bet is right
*and* that it relocates rather than removes the bug surface: the translation layer
(their `transform_cypher_*`, our `executor.py`) is where the blood is. The absence of an
*own* logical IR did not hurt AGE where it borrowed one; it hurt exactly where it
side-stepped the borrowed one (VLE, below).

### Dispatch structure — bottom-turtle question 2

**One uniform top-level lowering, many special-case interiors, and one structurally
separate second lane.**

- Top: a single central dispatch, `transform_cypher_clause`
  (`cypher_clause.c:519-617`) — an `is_ag_node` ladder over ~14 clause kinds, chaining
  each clause's Query as a subquery RTE of the next (each clause consumes its
  predecessor's rows as a table). The `else` is a hard error (`:595-598`) — fail-closed
  at the router.
- Interior: each clause transform is a large bespoke function juggling `ParseState`
  namespaces by hand; predicate and variable-scope knowledge was historically
  *per-clause* — which is where the silent drops happened (next section).
- Second lane: write clauses (CREATE/SET/DELETE/MERGE) do not execute as plain Query
  trees. The transform appends a sentinel `FuncExpr` as the **last targetlist entry**;
  a planner hook (`set_rel_pathlist`) sniffs every subquery RTE for that sentinel
  (`get_cypher_clause_kind`, `src/backend/optimizer/cypher_paths.c:101-135`) and
  replaces all plan paths with a CustomScan (`handle_cypher_*_clause`). The
  parse-to-planner contract is *implicit pattern-matching on plan shape* — a fragile
  seam, and the chained-DML visibility bug family lives on it: MATCH after CREATE
  returning 0 rows (`217467a` #2308, `d6f1b7f` #2341), chained MERGE not seeing sibling
  MERGE's writes (`20ada84` #1446), CID visibility for CREATE+WITH+MERGE (`d0741d8`
  #2343).

**"Did they unify the executor?"** No single big-bang collapse; instead a recurring
pattern of *partial rewrites after pain*: `Reimplement list comprehension` (`1251096`
#2169), `Refactor the IN operator to use '= ANY()'` (`85b41b0` #1236), `DELETE refactor
and bug fix` (`fa5782f`), `SET refactor` (`23ec457`), `Refactor VLE edge uniqueness`
(`941d678`), two 2026 VLE overhauls (`f02eda0` #2420, `73d0705` #2421). The most
instructive unification is small: `transform_cypher_clause_with_where` used to contain
per-clause-type knowledge of where a WHERE node lived, and *lost* WITH's WHERE when the
WITH→RETURN wrapper rewrite discarded it — silently returning unfiltered rows. The fix
(`4817bfb`, #646, 2023) changed the function signature so the WHERE is an **explicit
required parameter** every caller must hand over — converting tribal per-clause
knowledge into a passed obligation. That is the single-hop-collapse move in miniature,
and it is the most transferable structural idea in this dossier.

### Invariant enforcement — bottom-turtle question 3

Split verdict, and the split is the lesson:

- **Enforced at one choke point:** permissions (via PG's RTE machinery, above);
  terminal-DML result typing — every trailing write clause is coerced to agtype at the
  single exit of the central dispatch (`cypher_clause.c:600-611`); edge-uniqueness
  (below).
- **Re-asserted per path:** null handling. `agtype` introduces a *second* null
  (`AGTV_NULL`) distinct from SQL `NULL`, and every C operator/function re-checks both
  by hand — the comment "Return null if arg_agt is null. This covers SQL and Agtype
  NULLS" recurs verbatim across `agtype.c` (`:3184`, `:3308`, `:3429`, `:5401`, `:5571`,
  …), and arithmetic ops each re-test `AGTV_NULL` (`agtype_ops.c:168-172`, `:535`,
  `:688`, `:784`, `:908`, `:1004`). There is no null choke point, and the null-crash
  class recurred for the project's whole life: crash on NULL to UNWIND (`692cb02`
  #1302), `SELECT agtype(null)` server crash (`b5d866f` #1303), null operand for access
  operators (`16374c3` #1389), null key name (`c215372` #1956), NULL start-offset in
  `substring()` (`6c40838` #2401), null propagation through slice bounds (`6f520fe`
  #2400) and through `unnest`/`single()` 3VL (`39273ca` #2406, merged **the day before
  this clone**). Seven years in, the class is still paying out.

### Fail-closed — bottom-turtle question 4

Fail-closed lives at the *routers* (clause dispatch `cypher_clause.c:595-598`;
expression transform errors on unrecognized nodes, `cypher_expr.c:169,245,258`; planner
hook errors on invalid clause kind, `cypher_paths.c:93`). **It does not live inside the
transforms, and that is exactly where AGE's envelope-WHERE-shaped bugs recurred** — a
path accepting input it silently ignores:

- `WITH ... WHERE` — WHERE accepted, silently dropped (`4817bfb`, #646).
- `CALL ... YIELD ... WHERE` — same shape (`015434e` "Fix Bug with CALL... YIELD clause
  ignores WHERE").
- Single-node labeled pattern-expression `WHERE (a:Person)` — accepted, label **never
  tested**: `make_path_join_quals` (`cypher_clause.c:6220`) early-returned for
  vertex-only patterns (`list_length(entities) < 3`), emitting no quals, making the
  sub-pattern uncorrelated and trivially true (`fe48740`, #2443, fixed **June 2026**).
- OPTIONAL MATCH with subquery-bearing WHERE — predicate either silently dropped in the
  inner transform or hoisted to a post-filter that destroyed null-preserving rows
  (`15030a0` #2380; in-source postmortem comment `cypher_clause.c:3856-3870` and
  `:4016-4028`, issue #2378).

A 2020-born system with a fail-closed router still shipped accept-and-ignore bugs in
2023 and 2026 because the *interior* of each special-case transform can drop what the
router correctly admitted. Gryphon's AAR rule ("no dispatch path may accept input it
silently ignores") has to hold at every consumption site, not just at `_dispatch_pattern`.

### Join & traversal lowering (k-hop, var-length, OPTIONAL, aggregation)

- **Fixed k-hop:** each vertex/edge entity becomes a label-table scan RTE; connectivity
  becomes graphid-equality quals (`prev.id = edge.start_id` etc.,
  `make_directed_edge_join_conditions`, `cypher_clause.c:4776-4810`; assembled
  `transform_match_pattern` `:4624-4707`). Join *order* is entirely the PG planner's.
- **Variable-length (the E1 seam):** NOT relational. A `[*min..max]` becomes an opaque
  set-returning C function `vle` spliced into the FROM clause
  (`cypher_clause.c:148-155`, `append_VLE_Func_to_FromClause`), which runs a DFS in C
  over a **process-global cached graph snapshot** (`age_vle.c`; global context
  `age_global_graph.c:137-155`). The in-source design note (`age_vle.c:20-63`, added
  `9f9d0f3` #2349/#2413) pins the semantics — edge-isomorphism per openCypher, vertices
  may repeat — and the cost — unbounded patterns are O(E!) with no termination
  guarantee beyond edge depletion. The side-cache required a shared-memory
  version-counter invalidation scheme incremented by Cypher mutations *and* SQL
  triggers (`age_global_graph.c:54-99`) and still produced a standing bug family:
  stale-visibility (`217467a` #2308, `d6f1b7f` #2341), failure on read-only replicas
  (`346f319` #2160), a self-deadlocking mutex (`23cbe57` #2433), zero-hop self-binding
  (`12e2a31` #2382), VLE NULL under chained OPTIONAL MATCH (`5005c21` #2337). **The
  moment AGE left the relational plan, it had to re-earn transactional consistency by
  hand — and never fully has.** This is the strongest single datum for Gryphon's E1
  decision: lower variable-length *inside* the plan (rung-4 recursive CTE per
  `req-grid-traversal-exec-lowering`), never as an out-of-plan traversal service with
  its own cache.
- **OPTIONAL MATCH:** lowered as a **LATERAL LEFT JOIN** — previous clause chain as the
  left subquery, the optional pattern as the lateral right subquery
  (`transform_cypher_optional_match_clause`, `cypher_clause.c:3995-4127`). The
  hard-earned rule, written into the source after #2378: the OPTIONAL MATCH's WHERE
  must become the **LEFT JOIN's ON condition** — the only placement that both scopes
  the predicate to the optional binding and preserves null-filled outer rows
  (`:4016-4028`, `:4057-4074`). Inside the inner subquery it mis-scopes; as an outer
  post-filter it deletes the null-preserving rows. Three placements, one correct.
- **Aggregation:** Cypher's implicit grouping is lowered by construction — while
  transforming RETURN items, every item that did *not* contain an aggregate is
  accumulated as a GROUP BY key (`transform_cypher_item_list`,
  `src/backend/parser/cypher_item.c:57-133`), then validated by PG's own
  `parse_check_aggregates` (`cypher_clause.c:3565-3568`). Grouping is derived from the
  target list in one pass — not re-decided per execution path.

### Predicate placement (+ documented drop/mis-scope bugs)

Non-optional MATCH: pattern-connectivity quals, property-constraint quals, and the WHERE
expression are AND'ed into a **single jointree qual** (`transform_match_pattern`,
`cypher_clause.c:4649-4706`) — one funnel, then the planner places predicates. The
documented drop/mis-scope record is extensive and is this dossier's core Lens-H payload:
`#646` (WITH), CALL-YIELD (`015434e`), `#2443` (pattern-expression label,
2026), `#2378/#2380` (OPTIONAL MATCH), `e396815` #339 ("entities in WHERE clause have
wrong Expr", 2021), plus the scoping-adjacent cluster (`0f0d9be` #1955 list-comprehension
in WHERE, `798218f` #1045 path var in WHERE, `bef363a` #1399 EXISTS on non-existent
labels). Every one is the envelope-WHERE shape: the funnel existed, and a special-case
path walked around it.

### NULL / 3VL lowering

AGE's null story is a three-regime accident where Gryphon's is a two-regime design:

1. SQL `NULL` operands → PG strict-function machinery → SQL 3VL (row drops from WHERE).
2. `AGTV_NULL` (agtype null) inside operators → hand-checked per function
   (`agtype_ops.c:168-172` "openCypher: arithmetic over null yields null", et al.).
3. **Equality is implemented over the total order:** `agtype_eq` compares via
   `compare_agtype_containers_orderability` (`agtype_ops.c:1052-1080`), and the scalar
   comparator returns 0 for NULL-vs-NULL (`compare_agtype_scalar_values`,
   `agtype_util.c:2180-2186`) — so at the operator level two agtype nulls are *equal*
   (Cypher mandates `null = null` → `null`). Equality and orderability — which Cypher
   deliberately separates — share one comparator.
4. A bare agtype value coerced to boolean in WHERE goes through `agtype_to_bool`, which
   raises an error on agtype null (`agtype.c:3147-3161`; error table `:3119` "cannot
   cast agtype null to type %s") rather than treating not-true as filtered.

The same predicate surface can thus filter (SQL null), match (agtype null under `=`'s
orderability), or error (agtype null under boolean coercion) depending on which null
arrives by which route. Gryphon's documented 2VL-literal / 3VL-field boundary
(`doc-dev-gryphon-vs-cypher.md` Ledger B) plus a *single* null is structurally simpler
than what AGE grew; AGE is the cautionary exhibit for what an undesigned null boundary
looks like after seven years of patching.

### Type handling

Coercion-permissive, with a decade-long walk-back:

- `+` between a string and a number **concatenates** (`agtype_add`,
  `agtype_ops.c:145-190`); int/float cross-coerce silently; `agtype` compares any type
  to any type via the total order (no cross-type rejection anywhere in
  `agtype_ops.c:1052-1290`).
- History then removed coercions one bite at a time: `Remove implicit casting from int
  to bool` (`52bfe9b` #923), `Typecast bool to integer and vice versa` churn (`87f8601`
  #905, `d0323f9` #827), `PG Boolean used as AGTYPE object` (`9b4a3e5` #1953),
  `Regression in string concatenation` (`190354c` #2243).
- The crash class at the cast boundary is the one the study's literature notes flagged:
  `unknow type of agtype container 0` (`56b2fcc` #1347), `agtype_to_int4 crash`
  (`b25f6f7` #1329), container-type confusion (`4e26265` #1043, `5971374` #395),
  `coalesce` segfault (`26f748c` #2256), `toFloatList()` stack overflow (`fafdaa1`
  #2451, 2026).
- **The 2026 turn:** `5ef7d6d` (#2303, June 2026) introduces real PG **composite types
  for vertex and edge** — `vertex(id, label, properties)`, `edge(id, label, end_id,
  start_id, properties)` — with direct field access for read queries, explicitly noting
  write executors remain "strictly tied to agtype". After six years, AGE is walking
  reads back *out* of the everything-is-one-blob-type design toward typed lanes. This is
  the strongest external validation in the study for Gryphon's typed-model /
  schema-as-oracle bet (`req-grid-traversal-lang-type-strictness`): the peer that chose
  the opposite pole is migrating toward ours, under performance and correctness
  pressure, one lane at a time.

### Row-inflation defenses

- Within a MATCH, Cypher's relationship-uniqueness is enforced by injecting an
  `_ag_enforce_edge_uniqueness` function call into the quals over all edge ids in the
  path (`prevent_duplicate_edges`, `cypher_clause.c:4713-4768`; arity-specialized
  variants for common path lengths). A *semantic* dedup at the qual level — not a
  DISTINCT slapped on output.
- The count(*) wrongness (`ae058ef`, #945) is the mirror image of Gryphon's inflation
  class: an `output_node=false` "optimization" for anonymous nodes short-circuited tuple
  flow between chained clauses, deflating `MATCH () RETURN count(*)`. The fix sets
  `output_node = true` (`cypher_clause.c:5990` — the TODO comment confessing "we likely
  need to remove all of the output_node logic" is still in the tree in 2026). Lesson:
  a cardinality-affecting fast path is a standing liability; delete it rather than
  gate it.

### Determinism / ordering

AGE relies on plan-order and pays for it in its own test suite: fixes for unsorted
output (`c3f8caf` #1507), big-endian-dependent order (`3b8aaa6` #1892), a
nondeterministic regression test (`a29e281` #2365), locale-dependent string comparison
in tests (`14732bf` #2439), and — 2026 — adding ORDER BY to nondeterministic RETURN
queries in the tests themselves (`3cc74a4` #2436). Orderability itself needed a
correctness fix (`88ead70` #870; `a3cdba0` "Fix compare_agtype_scalar_values returned
result"). Their remedy is *constrain the query*; Gryphon's remedy is *normalize the
capture* (sorted `pk__in` collections, `req-grid-traversal-exec-sql-capture-3`) —
Gryphon's is strictly stronger for snapshot testing because it doesn't distort the
query under test.

### ★ Transferable to Gryphon (Lens E)

1. **Predicate-as-required-parameter** (`4817bfb`): make every lowering path *sign for*
   the WHERE it must apply, structurally — the generalization of the single-hop
   collapse to the remaining paths (see opportunities and
   `dispatch_collapse_candidates`).
2. **OPTIONAL MATCH WHERE = join-ON semantics, and only that** (`#2378`,
   `cypher_clause.c:4016-4028`): three candidate placements exist and two are wrong in
   ways that return plausible rows.
3. **Var-length stays in-plan** (`age_vle.c` + `age_global_graph.c:54-99` + the five
   cache-coherence fix commits): pre-commit this as a spec constraint on E1 before any
   code exists.
4. **Implicit grouping derived in one pass from the target list**
   (`cypher_item.c:57-133`) — matches Gryphon's `_compute_rows` posture; keep it derived,
   never per-path.
5. **Design-note-at-the-enforcement-site** (`9f9d0f3`): AGE commits semantics+cost
   postmortems *into the source file* where the misdiagnosis would happen. Cheap,
   Player-3-legible, worth copying as practice.

## Lens T — Testing

- **Oracle model: none independent.** The suite is pg_regress golden files — 21,046
  lines of scenario SQL (`regress/sql/`), 47,143 lines of expected output
  (`regress/expected/`), text-diffed. This is exactly the "ratchet, not oracle" Gryphon
  names (`doc-gryphon-testing-philosophy.md §2`): first-write wrongness is protected
  forever. Observed concretely: expected outputs pin duplicate rows and arbitrary
  orderings as "correct" (the row-churn throughout the `ae058ef` diff), and the count(*)
  fix had to *rewrite* expected outputs — the goldens had been faithfully guarding the
  bug (#945).
- **Differential/metamorphic: none in-repo.** No TLP/NoREC/PQS, no second
  implementation, no plan-vs-plan differential (`grep -ri fuzz` finds only the
  `fuzzystrmatch` PG-contrib wrapper). External researchers supplied the differential
  axis: Dinkel et al. (arXiv:2408.07525) found 11 bugs, 8 parser / 1 executor —
  consistent with a suite that asserts self-consistency only. AGE's crash-not-error
  posture at the agtype boundary (#1302/#1303/#1347 fix commits above) is what a missing
  fail-closed rung looks like from the outside.
- **Fuzzing/generation: none in-repo.** No generator, no shrinking, no
  replay-from-seed. CI is installcheck (pg_regress) plus driver test workflows
  (`.github/workflows/installcheck.yaml` et al.).
- **Corpus/coverage/TCK:** no openCypher TCK usage found in the tree; no coverage
  gates; the corpus is hand-authored per feature/fix. Regression capture discipline is
  genuinely good: fix commits routinely land with new regress scenarios (`fe48740`,
  `12e2a31`, `ae058ef` all add tests) — the ratchet is well-fed even though it is only
  a ratchet.
- **Answer-vs-artifact posture:** pg_regress asserts the answer *as ordered text*, which
  drags in row order, locale, endianness, and float formatting as false failure axes —
  four separate fix commits exist just to stabilize the suite (`c3f8caf`, `3b8aaa6`,
  `14732bf`, `a29e281`). Their fix direction (add ORDER BY to the tested queries,
  `3cc74a4`) changes the query under test; Gryphon's identity-set envelope comparison +
  deterministic SQL capture is the stronger posture and should be recorded as a credit,
  not revisited.
- **★ Transferable to Gryphon:** almost nothing to import — this lens is a *mirror*, not
  a mine. AGE is the control group for Gryphon's whole ladder: same problem, strong
  golden-file ratchet, no oracle rung — and a 7-year silent-wrong-answer stream. The one
  importable T-item: AGE's regress suite tests *its own upgrade path* as a first-class
  surface (`90c33eb` #2364, `54e19fa`, `a1b749a`) — the analogous Gryphon surface
  (Gridkin corpus vs. grammar/schema migrations) is already covered by snapshot
  regeneration discipline, so this is noted, not proposed.

## Lens H — History

**Scale:** 1,834 commits (all branches; 878 on master), 2019-03 → 2026-07, single
dominant maintainer (284/878), long-tail contributors. Multi-PG-major support is done as
*separate release branches* merged periodically (`c075703` "Merge branch PG12 (version
1.3.0) into the master branch"; `b3219fd` PG18, `d336d6d` PG17, `81ecd56` PG16) — a
standing maintenance tax Gryphon avoids entirely by riding the ORM.

**Bug taxonomy** (method: `git log -iE --grep='fix|bug|wrong|incorrect|crash|segfault|regress'`
subject-line clustering, N≈456 matches; classes overlap so counts are indicative, and
write-path counts are inflated by the words CREATE/SET/DELETE appearing in write-feature
fixes — read them as ranks, not measures):

| Class | ~Count | Representative fixes |
| --- | ---: | --- |
| Write-path semantics & visibility (CREATE/SET/DELETE/MERGE) | 52 | `20ada84` (#1446 chained MERGE), `00e0c58` (#1691 MERGE dup vertices), `5fbe064` (#1398 SET-then-DELETE), `e1b47e9` (#1907), `d0741d8` (#2343 CID visibility) |
| VLE / variable-length | 26 | `346f319` (#2160 replicas), `12e2a31` (#2382 zero-hop), `23cbe57` (#2433 deadlock), `d73d3eb` (#1910 exists(vle) crash), `5005c21` (#2337) |
| Variable scoping / reuse / ambiguity | 23 | `0ab0ebb` (#1002), `e22c5ac` (#975), `75a0e43` (#997), `a26d6a6` (#1219), `b2d616d` (#1393), `56a92d8` (#1884), `27d4375` (#876) |
| Crashes at the agtype boundary | 22 | `56b2fcc` (#1347 container 0), `b5d866f` (#1303 agtype(null)), `26f748c` (#2256 coalesce), `fafdaa1` (#2451), `b25f6f7` (#1329) |
| Type casts / coercions | 20 | `52bfe9b` (#923), `9b4a3e5` (#1953), `190354c` (#2243), `87f8601` (#905) |
| Null handling (dual-null) | 17 | `692cb02` (#1302), `16374c3` (#1389), `6f520fe` (#2400), `39273ca` (#2406), `c215372` (#1956) |
| Predicate drop / mis-scope | 17 | `4817bfb` (#646 WITH), `015434e` (CALL-YIELD), `fe48740` (#2443 label filter), `15030a0` (#2380 OPTIONAL), `e396815` (#339) |
| Ordering / determinism | 9 | `88ead70` (#870), `c3f8caf` (#1507), `3b8aaa6` (#1892), `3cc74a4` (#2436) |
| Memory/resource leaks | 8 | `64a415e` (#2020), `05487a0` (#2046), `0ea9464` (#2258) |
| Aggregation cardinality | — | `ae058ef` (#945 count(*)) |

**Turning-point commits:**

- `789f4ca` (2019, commit #2): clauses-as-chained-subqueries — the architecture chosen
  on day two and never revisited; everything else is interior.
- `4817bfb` (2023): WHERE becomes an explicit parameter — per-clause knowledge converted
  to a passed obligation after a silent drop.
- `ae058ef` (2023): the cardinality-affecting fast path indicted (TODO still present,
  `cypher_clause.c:5983-5989`).
- `9f9d0f3` (2026): semantics + cost model design note committed into `age_vle.c` to
  "prevent future misdiagnoses" (#2349) — postmortem-at-the-site practice.
- `5ef7d6d` (2026): composite vertex/edge types for reads — the typed-lane turn, the
  agtype monoculture partially walked back.
- `73d0705`/`f02eda0` (2026): VLE overhauls — the out-of-plan traversal engine still
  demanding rewrites seven years in.

**Design-doc/RFC trail:** thin. Reasoning lives in commit messages and (recently)
in-source notes; no RFC directory. The 2026 in-source-note practice is the compensation.

**★ Predicted Gryphon hotspots (mapped from AGE's bleed):**

1. **Every new clause re-opens the predicate-drop class.** AGE dropped WHERE in WITH
   (2023), CALL-YIELD, pattern-expressions (2026), OPTIONAL MATCH (2026) — each a *new
   path* that failed to sign for the predicate. Gryphon's WITH-pipelining and
   per-MATCH-WHERE work (Ledger C futures) will re-open the same class unless the
   predicate-as-parameter contract is structural first.
2. **Variable scoping across clause boundaries becomes the top read-path class once
   WITH lands.** It is AGE's largest non-write cluster (~23 fixes) and Gryphon has no
   equivalent surface yet — the bugs arrive with the feature.
3. **OPTIONAL MATCH WHERE placement** — Gryphon's v0 scoreboard path should be probed
   against the three-placements analysis now, while the surface is small.
4. **Var-length implementation choice** — if E1 ever reaches for an out-of-plan
   traversal (including "a PG graph extension as a backend", the execution spec's own
   Future note), AGE's cache-coherence family is the cost forecast.

**Credits (classes Gryphon's architecture forecloses — recorded per §7.3):**

- The entire ~52-fix write-path/MERGE-visibility family: inexpressible; Gryphon rejects
  write clauses at parse time (Ledger C) and runs on `search_readonly`.
- The coercion family: Gryphon rejects cross-type predicates
  (`req-grid-traversal-lang-type-strictness`); AGE spent 2022-2026 removing coercions
  one regression at a time, then started building typed lanes.
- The dual-null family: structurally absent — Gryphon has one null with a documented
  two-regime boundary, plus `IS KNOWN`/`IS UNKNOWN` for the observational question.
- The golden-file determinism churn: foreclosed by deterministic SQL capture and
  identity-set envelope comparison.

## Net read

The "bolt Cypher onto Postgres is a kludge" instinct is half right, and the study needed
to learn *which* half. The lowering half is vindicated: chaining every clause into
Postgres's own logical Query representation bought AGE a mature planner, EXPLAIN,
permissions, and joins that essentially never appear in its bug stream — the same
inheritance Gryphon gets through the ORM. The value-type half is the kludge: `agtype`
created a second null, a crash-prone cast boundary, coercion semantics that took years
to walk back, and in 2026 AGE began re-introducing typed composite lanes for reads —
converging on the bet Gryphon started with. The biggest thing to steal is small and
structural: after their WITH clause silently dropped its WHERE, they made the predicate
an explicit parameter every transform must sign for (`4817bfb`) — the generalization of
Gryphon's single-hop collapse, and the medicine for the paths still outside our chain
lowering. The biggest thing to avoid is the VLE engine: the one subsystem that left the
relational plan needed its own shared-memory cache-invalidation scheme and still bleeds
consistency bugs seven years later — variable-length paths must lower in-plan. The
standing credit: AGE is the control experiment for Gryphon's testing ladder — the same
translation problem, a well-fed golden-file ratchet, no independent oracle — and its
history is precisely the silent-wrong-answer stream (dropped WHEREs, wrong counts,
trivially-true predicates) that Gryphon's model oracle and fail-closed dispatch were
built to make loud.
