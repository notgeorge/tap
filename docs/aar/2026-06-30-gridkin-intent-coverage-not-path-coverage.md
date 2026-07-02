# AAR — Gridkin catches *intents*, not executor *paths*: a silent-WHERE-drop bug we found by luck of authoring shape

**Subject:** the gridkin / openCypher-TCK testing *process*, not the bug it surfaced.
**Companion:** the bug itself is handed off in `docs/misc/doc-gryphon-envelope-where-defect-handoff.md` (the *what-to-fix*); this AAR is the *why-didn't-our-process-guarantee-the-catch*.
**Date:** 2026-06-30.

> **RESOLVED 2026-07-01.** The corrective actions in §7 were built. The headline
> — a mechanical, authoring-independent invariant that fires no matter which
> query shape an author picks — was implemented not as an SQL-scrape (which
> false-greens: the dropped column still appears in the SELECT list) but as an
> **independent model-based reference oracle** (`plugins/gryphon_playground/gridkin/model_oracle.py`):
> a second Gryphon engine that interprets the same AST over plain Python objects
> from the same fixture, sharing zero ORM-lowering with the executor, wired as a
> third gridkin assertion. It caught the envelope-WHERE bug day one (executor
> returned 4 nodes, oracle computed the correct 3) and then served as the net
> proving behavior-preservation while the executor was refactored. "Fail closed
> at the source" was implemented as the **single-hop dispatch collapse** (4
> executors → 1, all routed through the WHERE-applying chain path — apply-or-
> reject, silent-drop now structurally impossible). **Next-tier seeds** (deferred,
> not built): the envelope-vs-projection consistency relation is *NoREC* (SQLancer);
> the 2VL/3VL null boundary is what *TLP* probes; a random-GRIFT generator feeding
> the model oracle turns it into a property-based fuzzer overnight. See the
> compiler-validation research thread in `docs/misc/doc-gryphon-path-coverage-sprint-plan.md`.
>
> **Update 2026-07-01 (follow-on).** The oracle's `OracleUnmodeled` skip-list was
> shrunk so it asserts on 99% of result scenarios (union, NOT EXISTS, OPTIONAL
> MATCH, bare-var RETURN now modeled). And the §7 **"executor-path coverage axis"**
> corrective action is now built as a real gate: `req-gridkin-stage-coverage`
> (`plugins/gryphon_playground/gridkin/stage_coverage.py`, guarded by
> `TestStageCoverage`) derives the dispatch-path set from the executor's
> `gryphon_stage()` call sites and asserts each is exercised by a *WHERE-carrying*
> scenario — the exact property whose absence was this bug. The §7
> **"branch coverage on the executor, ratcheted"** action is built too:
> `req-gridkin-executor-branch-coverage` (`scripts/gryphon-coverage-ratchet` + a
> committed floor in `tap_grid/gryphon/coverage-baseline.json`) ratchets
> `coverage.py` branch coverage of `executor.py` (floor 73% at landing) across the
> whole executor test corpus — the branch-level complement to the stage gate,
> honestly tracked in the `spec-dev-validation.md` Validation Map as a script (not
> per-commit CI) until the dev-validation gate absorbs it. Every §7 corrective
> action is now realized. **And one next-tier seed is built:** TLP
> (`req-gridkin-metamorphic-tlp`) — a metamorphic partition (TRUE/FALSE/UNKNOWN
> reconstructs the unfiltered scan) that probes the 2VL/3VL null boundary as
> executor *self*-consistency, catching common-mode bugs the oracle could share.
> Its sibling NoREC was considered and deferred (single-hop projections degrade to
> envelopes, so it yields no distinct check). Still open: the property fuzzer
> (random graph + query → executor vs oracle).

---

## 1. Goal vs. Outcome (read this first)

**Goal:** the gridkin/TCK mop-up's whole premise — author oracle-disciplined scenarios mined from the openCypher TCK so that Gryphon's traversal behavior is *systematically* covered, and silent-wrong-results bugs can't hide.

