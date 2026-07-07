# Dossier — GraphFrames   (clone `28d181c00e8364edc3114ba6d803e1b2520b2c17`, cloned 2026-07-04, HEAD dated 2026-06-16, license Apache-2.0)

> Study artifact of `doc-gryphon-comparative-eval-protocol.md`. Every claim carries an
> anchor into the clone at `comparanda-clones/graphframes/` (file:line at the clone SHA,
> or a commit SHA / PR# from its history). IP posture: ideas mined, no code copied.

## Snapshot

GraphFrames is the Apache-Spark package that gives Spark DataFrames a graph API: a graph
is literally two DataFrames (`vertices` with an `id` column, `edges` with `src`/`dst` —
`core/src/main/scala/org/graphframes/GraphFrame.scala:1227-1242`), and its query surface
is **motif finding** — a tiny domain pattern language (`(a)-[e]->(b); !(b)-[]->(a)`)
compiled directly into a chain of DataFrame joins that Spark's Catalyst optimizer then
plans (`GraphFrame.scala:1033-1041`, `1479-1663`). It is *not* Cypher (no WHERE, no
RETURN, no aggregation in the language — filters and projections are ordinary DataFrame
operations applied *after* `find()`, `GraphFrame.scala:589-591`), but it is one of the
purest living examples of the relational-lowering bet Gryphon made: a graph pattern
becomes relational joins over two base tables, and everything else — optimization, join
reordering, predicate pushdown, null semantics, type coercion — is inherited from the
host relational engine. Born at Databricks 2015-2016 (Hunter/Meng/Bradley, `git shortlog
-sn HEAD`), near-dormant ~2019-2023, revived 2024+ by a new maintainer generation (Sem
/ SemyonSinchenko, 100 commits) who added var-length and undirected patterns — and whose
commit stream is the freshest bug data in this study. 627 commits total (`git log
--oneline | wc -l`).

Inclusion score (§2.2): relational-lowering relevance **high** (pattern → join chain over
two tables — the same shape as Gryphon's chain machinery over Entity/Edge); source
availability **high** (Apache-2.0, readable Scala, the whole lowering is ~500 lines);
history richness **high** (10 years, two maintainer eras, issue-linked fixes);
semantics documentation **medium** (semantic decisions live in scaladoc on `find()`,
not a spec). Verdict: **deep**.

---

## Lens E — Execution  ★ PRIMARY

### Pipeline shape / IR count

Motif string → **three string-level regex rewrites** → combinator parse into a
**6-node pattern ADT** → left-fold that emits DataFrame joins per pattern → Spark
Catalyst logical plan → physical plan.

- String rewrites (pre-parse, on the raw query text):
  - incoming-edge reversal `(a)<-[e]-(b)` → `(b)-[e]->(a)` and bidirectional expansion
    (`pattern/patterns.scala:72-97`),
  - fixed-length expansion `(a)-[e*3]->(b)` → a `;`-joined chain of 3 single-hop terms
    with synthesized mid-vertex names (`patterns.scala:102-134`),
  - var-length dispatch: `find()` regex-matches the *whole* pattern string for
    `*min..max` before parsing and, on match, expands to a union of fixed-length motifs
    (`GraphFrame.scala:618-640`, `642-674`).
- The parse itself is a Scala `RegexParsers` combinator grammar producing
  `Pattern`/`Vertex`/`Edge` case classes — six node types total
  (`patterns.scala:29-52`, `284-300`).
- Lowering: `findSimple` folds the pattern list, `findIncremental` pattern-matches each
  term and joins it onto the accumulated DataFrame (`GraphFrame.scala:1033-1041`,
  `1479-1663`).

**Bottom-turtle Q1 — logical-plan IR?** GraphFrames has **no graph-level logical IR of
its own** — the 6-node pattern ADT is the only intermediate, and it lowers straight to
DataFrame operations. But the target of the lowering *is* a logical-plan IR: a Spark
DataFrame is a lazily-built Catalyst `LogicalPlan`, so join reordering, predicate
pushdown, and cost-based optimization are all inherited. The scaladoc leans on this
explicitly — motif performance guidance is "enable Spark's CBO and join reordering"
(`GraphFrame.scala:595-610`), i.e. *the optimizer they never wrote is Spark's*. The
one place a comment admits the missing planner: `// TODO: expose the plans from joining
these in the opposite order` (`GraphFrame.scala:1630`) — join-order choice is frozen by
lowering order because GraphFrames has no plan layer of its own to defer it.

Where the *absence* of an own-IR demonstrably cost them: **desugaring happens on the
query text, by regex, because there is no plan layer to normalize on** — and that layer
is their single hottest bug cluster (see Lens H: #754, #771, #781, #728 — four
composition fixes in four months). The transferable reading for Gryphon: a thin
transpiler *is* fine without a logical IR **when the lowering target is itself a strong
plan IR with an optimizer** (Catalyst). Gryphon's target (Django ORM QuerySets) is a much
weaker plan layer — no join reordering, no cross-queryset composition — so Gryphon gets
less for free from the same bet; and *regardless of IR, desugaring below the AST (on
text) is the demonstrated bug factory*.

### Dispatch shape (bottom-turtle Q2)

The core lowering is **one uniform path**: `findIncremental` is a single case-match over
the six AST node shapes, sub-keyed only by *binding state* — whether each named vertex
was already `seen` in prior terms decides join-to-existing-column vs cross-join-new-table
(`GraphFrame.scala:1449-1465`, `1488-1663`). Every term of every motif flows through this
one fold. It has been remarkably stable: `git log -S findIncremental` shows essentially
two touches in ten years — the 2018 negation rework (`024f939`) and the 2025 undirected
support (`0179298`) — a strong argument that a uniform binding-state-driven lowering core
is a durable bottom turtle.

But *around* the uniform core, each newer feature was bolted on as a **rewrite layer or
set-operation wrapper**, and those are what keep breaking:

- var-length = regex-dispatch + string expansion + union *around* the core
  (`GraphFrame.scala:618-674`) — broke when chained with other patterns, fixed in
  `fdfaa07` ("fix: allow chaining with fixed-length patterns (#771)", 2026-01-25);
- undirected = duplicate-the-plan-and-union with `_pattern`/`_direction` marker columns
  (`GraphFrame.scala:1501-1550`) — broke when mixed with directed edges, fixed in
  `0179298` ("fix: mixing directed and undirected edges in motif throws parse error
  (#754)", 2025-12-30), then again for fixed-length in `3270c22` (#781, 2026-01-27);
- negation = post-hoc `p.except(result)` set-difference *outside* the join machinery
  (`GraphFrame.scala:1653-1661`) — carries a live acknowledged defect (below).

**Their "we unified the executor" moment:** commit `024f939` ("Fix negation in motif
finding (#278)", 2018-07-02, fixing issue #276). The original design threaded scoping
state through an order-dependent recursion; a named vertex appearing *only* in a negated
term was mis-scoped. The fix did not patch the negation arm — it added a **normalization
pass before the fold** (augment the positive terms with a standalone `(v)` for every
vertex named only in negations, `GraphFrame.scala:679-685`, still citing issue #276), and
converted the recursion to an explicit fold (`findSimple`, diff in `024f939`). The same
commit also fixed **two silent-wrong-answer dispatch bugs hiding in the case arms**: a
`left_outer` join that should have been inner (unseen-destination edge case — dangling
edges kept rows with null vertices; diff hunk at old `GraphFrame.scala:828-841`), and a
**missing case**: `(a)-[e]->(a)` self-loops fell into the generic two-new-vertices arm
and joined two copies of the same name (fixed by adding the `srcName == dstName` arm, now
`GraphFrame.scala:1632-1642`). That is Gryphon's exact scar tissue — a many-armed
dispatch where one arm silently does the wrong join — observed in an independent
codebase, and fixed the same way Gryphon fixed single-hop: normalize first, collapse the
special case into the uniform machinery.

### Invariants (bottom-turtle Q3)

- **Structural / free:** read-only is inherited — DataFrames are immutable and motif
  finding cannot write; there is no write path to guard. Parameterization does not arise:
  the language carries **no user values at all** (no literals, no predicates), so
  injection is inexpressible in the motif surface.
- **One choke point at parse:** `assertValidPatterns` centralizes the language's
  well-formedness invariants — name reuse across vertex/edge namespaces rejected,
  duplicate edge names rejected, fully-anonymous terms rejected, named edges inside
  negation rejected — all loud `InvalidParseException`s
  (`patterns.scala:144-231`).
- **NOT centrally enforced — and it shows:** result-identity semantics. The undirected
  and var-length layers inject bookkeeping columns (`_pattern`, `_direction`, `_hop`)
  into the result frame (`GraphFrame.scala:1533-1550`, `660-670`), and the negation
  lowering compares **whole rows** via `except` — so bookkeeping columns participate in
  set-difference identity. The code says so itself: `// TODO: _pattern. _direction
  columns should be ignored if it is impacting` (`GraphFrame.scala:1657`) — an
  acknowledged latent wrong-result at the intersection of two features, sitting in
  HEAD. There is no single place that defines "what makes two result rows the same
  row," so every set-op wrapper re-decides it implicitly.

### Fail-closed (bottom-turtle Q4)

Parse-level: genuinely fail-closed and loud — unbounded var-length rejected
(`GraphFrame.scala:624-628`), hop 0 rejected (`patterns.scala:127`), the whole
`assertValidPatterns` battery above, and unparseable input raises
`InvalidParseException` with the original string (`patterns.scala:58-64`).

But the **string-rewrite layers are fail-open in shape**: every rewrite regex falls
through on non-match to `case original => original` (`patterns.scala:92-93`, `129-130`)
and *relies on the downstream grammar to reject what slipped past* — which it currently
does only because `*` is absent from the core grammar's name character class
(`patterns.scala:30, 34`). That is fail-closed **by lucky grammar, not by construction**;
a future grammar extension admitting `*` would convert missed rewrites into silent
misparses. The observed failures of this layer landed on the loud side — valid
*compositions* were wrongly rejected (#754, #771) rather than silently mis-answered — but
the 2018 `left_outer` bug and the live `_pattern`/`except` TODO show the silent class is
expressible in this architecture whenever a wrapper path owns its own semantics.

### The specific lowering questions

- **k-hop / fixed-length:** string-rewritten into an explicit chain of single-hop terms
  with synthesized mid-vertex names, then folded through the uniform join core
  (`patterns.scala:102-134`).
- **Variable-length:** `*min..max` expands to a **union of fixed-hop motifs**, one
  per hop count, each tagged with literal `_hop`/`_pattern`/`_direction` columns,
  `unionByName(allowMissingColumns = true)` (absent mid-vertex columns become nulls),
  then `orderBy("_hop", "_direction")` (`GraphFrame.scala:642-674`). No recursion, no
  recursive CTE analog; unbounded is rejected loudly. **This independently validates
  Gryphon's wishlist-E1 instinct** that bounded repetition can lower as a union of
  fixed-length chains at rung 1 — while warning (via #771/#781) that doing the
  expansion outside the core lowering breaks composition.
- **OPTIONAL MATCH analog:** none. The nearest shape is negation-via-`except`
  (`GraphFrame.scala:1653-1661`) and the 2018 lesson that outer-join-flavored arms in
  the incremental fold produce silent wrong answers (`024f939`'s left_outer→inner fix).
- **Aggregation:** not in the language; users aggregate the returned DataFrame. The
  COUNT-inflation trap is therefore **not expressible inside GraphFrames' language**
  — it is exported to the user, along with everything else.
- **Predicate placement:** *the most instructive contrast in the study.* GraphFrames
  **never carries a predicate**: filters are ordinary `df.filter(...)` applied after
  `find()` (`GraphFrame.scala:589-591`), and pushing them down into the join tree is
  Catalyst's job, not GraphFrames'. The predicate-drop bug class (Gryphon's
  envelope-WHERE scar) is **inexpressible in GraphFrames because the compiler never owns
  a predicate to drop.** The cost of that dodge: the language cannot express filtered
  traversal, the engine materializes the unfiltered match (pre-CBO), and safety-boundary
  use (accepting query text from a semi-trusted caller) is impossible since "the rest of
  the query" is arbitrary host-language DataFrame code. Gryphon's decision to own WHERE
  is what makes it a safe stored/embeddable query surface — the scar is the price of the
  boundary.
- **NULL / 3VL:** wholly delegated to Spark SQL. Joins on null `src`/`dst` simply don't
  match; there is no motif-level null logic at all. The one null fix in history is at a
  boundary: null vertex/edge ids crashed `toGraphX` and were converted to a loud
  `IllegalArgumentException` (`77c5599`, "Throw IllegalArgumentException for null
  IDs/Src/Dst in toGraphX (Fixes #765)", 2026-01-03).
- **Type handling:** ids are whatever type the user's DataFrame has; integral ids are
  cast to long, non-integral ids get a **generated surrogate long id** via
  `monotonically_increasing_id()` — which is recompute-unstable in Spark, so they pin it
  with `persist(StorageLevel.MEMORY_AND_DISK)` (`GraphFrame.scala:1053-1088`). A
  determinism hazard class (generated-identity instability) that Gryphon's substrate
  makes inexpressible — entity ids are database PKs.
- **Row-inflation defenses:** essentially **none by policy** — motif semantics are
  homomorphic ("names do *not* identify *distinct* elements", duplicates documented as
  the caller's problem with post-hoc `filter("a.id != c.id")`,
  `GraphFrame.scala:568-572`, `592-593`). Worse, multiplicity is *inconsistent across
  features*: positive motifs return duplicates, but adding a negated term routes results
  through `except` — Spark's EXCEPT DISTINCT — silently deduplicating the positive rows
  too (`GraphFrame.scala:1658`). For skew, `skewedJoin` splits hub keys into a broadcast
  join (`GraphFrame.scala:1151-1171`) — a performance defense, not a correctness one.
- **Determinism / ordering:** patchwork. Column order was made deterministic in 2016
  (`b78301f`, "motif search result DataFrame columns in order"); union results get
  `orderBy("_direction")` / `orderBy("_hop", "_direction")` sprinkles
  (`GraphFrame.scala:1424`, `673`) — which order groups but not rows within groups;
  anonymous-edge temp column names come from a `Random` deliberately seeded with the
  class-name hash for reproducibility (`GraphFrame.scala:1414`, `1648`). No systematic
  captured-artifact determinism discipline like Gryphon's sorted `pk__in`
  (`req-grid-traversal-exec-sql-capture-3`).

### ★ Transferable to Gryphon

1. **Desugar on the AST at one normalization choke point — never on text, never inside a
   wrapper path.** Their uniform core never breaks; their rewrite layers break every few
   months (#754, #771, #781, #728). The `024f939` pattern — pre-fold normalization made
   the scoping bug structurally unreachable — is the same medicine as Gryphon's
   single-hop collapse, applied one layer earlier.
2. **Binding-state-driven uniform lowering scales.** One case-match keyed on "is this
   variable already bound" carried ten years of feature growth. Gryphon's chain
   machinery (`_build_chain_queryset` + `_apply_predicate_to_qs`) is the same idea; the
   peer evidence says *push more shapes through it*, not fewer.
3. **Define result-row identity once, structurally.** Their `_pattern`/`except` TODO is
   what happens when each set-op wrapper implicitly re-decides row identity. Gryphon's
   envelope keys (`_node_key`/`_edge_key`, `executor.py:434-450`) are the right seed —
   the opportunity is making *every* merge/dedup/set-op path consume that one identity.
4. **Feature-composition is where bolt-on architectures die.** Every 2025-26 motif fix is
   a pairwise composition (var-length×chain, directed×undirected, undirected×fixed).
   Test-side and structure-side consequences below.

---

## Lens T — Testing

- **Oracle model:** hand-authored expected sets, no independent reference implementation
  for motif finding. Assertions are answer-based — `collect().toSet` compared against
  literal expected sets via a `compareResultToExpected` helper that prints both
  directions of the set diff (`core/src/test/scala/org/graphframes/
  PatternMatchSuite.scala:72-87`, 875 lines of such tests). Self-consistent, exactly the
  trap Gryphon's ladder is built against.
- **One genuinely independent oracle exists — for algorithms, not motifs:** the LDBC
  Graphalytics suite downloads reference datasets *with published expected outputs*
  (BFS distances etc.) and diffs against them
  (`core/src/test/scala/org/graphframes/ldbc/TestLDBCCases.scala:70-90`; added in
  `45f9d8c`, "feat: add LDBC tests (#570)"). Better still, it runs **differentially
  across two in-house implementations** — `Seq("graphframes", "graphx").foreach { algo
  => ... }` (`TestLDBCCases.scala:90`) — the same algorithm computed by the DataFrame
  engine and the GraphX engine against one expected answer. That is Gryphon's
  model-oracle idea, independently reinvented for the algorithm layer.
- **A mini-metamorphic gem:** the negation tests derive the expected answer from a
  relational identity rather than by hand — the complement-edge set is computed as
  `crossJoin(all pairs).except(edges)` and negation motifs are checked against it
  (`PatternMatchSuite.scala:58-62`). An oracle from an algebraic identity, in the
  fixture.
- **Fuzzing / generation / shrinking:** none. No ScalaCheck/Hypothesis anywhere
  (`grep -rn scalacheck build.sbt project/` → empty; no `hypothesis` in `python/`). The
  CC wrong-result bug #208 was shrunk **by hand by the reporter** — the fix commit
  quotes "it appears to be minimal, after trying to shrink the test case manualy"
  (`5faffc5`, 2017-06-13). A ten-year-old codebase whose hardest wrong-result bug was
  minimized by a user by hand is the strongest argument in this dossier for Gryphon's
  seeded fuzzer + replay discipline.
- **Corpus/coverage/TCK/mutation:** no TCK (own DSL, not Cypher), no coverage gate on
  lowering paths, no mutation testing. The AGENTS.md testing doctrine is regression
  conservatism ("NEVER change existing test assertions", `AGENTS.md:9-16`), not
  correctness hunting.
- **Answer-vs-artifact posture:** tests check answers (good). But the *production code*
  contains a proxy-artifact false-green of its own: ConnectedComponents detected
  convergence by comparing the **sum of min-neighbor ids** across rounds — a checksum
  proxy that silently overflowed/nulled on big graphs; fixed by moving the sum to
  `DecimalType(20,0)` and throwing `ArithmeticException` when it still nulls
  (`107eebe`, "Fix connected component (#454)", 2024-06-20; see `_calcMinNbrSum` in the
  diff). "Check the answer, not the artifact" applies to convergence signals too.

**★ Transferable to Gryphon:** almost nothing to import — Gryphon's ladder strictly
dominates this one (model oracle, fuzzer, TLP, snapshot+SQL capture, branch gates). The
two live imports: (a) the *composition* emphasis — their entire recent bug stream is
pairwise feature interaction, and Gryphon's fuzzer/coverage ledger does not currently
guarantee pairwise-composition coverage; (b) the fixture-level algebraic-identity oracle
(complement-graph trick) as a cheap pattern for negation-flavored scenarios
(`NOT EXISTS`).

---

## Lens H — History

**Scale:** 627 commits, 2015-11 → 2026-06; two eras — Databricks origin (Hunter 126,
Meng 109, Bradley 101+7) and the 2024+ revival (Sem 100, Goun Na 9, James Willis 12)
(`git shortlog -sn HEAD`). Correctness-relevant grep stream: 176 commits match the
fix/bug/wrong/null/dedup filter (`git log --regexp-ignore-case -E --grep=...`).

### Bug taxonomy (class → count → representative anchors)

| Class | Count (read) | Representatives | Note |
| --- | :---: | --- | --- |
| **Desugar/rewrite-layer composition breaks** | 4 in ~4 months | `0179298` (#754 directed×undirected), `fdfaa07` (#771 var-length×chain), `3270c22` (#781 undirected×fixed), `f5de10f` (#728 var-length result formatting) | The hottest current cluster; all in the text-rewrite/wrapper layers, none in the uniform core |
| **Pattern scoping / dispatch-arm wrong-join** | 3 (one commit) | `024f939` + `4fd2401` (#276/#278/#279): negated-only vertex mis-scope; `left_outer`→inner silent wrong rows; missing self-loop arm | The 2018 reckoning; fixed by pre-fold normalization + new case arm |
| **Algorithm identity/boundary wrong-results** | 3 | `5faffc5` (#212/#208 CC small-star min-nbr exclusion), `12ad0c8` (#802 kcore swapped sendMsgToSrc/sendMsgToDst), `b18b35f` (#320 CC label semantics → min of original id) | Column-swap and boundary-condition classes in iterative algorithms |
| **Proxy-signal false-green in production** | 1 | `107eebe` (#454 CC sum-based convergence overflow → Decimal + loud throw) | An engine trusting a checksum artifact |
| **Null/id boundary crashes → loud errors** | 1 | `77c5599` (#765/#766 null ids in toGraphX) | Crash converted to typed rejection |
| **Resource/perf regressions & leaks** | 3 | `8a719fb` (#552 CC memory leak), `d72ef0f` (#687 GraphX leaks), `afea945` (#772 revert CC to 0.9.3 after perf regression) | Includes a full **rewrite-regretted revert** |
| **Determinism/presentation** | 2 | `b78301f` (2016 column order), `f5de10f` (#728) | Ordering as an afterthought, patched when noticed |

### Turning points

- `aa78d0b` (2015-11-28): result schema flat → **nested StructType per name** — the
  column-name collision problem solved structurally, once, at the start.
- `024f939` (2018-07-02): the unification/normalization refactor described in Lens E —
  their closest analog to Gryphon's single-hop collapse.
- `c352149`/`d72ef0f` (2025): vendored GraphX in-tree (`feat: initial commit with a copy
  of GraphX code (#680)`) as Spark deprecates GraphX — the dual-engine differential in
  LDBC tests is a side-benefit.
- `afea945` (2026-01-14): **revert of a rewritten ConnectedComponents to the 0.9.3
  version** for a perf regression (#772) — a rewrite regretted in public, and a caution
  for "improve by rewrite" instincts without a differential net. (Gryphon's collapse had
  351 pinned answers + the model oracle as its net; this revert is what the move looks
  like without one.)

### Design-doc / RFC trail

Thin. Reasoning lives in PR descriptions (e.g. `024f939`'s four-step algorithm sketch)
and scaladoc, not specs. The revival era added `AGENTS.md` — an AI-agent operating doctrine
whose center is regression conservatism (`AGENTS.md:5-28`) — but no semantics spec; motif
semantics (homomorphism, duplicate rows) are documented only in the `find()` scaladoc
(`GraphFrame.scala:568-593`).

### ★ Predicted Gryphon hotspots (mapped)

1. **Feature-pair composition seams** — the dominant peer class maps directly onto
   Gryphon's bolt-on paths: `OPTIONAL MATCH` × WHERE-scoping, `NOT EXISTS` × multi-hop,
   bounded repetition × far-node WHERE, multi-`MATCH` union × ORDER/LIMIT. Peer history
   says the next Gryphon bug is likelier at a pairwise seam than inside chain lowering.
2. **Set-op wrappers re-deciding row identity** — their `except`/`_pattern` TODO
   predicts bugs wherever Gryphon merges or subtracts result sets outside the chain
   (`_merge_envelopes`, `_apply_not_exists`, OPTIONAL MATCH scoreboard).
3. **Missing dispatch arm for degenerate shapes** — their self-loop bug predicts the
   same for Gryphon: patterns where two variables bind the same entity
   (`(a)-[e]->(a)`), zero-length chains, repeated variables across MATCH clauses.
4. **Credits (classes our architecture forecloses):** predicate-drop is *their*
   inexpressible class, not ours — but our typed lane forecloses their id-cast/surrogate
   nondeterminism class (DB PKs, no `monotonically_increasing_id` analog); read-only
   forecloses the entire iterative-algorithm-state family (CC/kcore/Pregel bugs — over
   half their wrong-result history); and deterministic SQL capture already exceeds
   their ordering patchwork.

---

## Net read

The biggest thing to steal is negative-space evidence for a positive rule: GraphFrames'
uniform, binding-state-driven lowering core went essentially untouched for ten years
while every feature implemented as a rewrite layer or set-op wrapper *around* that core
(var-length string expansion, undirected union-doubling, negation-via-except) produced
the entire modern bug stream — so Gryphon should collapse its remaining bolt-on paths
into the chain machinery and do all desugaring as AST→AST normalization at one choke
point, never below the AST and never inside a wrapper. The biggest thing to avoid is
GraphFrames' predicate dodge: it escapes the predicate-drop class by not owning WHERE at
all, which forfeits exactly the safe-embeddable-query-boundary property Gryphon exists to
provide — the scar class is the price of the boundary, and the model oracle is the right
payment. One credit: Gryphon's ladder (independent model oracle, seeded fuzzer with
replay, TLP, deterministic SQL capture) strictly dominates GraphFrames' testing — their
hardest wrong-result bug was hand-shrunk by a user (#208/`5faffc5`), their convergence
check false-greened on a checksum artifact (#454/`107eebe`), and their read-write
iterative algorithm layer, source of over half their correctness history, is a bug
family Gryphon's read-only bet makes inexpressible.
