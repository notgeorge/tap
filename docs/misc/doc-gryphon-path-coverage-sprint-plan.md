# Plan — Gryphon path-coverage hardening sprint (and mop up the envelope-WHERE bug *through* the process)

**When:** next session (big-token spend, kicked off up front).
**Why:** `docs/aar/2026-06-30-gridkin-intent-coverage-not-path-coverage.md` — gridkin/TCK coverage is indexed by language *intent*, not executor *dispatch path*, so a bug in one path hides behind scenarios routing through another. A "100% intents covered" ledger sat over an entirely untested branch.
**Bug we fold in:** the envelope-WHERE-drop defect (`docs/misc/doc-gryphon-envelope-where-defect-handoff.md`). We do **not** fix it in isolation — we build the process that *surfaces* it, *mechanically confirms* it, fixes it, then *generalizes + regression-locks* across all paths.
**Scope boundary (explicit):** deliver the three cheap layers below and the bug fix. **Stop just shy of metamorphic / property-based tests** — that's the next tier, deliberately deferred (name it, don't build it).

---

## The thinking we're baking in (from the AAR discussion)

Ranked by leverage-per-cost. You cannot test your way to completeness (testing shows presence of bugs, not absence), so the posture is **layered defense + loud failures**, not one guarantee:

1. **Fail-closed at the source** — no dispatch path may accept-and-ignore part of its input (a `where_clause` it never applies). Apply-or-reject. This *reduces the stakes* of incomplete coverage: an untested case fails loud, not silent. Most important because it doesn't depend on having thought of the case.
2. **Empirical path coverage** — derive the path set from the *code*, not a human's mental model. TAP already emits `gryphon_stage("...")` markers, and they're already printed in every captured SQL snapshot (`-- statement 1 · stage: edge-type-scan`). Gate that every reachable stage is exercised — sharpened to "with a WHERE." Makes gaps *visible* without anyone enumerating them.
3. **Failure-mode invariant** — for the specific silent-drop class: assert every data-lane WHERE predicate's column appears in the captured SQL (exempt the two-valued null short-circuit). Cheap point-defense that fires regardless of authoring shape.

*Deferred (next tier, not this sprint):* **metamorphic / property tests** — assert different query shapes of the same intent agree (envelope form vs projection form must return consistent node sets). This is the automated version of what caught the bug by hand; build it once the language surface stabilizes.

---

## Morning sequence

### Phase 0 — Frame & instrument (small)
- Re-anchor line numbers (they drift): `grep -n "def _execute_edge_type_scan\|def _execute_hub_and_spoke\|def _dispatch_pattern\|def _apply_predicate_to_qs\|gryphon_stage(" tap_grid/gryphon/executor.py`.
- Confirm the bug still repros (the two-node-AND envelope query from the handoff → Neighbor One leaks).
- **Enumerate the dispatch paths from the code** — every `gryphon_stage("...")` call site is the authoritative path list (edge-type-scan, hub-and-spoke, advanced/chain, type-scan, bare-scan, optional-match, NOT-EXISTS, …). This list is the coverage target; it comes from the source, not memory.

### Phase 1 — Empirical stage-coverage gate (visibility first)
- New gridkin meta-test: parse the `stage: <label>` tags out of every committed `*.sql.txt` snapshot; collect the set actually exercised. Cross-check against the enumerated `gryphon_stage` call sites.
- Assert every reachable stage is hit by ≥1 result scenario, **sharpened**: every stage that can carry a WHERE is exercised *with* a WHERE (parse the scenario query for a WHERE clause; map to the stage its snapshot recorded).
- Run it. Expected: it **flags `edge-type-scan` (envelope) as never exercised with a WHERE** — the blind spot, now visible and gated. *This is the process surfacing the bug.*

### Phase 2 — WHERE-reached-the-SQL invariant (mechanical catch)
- New gridkin meta-test: for every result scenario whose query has a data-lane WHERE predicate, assert the predicate's field/column name appears in the captured SQL snapshot. **Exempt** the deliberate two-valued null short-circuit (e.g. `STARTS_WITH null` → always-false `pk IS NULL AND NOT pk IS NULL`, where the column legitimately doesn't appear).
- Run against existing scenarios — should be green (they route through WHERE-applying paths).

### Phase 3 — Author the envelope-WHERE scenario → confirm the bug mechanically
- Author the envelope-form scenario Phase 1 demands (`MATCH (h:pg_hub)-[:PG_LINKS]->(n:pg_node) WHERE … `, no RETURN).
- The Phase 2 invariant should now **fire** — the WHERE column is absent from the SQL. *The bug is now confirmed by a machine, not by luck of a human reading an oracle.* That is the whole point: the process catches it independent of authoring shape.

### Phase 4 — Fix (apply the WHERE; fail-closed folded in)
- Per the handoff's preferred option: route envelope-with-non-anchor-WHERE through the **chain machinery** (`_build_chain_queryset` + `_apply_predicate_to_qs`, already strictness-aware), then serialize as a graph envelope. Keep the fast `_execute_edge_type_scan` for the genuinely WHERE-less case.
- Fix `_execute_hub_and_spoke` to apply the AND-ed remainder beyond the `entity_id` anchor.
- **Fail-closed folded in:** any predicate shape the envelope path genuinely can't support must `raise SearchExecutionError`, never silently drop. After this, no dispatch path accepts-and-ignores a WHERE.
- Gotchas (from the handoff): direction fan-out (undirected `any` runs two queries + unions — filter both arms); endpoint joins via the per-variable bindings; thread `declared_types` so strictness applies here too; SQL snapshots change (multi-statement) — regenerate and **read** them.