**Outcome:** we *did* catch a major silent-wrong-results bug — a single-hop relationship **envelope** query silently drops its non-anchor `WHERE`, returning too many rows. But the catch was **contingent on an arbitrary authoring choice**, not guaranteed by the process. Had the scenario been written in a different-but-equally-valid query shape, it would have closed **green** and the bug would still be hidden. The process surfaced the right *intent*; it did not *oblige* coverage of the buggy *path*. The safety net that actually caught it (manual oracle review) is real and worked — but it only got the chance because the dice landed on the buggy shape.

The scary inference: **other executor paths are almost certainly untested in the same way, and nothing in the process would tell us.**

## 2. Timeline

1. TCK mining surfaced a coverage gap: *"multi-variable conjunction constraining two different bound nodes"* (`clauses/match-where`).
2. I authored a scenario for it as a **graph envelope** query — `MATCH (h:pg_hub)-[:PG_LINKS]->(n:pg_node) WHERE h.data.severity_score = 0 AND n.data.severity_score > 15`, no `RETURN`.
3. Regenerated the oracle. Hand-prediction: hub + the two neighbors with sev > 15. The regenerated oracle contained **Neighbor One (sev 10)** as well.
4. The prediction-vs-oracle mismatch (`req-gridkin-oracle-assertion`) forced an investigation. The captured SQL had **no `severity_score` clause at all** — the entire `WHERE` was absent.
5. Traced it to `_execute_edge_type_scan`, which never receives `where_clause`. Confirmed the **aggregation** form of the *same intent* applies the `WHERE` correctly (chain executor). Rewrote the scenario in aggregation form to close the gap honestly; recorded the envelope defect as a feature-gap and wrote the handoff.

The pivot point is step 2: *envelope* was an arbitrary pick. The *aggregation* pick (step 5) passes. Same intent, opposite outcome, chosen by a coin-flip.

## 3. What went well

- **Oracle discipline did its job.** Hand-predicting the result and reading the regenerated oracle is exactly the mechanism `req-gridkin-oracle-assertion` exists for, and it's the only reason a wrong row didn't get captured as "expected" and sail through green. The discipline is sound; keep it.
- **The TCK process surfaced the intent.** Mining did point at the "two bound nodes constrained" shape — without it I'd not have been near this query at all.
- **The dual-shape comparison localized the bug fast** — once the envelope form failed and the aggregation form passed, the buggy path was isolated in one step.

## 4. What went wrong (the process gap)

**Gridkin/TCK coverage is indexed by language *intent* (semantics), not by executor *dispatch path*.** One intent — "a `WHERE` predicate over two bound nodes" — maps **many-to-one** onto executor implementations:

| Query shape for the *same* intent | Executor path | Applies WHERE? |
| --- | --- | --- |
| envelope, unanchored (`...WHERE...`, no RETURN) | `_execute_edge_type_scan` | **No (the bug)** |
| envelope, `entity_id`-anchored | `_execute_hub_and_spoke` | anchor only; AND-ed remainder dropped |
| row projection / aggregation (`RETURN ... COUNT`) | chain executor (`_apply_predicate_to_qs`) | **Yes (correct)** |

The ledger tracks *which TCK intents are covered*. It does **not** track *which executor paths are exercised*, nor does it require a `WHERE` (or `ORDER BY`, or `LIMIT`, or `IN`, …) to be tested in **every shape that dispatches differently**. So:

- The envelope-with-non-anchor-`WHERE` path had **zero** scenarios — a whole branch untested.
- Nothing measured or flagged that absence. A "100% of mined intents covered" ledger sat directly on top of an entirely untested code path.
- The catch depended on a human/agent happening to author into the untested branch *and* the oracle review firing. Both are real; neither is guaranteed.

## 5. Root causes

