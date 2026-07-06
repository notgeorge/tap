---
spec: ../../tap_grid/specs/spec-grid-traversal-language.md
audience: [llm, developer]
covers:
  - doc-dev-gryphon-wishlist.md
  - doc-dev-gryphon-vs-cypher.md
  - ../../tap_grid/specs/spec-grid-traversal-language.md
assumes:
  - Reader knows Gryphon (Cypher-subset → ORM→SQL, read-only) and the demand-shape wishlist buckets
  - This is an EVIDENCE note — it measures external Cypher demand and contrasts it with Gryphon's shipped surface; it does not change any requirement
provides: |
  A numbers-first breakdown of which Cypher features real open-source graph
  applications actually hard-code in their queries, mined across 13 corpora
  (565 app-focused read queries; 1295 with the two library corpora included),
  cross-referenced against what Gryphon supports today. The point is to let
  wishlist sequencing be set by measured demand rather than by Cypher's table
  of contents or by intuition. Includes the apoc/GDS skew caveat, the
  non-obvious findings (COLLECT ≫ numeric aggregates; UNWIND's signal has
  arrived; CALL is library-inflated), and one live doc-drift flag.
---

# Gryphon Feature Demand — What Real Cypher Corpora Actually Use

> "I want to see some numbers first." — George
>
> This is the numbers. It measures the **demand side** (what features real Cypher-writing
> applications reach for) and lays it against the **supply side** (what Gryphon lowers today),
> so the wishlist's `extract-ahead` / `wait-for-signal` calls rest on evidence, not vibes.

## 0. TL;DR — the ranked gap

Sorted by demand among **application** corpora (excludes the two library corpora — see §4 for why),
showing only features Gryphon does **not** fully ship today:

| Rank | Feature | App-corpus demand | Breadth | Gryphon status | Wishlist |
| :--: | --- | :--: | :--: | :--: | :--: |
| 1 | **`WITH`** (pipeline / post-aggregate filter) | **19.5%** | 10/11 repos | ❌ not in grammar | **F1 ★** |
| 2 | **`COLLECT`** | **14.9%** | 10/11 repos | ❌ not in grammar | **C2** |
| 3 | **var-length path** `-[*n..m]-` | **14.5%** | 7/11 repos | ⚠ parses, executor **rejects** | **E1** |
| 4 | **`DISTINCT`** | **12.2%** | 7/11 repos | ❌ not in grammar | **A4** |
| 5 | arithmetic in expressions (`a.x + b.y`) | 10.4% | 10/11 repos | ❌ not built | — (no bucket) |
| 6 | `coalesce()` | 8.7% | 5/11 repos | ❌ not in grammar | H1 |
| 7 | `labels()` / `type()` / `keys()` | 6.7% | 7/11 repos | ❌ not built | — |
| 8 | string fns (`toLower`, `substring`, …) | 6.0% | 5/11 repos | ❌ not built | H2 |
| 9 | **`shortestPath`** | 5.8% | 5/11 repos | ❌ not in grammar | E3 |
| 10 | list ops / comprehensions | 5.0% | 9/11 repos | ❌ not built | — (deliberate subset) |
| 11 | `size()` | 5.0% | 8/11 repos | ❌ not built | H2 |
| 12 | **`UNWIND`** | 4.8% | 7/11 repos | ❌ not in grammar | F3 |
| 13 | `SKIP` / `OFFSET` | 3.4% | 2/11 repos | ❌ not in grammar | A3 |
| 14 | numeric aggregates (`SUM`/`MIN`/`MAX`/`AVG`) | 2.5% | 4/11 repos | ❌ not in grammar | C1 |
| 15 | positive `EXISTS { }` | 0.5% | 1/11 repos | ❌ not in grammar | D2 |
| 16 | explicit `UNION` | 0.2% | 1/11 repos | ❌ not in grammar | F2 |