### Phase 5 — Backfill coverage, generalize, lock in
- Author envelope-WHERE scenarios across the shapes that dispatch differently: data-lane comparison, `IN`, `IS NULL`, anchor + data-lane remainder, directed + undirected. Predict, regenerate, **verify each oracle**.
- Both new guards (stage-coverage + WHERE-in-SQL) green across all paths; the envelope-WHERE branch is now covered.
- Strike the `clauses/match-where` defect gap in the coverage ledger; add the new scenarios' folder cites.
- Update `spec-grid-traversal-language.md` (WHERE behavior on the envelope path) and the divergence doc if relevant.
- Full suite + guards + black/ruff/mypy green. Commit in logical chunks; promote.

### Stop line
- **Do not** build metamorphic / property-based tests this sprint. Record the envelope-vs-projection consistency relation as the seed for that next tier (in the AAR corrective-actions and a memory) and stop.

---

## Beyond the sprint — research threads toward verifiable completeness (morning question, NOT this sprint)

The reframe that makes this tractable: **Gryphon is a compiler, not a database.** It translates AST → SQL over a schema we own, run by Postgres (treat as trusted). So the bug surface is *translation fidelity*, not query execution — and we have the intermediate representation (the SQL, already snapshotted) **and** a ground-truth substrate (the relational tables). Black-box regimes (TCK) have only inputs/outputs; we have more, and should exploit it. Citations below are **leads to verify**, flagged by confidence — do not trust as fact until checked.

**Query-engine testing prior art (directly relevant, high confidence):**
- **SQLancer** (Manuel Rigger, ETH) — the landmark automated DBMS-testing work; its oracles are the industrialized versions of what we want:
  - **NoREC** — optimized query vs. an equivalent form the optimizer can't optimize; counts must match. **Literally the envelope-vs-projection relation that caught our bug.**
  - **TLP** (Ternary Logic Partitioning) — `p` / `NOT p` / `p IS NULL` partitions must union to the whole. Targets three-valued-logic bugs — directly probes Gryphon's deliberate **two-valued** divergence for consistency.
  - **PQS** (Pivoted Query Synthesis) — pick a seeded row, synthesize a query guaranteed to return it, assert it's returned. Oracle-by-construction.
- **Differential testing** — same query, two independent computations, compare.

**Graph-specific (verify — lower confidence):** openCypher TCK (conformance, have it); believed academic metamorphic/differential work on Cypher engines (e.g. something like "GDsmith" targeting Neo4j/RedisGraph) — thread to pull, not a fact.

**Formal methods (the "coming back" tier):**
- **Cypher formal semantics** — Francis, Guagliardo, Libkin et al., ~SIGMOD 2018 (confident it exists). Gryphon is a subset+divergence; read for *what* to formalize.
- **SQL equivalence provers — Cosette / HoTTSQL** (UW; Chu, Cheung, Suciu). Because we emit the SQL, assert a Gryphon query's compiled SQL is *provably equivalent* to a reference SQL — proof, not sampling.
- **GQL / SQL-PGQ** (ISO graph-query standard) formalization momentum — track it.
- Mechanized compiler proofs (Coq/Isabelle/Lean) — the ceiling; almost certainly beyond v0 ROI.

**What owning the SQL substrate unlocks (George's reverse-query idea, laddered by power):**
1. **Differential vs. an independent oracle** — seed a graph, compute the expected answer a *second* way (hand SQL, or a tiny in-Python graph interpreter over the ORM), diff against Gryphon. Executable reference, not a human-predicted oracle. ("Seed then confirm" is rung 1; "seed randomly, compute expected via the model, diff" is the sharp version.)
2. **Model-based reference oracle** — maintain a trivial in-memory graph model while seeding; a Python function answers any query against the model; diff. The model IS the oracle; property/metamorphic generation plugs in here.
3. **Exhaustive small-scope** (Alloy small-scope hypothesis) — we control seeding, so generate ALL graphs up to N nodes / M edges and check a property: exhaustive over that scope, far stronger than random sampling for structural bugs.
4. **Compiler-testing framing → prior art** — Csmith (random programs, differential across compilers) and **EMI / equivalence-modulo-inputs** (Le, Su): mutate the input in result-preserving ways, assert output unchanged. Portable to "mutate a Gryphon query in result-preserving ways, assert the compiled SQL still agrees."

**Unifying thesis to test in the morning:** because the target is trusted, faithfulness can be checked three ways a black-box TCK can't — (a) an independent reference computation over the same seeded data, (b) SQL-equivalence proofs on the compiled output, (c) metamorphic relations that must hold regardless of emitted shape. Decide which of these earns its keep for v0 vs. reserves.

## Definition of done
- No executor dispatch path silently ignores a WHERE (apply-or-reject) — verified by fail-closed behavior.
- Stage-coverage gate green: every reachable `gryphon_stage` exercised, WHERE-carrying stages exercised with a WHERE.
- WHERE-reached-the-SQL invariant green across the suite.
- Envelope-WHERE defect fixed; its ledger gap struck; scenarios cover the envelope path across shapes.
- Both guards are the reusable regression floor for the *whole class*, not just this bug.

## Pointers
- Why: `docs/aar/2026-06-30-gridkin-intent-coverage-not-path-coverage.md`
- The bug (detail): `docs/misc/doc-gryphon-envelope-where-defect-handoff.md`
- Reference (correct WHERE application): the chain executor `_apply_predicate_to_qs` / `_build_chain_queryset`; strictness `_declared_data_types` / `_enforce_type_strictness`.
- Validation commands: in the defect handoff (regenerate oracles; run the four suites as ONE invocation — never overlap two pytest runs, they deadlock the test DB).