- **Intent-coverage ≠ path-coverage.** Mining a *spec/TCK* tells you the *language* is covered. It says nothing about whether each *implementation* of a feature is exercised. When a feature has multiple dispatch paths, intent-coverage systematically under-counts.
- **Silent-ignore is permitted by construction.** `_execute_edge_type_scan` *accepts* a pattern that carries a `WHERE` and simply never looks at it. An executor path that takes input it silently ignores is a latent silent-wrong-results bug with no alarm.
- **No mechanical, authoring-independent cross-check.** The only thing standing between this bug and a green checkmark was a human reading an oracle and noticing one extra row. There is no machine invariant that fires regardless of which shape an author happens to pick.
- **The SQL snapshot is captured but not *interrogated*.** Gridkin already records the generated SQL for every result scenario — the evidence that the `WHERE` was missing was sitting right there in the snapshot, unexamined by any guard.

## 6. Impact

- **One confirmed silent-wrong-results bug** (envelope drops `WHERE`) — common shape ("subgraph of hubs linked to high-severity nodes" silently returns *all* links). Handed off, reserved.
- **Unknown latent exposure.** By the same logic, any executor path not happened-upon by an author may harbor a similar silent defect. We have no measure of how many paths are unexercised. This is the part that should be treated as "scary": the process gave false confidence proportional to its intent-coverage number.

## 7. Corrective actions (proposed — none built in this session)

Tiered honestly; all are *recommended*, not yet implemented.

### Headline (cheap, mechanical, authoring-independent): assert the WHERE reached the SQL
A gridkin meta-check that, for every **result** scenario whose query carries a data-lane `WHERE` predicate, asserts the predicate's field/column **appears in the captured SQL snapshot** — *unless* the scenario is a deliberate two-valued null short-circuit (the `name STARTS_WITH null` → always-false contradiction, where the column legitimately doesn't appear). Rides entirely on SQL gridkin **already captures**. It would have caught this bug and catches the *entire* silent-WHERE-drop class across all paths, regardless of which shape the author picked. This is the asymmetric, build-once edge (cf. `spec-security-posture.md` cheap-foundational-edges).

### Fail closed at the source
No executor dispatch path should accept-and-ignore a `where_clause`. `_execute_edge_type_scan` / `_execute_hub_and_spoke` should **apply it or raise** — never drop it. Make silent-ignore structurally impossible (this overlaps the bug fix itself).

### Executor-path coverage axis (alongside the TCK-intent axis)
Enumerate the dispatch paths (`_execute_edge_type_scan`, `_execute_hub_and_spoke`, the chain/aggregation executor, OPTIONAL MATCH, bare labelless scan, type-scan, NOT EXISTS, …) and require each be exercised — ideally with `WHERE` / `ORDER BY` / `LIMIT` / `IN` / `IS NULL` variants where applicable. Add it to the coverage ledger as a second dimension, machine-checked.

### Branch coverage on the executor, ratcheted
`coverage.py` over `tap_grid/gryphon/executor.py` with a baseline-ratchet (same shape as the log-site-id / authz-coverage guards). The envelope-WHERE branch would have shown as uncovered.

### Query-shape matrix discipline (authoring rule)
When mining a TCK intent, enumerate the query **shapes** that route differently (envelope / projection / aggregation / anchored / unanchored / directed / undirected) and author across the ones that dispatch to different code — because the same intent is *not* the same execution path.

## 8. Lessons → durable rules

- **Semantic coverage is not path coverage.** Mining intents from a spec or TCK proves the *language surface* is covered, never that the *executor* is. Where one feature has multiple implementations, each implementation needs its own exercise — count paths, not just intents.
- **An executor path that silently ignores part of its input is a latent silent-wrong-results bug.** Fail closed: apply-or-reject, never accept-and-drop.
- **Don't let the last line of defense be the only line.** Oracle review (a human/agent reading a captured result) is necessary but it fired here only because the author stumbled into the broken path. Pair every "read it carefully" discipline with a *mechanical, authoring-independent* invariant that fires no matter what shape gets written.
- **If you already capture the evidence, interrogate it.** The missing `WHERE` was visible in the captured SQL the whole time. A guard that *reads* the artifact you're already snapshotting is nearly free and catches whole classes.
- **A green coverage number over an untested path is a confidence lie.** The ledger said "intents covered"; a reader heard "behavior verified." Name what a coverage metric does and does **not** assert (cf. the tap_cache AAR: "a comment asserting a guarantee is a latent lie until something fails when it's false").