**The headline: Gryphon's #1 measured gap is exactly the wishlist's #1 pick (`WITH`, F1 ★).** The
data confirms the existing intuition rather than overturning it — but it **re-sequences the middle
of the list** (see §3): `COLLECT` should precede numeric aggregates, and `UNWIND`'s demand signal
has now arrived.

**What Gryphon already ships covers the demand core.** Every one of the top-6 *most-used* features
across the app corpus — `pred_comparison` (42.8%), `AND/OR/NOT` (30.4%), pattern var-binding
(28.5%), `LIMIT` (23.2%), `$params` (20.9%), inline node props (20.5%) — is **shipped**. So are
`ORDER BY`, multi-`MATCH`, `IN`, `STARTS_WITH`/`CONTAINS`, undirected edges, `COUNT`, `IS NULL`,
`=~`, and (narrow-v0) `OPTIONAL MATCH`. The gap is a **tail of composition/aggregation/function**
features, not a hole in the core.

## 1. Method (so the numbers are auditable)

- **Corpora (14 attempted, 13 with ≥1 read query):** `lyft/cartography`, `SpecterOps/BloodHound`
  (CE), `CompassSecurity/BloodHoundQueries`, `hausec/Bloodhound-Custom-Queries`,
  `ReversecLabs/awspx`, `hetio/hetionet`, `greenelab/connectivity-search-backend`, `MannLabs/CKG`,
  `deepfence/ThreatMapper`, `spring-projects/spring-data-neo4j`, `neo4j-graph-examples/recommendations`,
  plus two **library** corpora held separate in the app view: `neo4j/apoc` and
  `neo4j/graph-data-science`. (`JupiterOne/starbase` was mined but yielded 0 — it uses J1QL, not
  Cypher, and delegates graph I/O to an SDK.)
- **Unit of count = "queries using the feature at least once"** (not raw occurrences), so a query
  that uses `WITH` three times counts once for `WITH`. Percentages are `queries-using ÷
  read-queries-analyzed` within the corpus set.
- **Read-only filter:** write clauses were tallied but excluded from the ranked gap — Gryphon
  rejects writes *by design* (read-only-by-construction; GRY-ARCH-7 / GRY-SEC-1). Writes appeared
  in only 1–2 corpora regardless.
- **Two aggregations** are reported because the two library corpora dominate raw volume and skew
  per-query rates:
  - **App-focused (11 repos, 565 read queries)** — the demand a customer-facing TAP instance
    actually sees. **This is the view the sequencing rests on.**
  - **All-13 (1295 read queries)** — includes apoc + GDS; useful only to show *how badly* they skew
    (see §4).
- **Corroborating external studies** (not counted, used as a sanity check on ranking): the SLE 2019
  empirical study of Cypher in the wild, Neo4j's Text2Cypher 44,387-instance dataset, and Francis
  et al. (SIGMOD 2018) for the semantic-feature taxonomy. All three rank `WITH`, aggregation, and
  variable-length paths in the same high band this corpus does.
- **Honesty about the instrument:** feature classification was done by LLM readers over each repo's
  query text, then aggregated deterministically from the workflow journal (not re-estimated). Treat
  the counts as **±1 rank noise**, not survey-grade precision — the *bands* (headline vs. tail) are
  the load-bearing signal, and they agree with the three external studies. The apoc/GDS split (§4)
  is exact, not estimated.

## 2. The full two-view table

Percentages are share-of-read-queries within each view. `∆` flags where the library corpora move a
feature's apparent rank.

