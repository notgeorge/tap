# Dossier — DuckPGQ (clone `84a8f054ef02beab8593bbc2b00a0e1e9e68a0e2`, cloned 2026-07-04, license MIT)

> Study artifact of `doc-gryphon-comparative-eval-protocol.md` (§4.4 template). All file:line
> anchors are against the clone SHA above in `undefined/duckpgq/`. IP posture: ideas mined,
> zero code copied (protocol §6). HEAD commit date 2026-03-02; first commit 2023-02-02.

## Snapshot

DuckPGQ implements **SQL/PGQ (SQL:2023 property-graph queries)** as a DuckDB extension. Its
bet is the purest form of the lowering thesis Gryphon follows: a `GRAPH_TABLE (... MATCH ...)`
clause is expanded — at **parse/bind time, as an AST→AST macro** — into an ordinary SQL
subquery (`SubqueryRef` of a `SelectNode`: cross joins + one big WHERE conjunction), which the
host's binder, optimizer, and vectorized executor then treat as any other SQL
(`src/core/functions/table/match.cpp:950-1076`, `MatchBindReplace`). Only *quantified* paths
(`{1,3}`, `ANY SHORTEST`) escape the relational lane, into an on-the-fly compressed-sparse-row
(CSR) adjacency structure plus scalar path UDFs (`iterativelength`, `shortestpath`) spliced
into the same plan (`match.cpp:652-695`, `src/core/functions/scalar/csr_creation.cpp`,
`src/core/functions/scalar/iterativelength.cpp`). The design-doc trail is unusually good: the
CIDR 2023 paper states the thesis explicitly — build graph querying *on* state-of-the-art
relational technology, "minimizing technical debt" by reusing the host's optimizer, type
system, and executor (ten Wolde, Singh, Szárnyas, Boncz, *DuckPGQ: Efficient Property Graph
Queries in an Analytical RDBMS*, CIDR 2023, https://www.cidrdb.org/cidr2023/papers/p66-wolde.pdf;
also PVLDB 16(12) demo, *DuckPGQ: Bringing SQL/PGQ to DuckDB*).

Inclusion score (§2.2): **deep — core**. Relational-lowering relevance: maximal (it *is* a
graph→SQL transpiler). Source readability: high (one 1,085-line lowering file). History
richness: 1,468 commits, 172 issues (26 open), live tracker. Semantics documentation: partial
(papers yes; NULL/type semantics implicitly "SQL's," which is itself a data point).

Scale/ownership caveat for everything below: this is a ~1.2-FTE project — `git shortlog -sn`:
dtenwolde 1,060 + 109 + 4 (author aliases), Sam Ansmink 196 (mostly extension-template/CI),
everyone else ≤19. Single-maintainer scar tissue, but the *classes* transfer.

## Lens E — Execution ★ PRIMARY

### Pipeline shape / IR count — the bottom-turtle question 1

**DuckPGQ has zero logical-plan IR of its own.** The pipeline is: host parser (a *patched
DuckDB fork*, `cwida/duckdb-pgq` — `.gitmodules:1-3` — carrying the PGQ grammar, producing
`MatchExpression`/`SubPath` parse nodes) → a parser-extension hook that walks the statement
tree hunting for `duckpgq_match` table-function refs and stashes each `MatchExpression` in
per-connection state under an integer index (`src/core/parser/duckpgq_parser.cpp:38-61`) → a
**bind-replace** that expands the stashed expression into a plain SQL parse tree
(`match.cpp:950-1076`) → DuckDB's own binder → DuckDB's own logical plan/optimizer → vectorized
execution. The logical IR exists — **it just belongs to the host.** DuckPGQ is a macro
preprocessor over someone else's compiler.

What that buys them, and where it stops, is the sharpest lesson in this dossier:

- **Inside the delegation zone** (fixed-length patterns → joins), correctness is inherited.
  Name resolution, type checking, NULL logic, predicate pushdown, join ordering — all enforced
  once, by the host binder/optimizer, for every query shape. There is no per-path re-assertion
  because there are no paths: one artifact, one binder. Their issue tracker shows essentially
  **no wrong-results bugs in the fixed-length relational lane** — the lane's bugs are binder-
  level scoping/naming (see Lens H taxonomy), which fail *loud* (BinderException), not silent.
- **Outside the delegation zone**, bugs concentrate. Three exits from the guarded zone, three
  bug clusters: (a) the *entry interception layer* — hand-rolled `dynamic_cast` walks over
  statement shapes (`duckpgq_parser.cpp:38-61,133-178`), where every unanticipated shape
  (MATCH inside CTE #129/#85/#276, inside a subquery #199, under EXPLAIN #7, under COPY #66,
  Python env #100) historically **segfaulted**; (b) the *side-state* (`duckpgq_state.hpp:28-38`:
  `transform_expression` map keyed by a monotonic `match_index`, `registered_property_graphs`,
  a global `csr_list`) — property graphs vanishing across connections (#209), prepared
  statements still unsupported (#75, open); (c) the *UDF escape lane* — where SQL's semantics
  no longer carry the query's meaning, and the extension must re-earn correctness by hand
  (next section).

**Verdict for Gryphon's bottom turtle:** a thin transpiler with no logical IR is *fine* —
provided (1) the target representation is itself semantically complete and guarded by a binder
that fail-closes on nonsense, and (2) the query's *entire meaning* stays inside the target's
native vocabulary. Gryphon's rung-1 ORM lowering satisfies (1): Django ORM + Postgres are
Gryphon's "host binder." The risk lives exactly where Gryphon violates (2): every place the
executor does Python-side semantics — `_merge_envelopes`, `_compute_rows`, the `OPTIONAL
MATCH` scoreboard, `NOT EXISTS` assembly (`tap_grid/gryphon/executor.py:536,2394,2835,1926`)
— is Gryphon's equivalent of DuckPGQ's CSR/UDF lane, the unguarded zone where their bugs
actually lived. An IR is not the medicine; **shrinking the out-of-vocabulary zone is.**

### Join & traversal lowering

- **Fixed k-hop:** `ProcessPathList` walks the pattern as (vertex, edge, vertex) triples and
  appends equality join conditions per hop into one `conditions` vector; every referenced
  table lands in an alias map, then all tables are emitted as CROSS JOINs and all conditions
  as a single WHERE conjunction (`match.cpp:774-867` walk; `972-983` FROM assembly; `1069`
  `CreateWhereClause`). Join *ordering* is entirely the host optimizer's problem — the
  extension emits the naive cross-product form on purpose. That is the CIDR-paper bet in one
  line of code.
- **Edge direction is a 4-way switch** (`AddEdgeJoins`, `match.cpp:589-620`): RIGHT/LEFT swap
  src/dst equalities; ANY (undirected) rewrites the edge table into
  `(SELECT src,dst,* UNION ALL SELECT dst,src,*)` (`EdgeTypeAny`, `match.cpp:258-319`);
  LEFT_RIGHT doubles the edge alias (`match.cpp:343-371`). Note the per-path asymmetry:
  LEFT/RIGHT call `CheckEdgeTableConstraints` (`match.cpp:325,336`), ANY does not — issue #47
  ("Check table constraints on any edge type", closed 2024-08-15) asked exactly this, and at
  HEAD `EdgeTypeAny` still carries no such call. A validation re-asserted per path, forgotten
  on one path: the textbook shape of Gryphon's own envelope-WHERE scar.
- **Variable-length / shortest path:** the escape lane. A quantified segment adds (i) a CTE
  `cte1` that builds a CSR via scalar UDF calls (`CreateDirectedCSRCTE` /
  `CreateUndirectedCSRCTE`, `src/core/utils/compressed_sparse_row.cpp`), (ii) a cross-joined
  `(SELECT count(cte1.temp)*0 AS temp FROM cte1) __x` subquery whose only purpose is to
  **force CSR materialization before the path UDF runs** (`CreateCountCTESubquery`,
  `match.cpp:227-256` — a sequencing hack encoded as arithmetic), and (iii) a WHERE condition
  `__x.temp + iterativelength(0, count, a.rowid, b.rowid) BETWEEN lower AND upper`
  (`AddPathQuantifierCondition`, `match.cpp:622-650`). The CSR id is **hardcoded to 0**
  (`match.cpp:406,627`) and the CTEs are create-once-per-query (`match.cpp:496,659-673`) — a
  second quantified segment over a *different* edge table would silently reuse the first
  segment's CSR (hazard by inspection at HEAD; no issue filed that we found).
- **OPTIONAL MATCH / aggregation:** neither exists inside the extension. SQL/PGQ's
  `GRAPH_TABLE` returns a table; optionality is an outer `LEFT JOIN`, aggregation an outer
  `GROUP BY` — both in plain SQL, handled by the host (the `COLUMNS` list is passed through
  into the subquery select list, `match.cpp:993-1067`). The *surface choice* deleted two
  whole executor subsystems that Gryphon hand-implements.

### Predicate placement [anchor]

There is **one predicate sink**. Element-local WHEREs (a `SubPath` wrapper's `where_clause`),
join conditions, inheritance/discriminator conditions, and the query-level WHERE all get
appended to the same `conditions` vector and folded by `CreateWhereClause` into a single
conjunction on the final SelectNode (`match.cpp:783-785,809-811,826-828` element WHEREs;
`985-987` query WHERE; `1069` the fold). Placement/pushdown is then the host optimizer's job.
Structurally, in the relational lane, "a path accepted a WHERE and ignored it" is nearly
inexpressible — there is no per-path WHERE handling to forget.

*Nearly.* The documented mis-scope bug lives at the seam where the sink meets the escape
lane: **issue #94** — `(a:Person WHERE a.name='Daniel')-[k:knows]->{2,3}(b)` computed with
bounds **{1,1}**, because wrapping the vertex in a WHERE turns the `PathElement` into a
`SubPath`, and the bounds-reading code picked them off the wrong AST node ("The lower and
upper bounds are 1 & 1 because the previous element pattern is seen as a Subpath because of
the filter" — issue #94 body, closed). Same disease as Gryphon's envelope-WHERE defect: the
*same intent* takes a different structural route depending on an incidental authoring choice
(here: presence of a WHERE), and one route mishandles it. A sibling: commit `0973422`
("Bug seems related to whether column in edge pattern is projected") — undirected-edge results
changed with whether an edge column appeared in the projection.

### NULL / 3VL lowering [anchor]

**None — deliberately.** User predicates pass through verbatim into the emitted SQL WHERE
(`match.cpp:985-987`); NULL comparison semantics are DuckDB's SQL 3VL, untranslated. Because
the query surface is SQL/PGQ — SQL itself — **there is no Cypher-3VL-vs-SQL-3VL impedance
mismatch to translate across.** They deleted the null-boundary bug class by choosing a surface
whose semantics equal the target's. Gryphon cannot fully take this road (Cypher-familiar
surface is a product choice) but has already done the next-best thing: *pin* its own
2VL-literal/3VL-field boundary in spec + oracle (`doc-dev-gryphon-vs-cypher.md` Ledger B).
Credit, and a confirmation the boundary must stay pinned rather than "fixed toward Cypher."

### Type handling [anchor]

Delegated to the host binder — SQL coercion rules apply; the extension performs no typing of
its own. Its only own-layer gates are name-level: labels must be registered
(`FindGraphTable`, `match.cpp:121-130`), properties must be registered — `CheckColumnBinding`
walks every column ref in the COLUMNS list against the property graph's registered columns and
throws `BinderException("Property %s is never registered!")` (`match.cpp:907-948`), a
fail-closed gate hardened after star-expression/undefined-property bugs (#191/#193/#198 trail,
commit `4736dcf`, `8c6091c`). Contrast: Gryphon *rejects* cross-type predicates
(schema-as-oracle, `req-grid-traversal-lang-type-strictness`) where DuckPGQ inherits SQL
coercion. On peers' evidence (AGE's agtype cast crashes; SQL's silent coercions), Gryphon's
rejection posture is a credit, not a gap.

### Row-inflation defenses [anchor]

**None added; SQL multiset semantics accepted and pinned.** The undirected rewrite (UNION ALL
of both directions) means a reciprocal pair (`(0,3)` and `(3,0)`) yields the same neighbor
twice, and the test *asserts the duplicate as expected* — including a hand-written plain-SQL
twin query returning the same 5 rows (`test/sql/pattern_matching/undirected_edges.test:24-38`,
"Daniel has 3 outgoing edges and 2 incoming edges, so there should be 5 tuples", `Peter`
twice). Meanwhile the CSR lane **rejects** the analogous dirtiness: non-unique/non-existent
vertices throw `ConstraintException` at CSR build (`csr_creation.cpp:121-124`; issue #139,
which had previously surfaced as `INTERNAL Error` — `test/sql/path_finding/non-unique-vertices.test`).
Same data, two lanes, two different answers (duplicates-as-semantics vs hard reject) —
documented *within one test file*. Lesson for Gryphon's rung-4 future: define one row-identity
discipline that both the ORM lane and any raw-SQL lane obey, before the second lane exists.

### Determinism / ordering [anchor]

Nothing extension-side; inherits SQL. Tests impose `ORDER BY` to stabilize themselves
(`undirected_edges.test:28`); unordered results are engine-order. No NULLS placement policy,
no LIMIT-without-ORDER story. Gryphon's deterministic SQL capture (sorted `pk__in`,
`req-grid-traversal-exec-sql-capture-3`) and pinned NULLS ordering are ahead here — credit.

### ★ Transferable to Gryphon

1. **One predicate sink, one artifact** (structural). The relational lane's silence-proofness
   comes from a single conjunction sink + a single emitted artifact per MATCH, with all
   scoping enforced once downstream. Gryphon's analog: route *every* dispatch path's predicate
   application through the one `_apply_predicate_to_qs`/chain seam, and treat "a path that
   receives a `where_clause` it does not forward to the sink" as structurally impossible —
   extending the single-hop collapse to the scan and advanced paths.
2. **Escape lanes are where semantics rot** (predictive). Their wrong-results/crash record
   is concentrated where they left SQL (CSR+UDF): #94, #139, #67, #46, #206, #18. Budget
   Gryphon's rung-4 (`WITH RECURSIVE`) work accordingly: oracle-first, semantics pinned in
   spec before lowering exists.
3. **Delete subsystems by delegation.** Their OPTIONAL/aggregation story is "compose in SQL."
   Gryphon's `OPTIONAL MATCH`/`NOT EXISTS`/aggregation Python paths should, wherever the ORM
   can express the combinator (`Exists`, `Subquery`, LEFT JOIN via `filter(Q|isnull)`,
   `Count(filter=Q)`), become queryset combinators on the chain artifact rather than
   Python-side row assembly.

## Lens T — Testing (lighter, per protocol — hunting only what Gryphon lacks)

- **Oracle model:** none. The suite is DuckDB **sqllogictest** files (~62 under `test/sql/`)
  asserting literal result rows — self-consistent assertions, no independent reference
  implementation, no differential/metamorphic anything, no fuzzing, no shrinking, no TCK
  analog (SQL/PGQ has no public TCK). `test/python/duckpgq_test.py` and
  `test/nodejs/duckpgq_test.js` are client smoke tests.
- **Answer-vs-artifact posture:** they do assert answers (result rows), which is right; the
  one genuinely mineable micro-pattern is the **hand-written SQL twin**: a plain-SQL
  formulation of the same question asserted alongside the GRAPH_TABLE form
  (`undirected_edges.test:24-33`) — a poor man's differential. Gryphon's model oracle strictly
  dominates this; no import needed (reject-with-reason: duplicate of a stronger rung).
- **The negative exhibit — known-suspect semantics shipping for years:** issue **#67** (open):
  "Test if bounded path lengths get correct results." The maintainer *documents* that
  `->{2,3}` lowers to `iterativelength(...) BETWEEN 2 AND 3` where `iterativelength` computes
  the **shortest** path length — so a pair with a length-1 shortest path *and* a valid
  length-2 path is wrongly dropped ("if the shortest path is 1 … that result should then be
  returned … However, since the shortest path was found to be 1 … it is left out"). The issue
  asks someone to *build a toy graph to verify*. That is what the absence of a reference
  oracle looks like from the inside: a suspected wrong-answer class, named, undisproven, open
  across releases. Gryphon's ladder (model oracle + fuzzer + TLP) exists precisely so this
  state is unrepresentable — strongest possible external validation of the ladder investment.
- **Host verification disabled:** DuckDB's own `pragma enable_verification` is commented out
  across the suite (`grep -rn enable_verification test/sql` — e.g. `undirected_edges.test:6`)
  because it segfaulted the extension (issue #18). When a borrowed correctness harness fights
  the extension, the extension turns it off — the exact anti-pattern Gryphon's "the harness is
  first-class" posture forbids.
- **Regression capture:** decent — issues do land as `.test` files named for them
  (`211_using_other_schemas.test`, `create_pg/209_property_undefined.test`,
  `csr_segfault.test`, `wcc_segfault.test`, `non-unique-vertices.test`).
- **★ Transferable to Gryphon:** (a) the #67 bug *class* — "quantifier lowered as
  shortest-path-in-range instead of exists-path-in-range" — belongs in Gryphon's corpus and
  fuzzer *now*, since Gryphon ships bounded repetition `*1..3` while the model oracle still
  skips bounded multi-hop (`doc-gryphon-testing-philosophy.md §8`, OracleUnmodeled list); (b)
  generator coverage: make the fuzzer emit WHERE-on-quantified-endpoint shapes (the #94
  killer combination: anchor predicate × bounded hop).

## Lens H — History (archaeology)

**Scale:** 1,468 commits, 2023-02-02 → 2026-03-02 (HEAD); 172 issues (26 open); effectively
one core developer (dtenwolde ~1,173 commits across aliases) plus template/CI support
(Sam Ansmink 196) and drive-by fixers (dentiny 19 — notably the binder-hardening cluster).

**Bug taxonomy** (clustered from the 232-commit fix stream — `git log --grep` per protocol —
and the issue tracker; counts are issues+distinct fix commits per class):

| Class | ~Count | Representative anchors | Shape |
| --- | :---: | --- | --- |
| Host-integration crashes: MATCH in an unanticipated statement shape (CTE, subquery, EXPLAIN, COPY, client env) | ~12 | #276, #199, #129, #85, #7, #100, #54, #40, #66, #96; fix `7f843af` ("Fixing segfaults happening when using CTE nodes"); open: #205 (R), #210 (`query()` fn) | Manual `dynamic_cast` statement-walk (`duckpgq_parser.cpp:38-61`); every new shape hand-added after a segfault report |
| Binder/registry scoping & naming: unregistered property, star expansion, case-sensitivity, alias vs table name, schema qualification, stale registry | ~12 | #228 (`264a718`), #211 (`9dafb86`), #209 (`3a50d83` — properties lost across connections), #176, #188 (`18e7e46`), #154 (`c0b6715` — label used where table name needed), #50, #44, #95; `05c818f` (missing alias for EdgeTypeAny), #60/#109 (duplicate table index) | The extension's *own* name/state layer — the part the host binder can't guard |
| Path-finding (CSR/UDF) semantics & crashes | ~11 | **#94** (bounds mis-read as {1,1} under WHERE), **#139** (`csr_creation.cpp:121-124` fix), **#67 (open, suspected wrong results)**, #46 (`fe67791`), #81, #206 (`1bce4d9`), #200, #18, #49, #107 | The escape lane: correctness re-earned by hand, sometimes not yet earned |
| Shape-dependent behavior (result changes with projection/authoring form) | ~3 | `0973422` (undirected results depend on whether edge column projected), #94 again, #228 | The intent≠path class, in their costume |
| Host-fork maintenance churn | recurring | `.gitmodules:1-3` (`cwida/duckdb-pgq` fork); commits `4550587`/`aec2e25`/`ccaaf94`/`57e7523` ("Merge with v1.3.0, fix parser errors"…); `docs/UPDATING.md` ("This API is not guaranteed to be stable") | Not bugs but a permanent tax: every DuckDB release = re-merge the grammar fork + chase C++ API breaks |

**Turning-point commits/PRs:** no "we unified the executor" rewrite exists — the relational
lane was born unified (single-artifact expansion) and stayed so; the notable hardening arcs
are instead (a) the binder-gate arc (`CheckColumnBinding` + star-expression fixes,
`4736dcf`→`264a718`, issues #191/#193/#198/#228), i.e. *adding* fail-closed checks at the one
choke point, and (b) the crash-to-error arc (`ce43b5d` "Throw error when creating property
graph on view instead of segfault"; `csr_creation.cpp` ConstraintException replacing an
INTERNAL error) — converting fail-open crashes into loud refusals, one report at a time.

**Design-doc/RFC trail:** the CIDR 2023 paper (architecture thesis + CSR/UDF design) and
PVLDB 16(12) demo are the design docs; issues serve as the reasoning log (#67 is a
maintainer-authored semantic doubt written in the open — rare and valuable).

**Lifecycle lesson:** living inside someone else's parser required forking it
(`cwida/duckdb-pgq`) — the grammar could not be a true extension — and the project has paid a
visible re-merge tax at every host release since (`UPDATING.md`; the "Merge with vX.Y" commit
stream). The inheritance dividend (optimizer, executor, 3VL, types — all free) is real and
huge; the rent is perpetual.

**★ Predicted Gryphon hotspots** (from their bleeding, mapped): (1) *quantifier × predicate
interaction* — WHERE on a bounded-repetition endpoint changing how bounds/predicates scope
(#94's class; Gryphon's `*1..3` is live and oracle-unmodeled — this is the top predicted
next bug site); (2) *the Python-side assembly zone* (`_compute_rows`, `_merge_envelopes`,
OPTIONAL scoreboard) as the analog of their CSR lane — expect wrong-results class there, not
in the ORM-lowered lane; (3) *registry/state drift* has no Gryphon analog (stateless per
query, schema from the live registry) — **credit**; (4) *host-shape crashes* have no analog
(Gryphon owns its grammar; nothing intercepts another parser) — **credit**; (5) all
write-path bugs — none observed here either (PGQ is read-only DQL as implemented; property
graph DDL registry bugs are their closest analog and Gryphon's typed service layer forecloses
that shape) — **credit**.

## Net read

The biggest thing to steal is structural, and it validates the direction Gryphon already
chose with the single-hop collapse: **DuckPGQ's fixed-length lane has essentially no silent
wrong-answer history because every pattern shape lowers to one artifact with one predicate
sink, and one downstream binder enforces all invariants once** — the medicine Gryphon should
now apply to its remaining scan/advanced/OPTIONAL/NOT-EXISTS dispatch, shrinking the
Python-side semantics zone to (ideally) nothing the ORM can express. The biggest thing to
avoid is their escape lane's epistemic state: a variable-length implementation whose core
semantic ("shortest length in range" vs "exists path in range", #67) is *suspected wrong,
in writing, for years*, because no independent oracle exists to settle it — Gryphon must
extend the model oracle over bounded repetition *before* rung-4 lowering work, not after.
One credit to bank: Gryphon's owned grammar, stateless execution, typed-lane rejection, and
read-only construction structurally foreclose four of their five bug classes; the entire
comparative surface reduces to the one class both share — shape-dependent mis-scoping at
dispatch seams — which is exactly where the study should keep drilling.