| Feature | App % (n=565) | App breadth | All-13 % (n=1295) | Gryphon status |
| --- | :--: | :--: | :--: | --- |
| `pred_comparison` (`=`,`<`,`>`,…) | 42.8 | 11/11 | 21.3 | ✅ shipped |
| `AND` / `OR` / `NOT` | 30.4 | 11/11 | 14.2 | ✅ shipped (combinators) |
| pattern var-binding `(a)-[e]->(b)` | 28.5 | 9/11 | 18.7 | ✅ shipped † |
| `LIMIT` | 23.2 | 7/11 | 12.1 | ✅ shipped (A2) |
| `$params` | 20.9 | 7/11 | 16.3 | ✅ shipped |
| inline node props `{k: v}` | 20.5 | 9/11 | 20.4 | ✅ shipped |
| **`WITH`** | **19.5** | 10/11 | 13.7 | ❌ not in grammar (F1 ★) |
| `ORDER BY` | 19.1 | 11/11 | 13.6 | ✅ shipped (A1) |
| multiple `MATCH` | 15.8 | 9/11 | 7.5 | ✅ shipped (implicit union) |
| `IN` list | 15.6 | 9/11 | 6.9 | ✅ shipped (B1) |
| **`COLLECT`** | **14.9** | 10/11 | 11.0 | ❌ not in grammar (C2) |
| **var-length path** `-[*n..m]-` | **14.5** | 7/11 | 7.5 | ⚠ parses, executor **rejects** (E1) |
| **`DISTINCT`** | **12.2** | 7/11 | 8.1 | ❌ not in grammar (A4) |
| arithmetic in expressions | 10.4 | 10/11 | 6.1 | ❌ not built |
| `STARTS_WITH`/`ENDS_WITH`/`CONTAINS` | 10.3 | 5/11 | 4.6 | ✅ shipped (B2) |
| undirected edge | 10.1 | 8/11 | 5.7 | ✅ shipped |
| `COUNT` | 9.9 | 10/11 | 11.7 | ✅ shipped |
| `coalesce()` | 8.7 | 5/11 | 3.9 | ❌ not in grammar (H1) |
| `labels()`/`type()`/`keys()` | 6.7 | 7/11 | 5.5 | ❌ not built |
| `OPTIONAL MATCH` | 6.5 | 6/11 | 3.1 | ✅ shipped (D1, narrow v0) |
| string functions | 6.0 | 5/11 | 2.7 | ❌ not built (H2) |
| **`shortestPath`** | 5.8 | 5/11 | 2.5 | ❌ not in grammar (E3) |
| `IS NULL` / `IS NOT NULL` | 5.0 | 6/11 | 2.4 | ✅ shipped |
| list ops / comprehensions | 5.0 | 9/11 | 4.7 | ❌ not built (deliberate subset) |
| `size()` | 5.0 | 8/11 | 3.2 | ❌ not built (H2) |
| **`UNWIND`** | 4.8 | 7/11 | 6.6 | ❌ not in grammar (F3) |
| `id()` | 4.2 | 4/11 | 4.2 | ⚠ partial (`entity_id` projectable; `id()` fn not built) |
| `=~` regex | 3.7 | 6/11 | 1.6 | ✅ shipped |
| `SKIP` / `OFFSET` | 3.4 | 2/11 | 1.5 | ❌ not in grammar (A3) |
| `CALL` procedure | 2.7 | 4/11 | **26.3 ∆** | 🚫 deliberate omission (→ §3, §5) |
| numeric aggregates `SUM`/`MIN`/`MAX`/`AVG` | 2.5 | 4/11 | 1.3 | ❌ not in grammar (C1) |
| label-union `(:A\|B)` | 1.9 | 4/11 | 1.1 | ❌ withdrawn (B4 superseded) |
| map projection | 1.9 | 2/11 | 1.4 | ❌ not built (deliberate subset) |
| `CASE WHEN` | 1.8 | 3/11 | 1.2 | ❌ not in grammar (H1) |
| temporal functions | 1.6 | 3/11 | 0.7 | ❌ not built |
| `reduce()` | 1.2 | 3/11 | 0.6 | ❌ not built |
| `NOT EXISTS { }` | 1.2 | 2/11 | 0.5 | ✅ shipped (`~Exists()`) |
| `CALL { }` subquery | 1.1 | 1/11 | 0.5 | ❌ not built |
| pattern predicate in `WHERE` | 0.9 | 3/11 | 0.4 | ⚠ partial |
| inline edge props `-[{k:v}]-` | 0.5 | 2/11 | 0.8 | ✅ shipped |
| `exists(n.prop)` | 0.5 | 2/11 | 0.5 | ✅ partial (via `IS NOT NULL`/`IS KNOWN`) |
| positive `EXISTS { }` | 0.5 | 1/11 | 0.2 | ❌ not in grammar (D2) |
| write clauses (`CREATE`/`MERGE`/`SET`/…) | 0.4 | 1/11 | 1.2–1.7 | 🚫 rejected **by design** (read-only) |
| explicit `UNION` | 0.2 | 1/11 | 0.2 | ❌ not in grammar (F2) |

† *Pattern var-binding* here means naming nodes/edges in the pattern (`(a)-[e]->(b)`), which ships.
The classifier folds in full **path-variable binding** `p = (a)-[*]->(b)` — that shape *parses* (grammar
line 35, `path_var: NAME "="`) but the executor **rejects** it, same fail-closed posture as var-length
paths; it's wishlist E2 and rides with E1. So the 28.5% overstates the *fully-shipped* slice slightly.

## 3. Non-obvious findings

1. **`COLLECT` (14.9%) massively outranks the numeric aggregates `SUM`/`MIN`/`MAX`/`AVG` (2.5%)** —
   a ~6× gap. Intuition (and the wishlist's Bucket C ordering) treats numeric aggregates as the
   natural "next aggregate after COUNT," but the corpus says list-aggregation is what people actually
   write — it's the N+1-defeater that assembles children-per-parent in one query.
   **Sequencing consequence: promote C2 (`COLLECT`) ahead of C1 (numeric aggregates).** The wishlist
   already tags C2 `extract-ahead` and notes it "unlocks UI shapes that don't yet exist" — the data
   backs that and says do it *first*.

2. **`UNWIND`'s demand signal has arrived.** The wishlist parks F3 (`UNWIND`) as `wait-for-signal`
   ("no demand signal yet"). It's in **7 of 11** app repos at 4.8% (and 6.6% across all-13, *above*
   its own IN-list cousin's all-13 rate). That crosses the wishlist's own promotion bar. It's still
   mid-pack, not urgent — but "no signal yet" is now factually stale.

3. **`CALL` is a library-inflation artifact, not app demand.** It's the #1 feature in the all-13 view
   at **26.3%** — but that is almost entirely apoc's test corpus calling apoc procedures. In the app
   view it collapses to **2.7% (4/11)**. This is the strongest argument in the dataset for the
   app/library split, and it **validates Gryphon's deliberate omission of general `CALL`**: real apps
   don't lean on it; the volume is a standard library testing itself. Where genuine app-side `CALL`
   demand exists it is *algorithmic* (GDS-style pagerank/community/path) — which points at the
   **NetworkX/analytics distinct-backend** (see `doc-gryphon-networkx-opportunity.md`), not at a
   general procedure-call surface.

4. **Security asset-graph corpora are the feature-dense, TAP-adjacent ones — and they lean on exactly
   the reachability tail Gryphon rejects.** BloodHound (CE + both community query packs), awspx,
   cartography, and ThreatMapper are the closest analogues to TAP's own domain (asset/attack graphs).
   They are disproportionately heavy on **var-length paths and `shortestPath`** — attack-path /
   blast-radius queries *are* variable-length reachability. So the E1/E3 tail, low-ranked in the
   general corpus, is **high-ranked in TAP's own neighborhood**. When a TAP customer writes the
   queries a BloodHound user writes, E1 stops being `wait-for-signal`. Worth weighting E1 above its
   raw 14.5% for TAP specifically.

5. **The shipped core is genuinely adequate.** No shipped feature is a rare curiosity, and no top-6
   feature is unshipped. Gryphon's demand-shape strategy — grow on signal, not on Cypher's ToC — has
   in fact tracked demand well: the built set *is* the high-frequency set. The gaps are the
   composition layer (`WITH`), the aggregation layer (`COLLECT`), and the graph-flavored tail
   (var-length / shortestPath) — precisely the three the wishlist already flags as its heaviest,
   highest-value items (F1 ★, C2, E1).

## 4. The apoc/GDS skew (why two views)

The two library corpora carry disproportionate raw volume and distort per-query rates:

| Corpus | Read queries | Share of all-13 | Nature |
| --- | :--: | :--: | --- |
| `neo4j/apoc` | 668 | **52%** | a standard-library test suite calling its own procedures |
| `neo4j/graph-data-science` | 62 | 5% | algorithm-library test fixtures + docs |
| all 11 real apps combined | 565 | 44% | actual application queries |

apoc alone is over half the raw corpus, and it is *not* representative of application demand — it is
a library exercising itself, which is why `CALL` balloons to 26.3% in the all-13 view and collapses
to 2.7% in the app view. **The app-focused view (§0, §2) is the one to sequence against.** The
all-13 column is retained only to make the skew visible and auditable.

## 5. What this means for the wishlist and the commandments

The data doesn't move the top of the list — it **confirms F1 `WITH`** as the keystone, matching the
wishlist and all three external studies. What it changes:

- **Re-order Bucket C:** `COLLECT` (C2) before numeric aggregates (C1). Finding §3.1.
- **Promote `UNWIND` (F3)** out of `wait-for-signal` into a named candidate. Finding §3.2. (Still
  behind F1/C2 — mid-pack, not headline.)
- **Keep `CALL` omitted** as an app-demand call, and route the genuine algorithmic slice to the
  analytics backend, not to a general `CALL`. Finding §3.3 + `doc-gryphon-networkx-opportunity.md`.
- **Weight E1 (var-length) up *for TAP's domain specifically*** even though it's mid-rank generally —
  TAP's asset-graph neighborhood is var-length-heavy. Finding §3.4. This is the demand signal Bucket
  E was waiting on; it is now visible in the adjacent corpora, though not yet from a TAP customer.
- **The commandments (`doc-gryphon-commandments.md`) need no change from this** — the doctrine is
  about *how* features ship (fail-closed, apply-or-reject, source-checked, oracle-pinned), not
  *which*. This doc feeds the wishlist's ordering, not the commandments' rules. Its one relevant
  reinforcement: features that "parse but reject" (var-length, path-var) are the fail-closed credit
  in action (GRY-ARCH-3) — the corpus shows they're *demanded*, which is what makes fail-closed
  (vs. silent-wrong) the right posture until they're built.

## 6. Doc-drift caught while verifying supply-side status (fixed 2026-07-06)

`doc-dev-gryphon-vs-cypher.md` (Ledger C, row "Variable-length paths") previously stated *"Bounded
repetition (`*1..3`) ships."* **It does not.** The grammar parses `*n..m` (`hop_range`, grammar line
55) but the executor rejects bounded multi-hop (`executor.py:412` and `:1652` raise
`SearchExecutionError`; rejection is pinned by `test_gryphon.py`; `model_oracle.py` marks it
`OracleUnmodeled`). The correct status is **"parses but the executor rejects — fail-closed, not
shipped"** (this is E1, still `wait-for-signal`). This is the same overclaim the comparative study
caught in its own synthesis and codified as GRY-PROC-2 (source-check executor claims). **The Ledger-C
row has since been corrected** to match the executor.

## Pointers

- **Supply side (what ships):** `doc-dev-gryphon-vs-cypher.md` (the three ledgers), `doc-dev-gryphon-wishlist.md` (the buckets this re-sequences).
- **The algorithmic-`CALL` destination:** `doc-gryphon-networkx-opportunity.md`.
- **The doctrine this respects:** `doc-gryphon-commandments.md` (fail-closed GRY-ARCH-3, source-check GRY-PROC-2).
- **External corroboration:** SLE 2019 Cypher-in-the-wild study; Neo4j Text2Cypher dataset; Francis et al., SIGMOD 2018 (semantic taxonomy).
- **Raw aggregation:** workflow `wf_684476bc-36b` journal (per-repo `feature_counts`), aggregated deterministically; re-derivable from the journal.
