---
audience: [llm, developer]
covers:
  - ../../tap_grid/specs/spec-grid-traversal-execution.md
  - ../../tap_grid/specs/spec-grid-traversal-language.md
  - doc-gryphon-testing-philosophy.md
  - doc-gryphon-comparative-findings.md
  - doc-gryphon-hardening-roadmap.md
assumes:
  - Reader has read doc-gryphon-testing-philosophy.md (the ladder + the "frontier" section that already names Cosette/HoTTSQL and Francis et al.) and doc-gryphon-hardening-roadmap.md (the shrink-the-glue / conservation-invariant program this doc rests on)
  - Reader knows Gryphon is a compiler over a trusted Postgres substrate — the bug surface is translation fidelity, and we own both ends (the AST and the captured SQL)
provides: |
  A hot take on when and where formal methods earn their keep for the Gryphon
  executor, given its current shape (a read-only Cypher-subset compiler to ORM→SQL)
  and its trajectory (more read features toward Cypher, eventually writes). The
  thesis, a three-regime when/where decision map (read-core now / recursion wall /
  writes flip the problem), the tool lineage, the AI angle, and a staged
  escalation ladder whose rung-0 cheap edges are the same artifacts the hardening
  roadmap already produces. Opinionated by design; a decision aid, not a survey.
---

# Gryphon Formal Validation — When and Where Proof Earns Its Keep (A Hot Take)

> The "bonus points" deliverable of the comparative study. Written to answer a specific
> question — *given the executor's state, intent, and future, where would formal approaches
> be interesting?* — not to survey formal methods. It takes positions. Where it defers, it
> says why. It rests on `doc-gryphon-hardening-roadmap.md`: the roadmap's structural program
> and this doc's formal program share one substrate.

## 0. Thesis, up front

**The highest-*value* formal *direction* for Gryphon is not a proof — it is bounded-exhaustive
equivalence checking on the SQL we already capture; and the logical-plan IR the study weighed is
the same lever that unlocks it.** "Highest-value direction" is a deliberately careful phrasing:
this is where formal effort *should* point, not a cheap near-term build. The one genuinely cheap
move is **rung 0 — writing the semantics down** (§8). The equivalence harness itself is a **named
frontier** (§3, cost caveat), not a bolt-on. Four claims carry the rest of the doc:

1. We are a **translation validator's** dream, not a compiler verifier's nightmare: we own the
   source (AST), the target (captured SQL), and the ground truth (the tables). That is the exact
   input a per-run equivalence check needs — the *approach* is affordable in a way compiler
   verification never is (§2). The *harness* is still real work (§3).
2. Our bug class is **small-model-manifesting** (the envelope-WHERE defect showed on 3–4 nodes).
   That makes *bounded-exhaustive* checking — "for all databases up to size N, does the emitted
   SQL mean the same as the query?" — the right shape, and it sidesteps decidability entirely.
3. The formal payoff **concentrates exactly where our bugs already are**: the hard edges of the
   SQL-equivalence literature are nulls/3VL and aggregation, which are Gryphon's hotspots.
4. There is a **window**. The read core is in the formal sweet spot *now*; variable-length paths
   (recursion) are the wall; and writes, if they ever come, **flip the problem** from query
   equivalence to invariant preservation — a bigger prize on a different tool.

Everything below is the argument for those four and the staged ladder that follows from them.

## 1. Why the question is even tractable here

Formal methods usually die at the first step: *specify the whole system.* Verifying that Postgres
returns the right rows for arbitrary SQL is a career, not a sprint. Gryphon escapes this because
of the framing the testing philosophy already established (`§0`): **Gryphon is a compiler over a
trusted substrate.** Postgres is assumed correct. The entire bug surface is *translation fidelity*
— does the SQL we emit mean the same thing as the query we were handed?

That collapses the formal target from "verify a database" to "verify that *our* SQL equals *our*
query's meaning" — a small, bounded object. The subset is small (MATCH/WHERE/RETURN + a handful of
combinators). The target is trusted SQL. And, decisively, **we own both ends and the middle**: the
AST is ours, the emitted SQL is captured by the `capture_sql` seam (`req-grid-traversal-exec-sql-capture`),
and the ground-truth tables are ours to enumerate. A black-box database tester can only poke inputs
and read outputs; we can compare *meanings* at the boundary. That asymmetry is the whole reason
formal is affordable here and isn't for a general graph engine.

## 2. Two schools — and which door is cheap

There are two ways to bring proof to a compiler, and they differ by a factor of ~100 in cost.

- **Compiler verification** (CompCert-style, Leroy): prove *once, for all inputs*, that the
  compiler preserves semantics. This means the whole executor — parser, lowering, ORM emission —
  reconstructed inside a proof assistant (Rocq/Coq, Lean) and kept in sync as it grows. For a
  Python, still-evolving, ORM-string-emitting executor this is a boondoggle. **Reject.**
- **Translation validation** (Pnueli–Siegel–Singerman 1998; Necula 2000): don't verify the
  compiler — verify each *run*. For *this* query, check that the emitted artifact is equivalent to
  the query's denotation. You never trust the compiler; you gate its output. This composes directly
  with the capture seam (the emitted SQL is already in hand) and with the model oracle (an
  executable denotation is already in hand). **This is the door.**

The study handed us a live data point on the difference. openCypherTranspiler *rents a whole Neo4j*
as a differential oracle (`dossier-opencyphertranspiler.md`, `SQLRendererTest.cs:266-360`) — a
runtime translation-validation instinct. But its own harness shows the trap: its ordering assertion
is a `NotImplementedException` and it blurs `null` vs `""` — **proxies that false-green exactly
where the lowering is weakest.** The formal version *replaces the rented engine with a checkable
semantics*, so the check is precise instead of noisy. (This is also why OPP-16 in the findings —
renting Neo4j as our third oracle — was rejected: a stock engine is a noisy oracle for a language
that deliberately diverges from Cypher.)

## 3. The bug class is small-model — so bounded beats unbounded

Every translation-fidelity defect Gryphon has had manifested on a *tiny* graph. The envelope-WHERE
bug showed on three nodes; the far-node-WHERE inflation on a three-layer chain. This is the
**small-scope hypothesis** (Alloy's founding premise, Jackson): if a transformation is wrong, it is
almost always wrong on a small input. Our property fuzzer already *bets* on this — with **random**
small inputs. The formal upgrade is to make the bound **exhaustive** rather than sampled:

> For all databases up to size N (all label/edge/property assignments over a bounded universe),
> does the emitted SQL return the same result as the query's reference denotation?

That is a genuinely different guarantee from everything on the current ladder. Snapshots say "same
as last time." The oracle + fuzzer say "agrees on the inputs we happened to try." **Bounded-
exhaustive says "cannot disagree, up to N"** — the first proof-shaped statement about *absence*
rather than presence, on the fragment it covers. Being bounded dodges the *decidability* questions
that make unbounded proof hard (below) — but "bounded" buys tractability of the *search*, not
cheapness of the *build*. Encode the query semantics and the SQL semantics into a solver (SMT via
Z3, or a bounded relational model finder like Alloy), assert non-equivalence, and let it search for
a counterexample DB ≤ N. No counterexample under the bound is a real, if bounded, guarantee. **This
is the highest-value formal direction for Gryphon — it reuses the oracle (the reference denotation)
and the capture seam (the emitted side) we already own.**

> **Cost caveat (Codex, 2026-07-05 — flagged and accepted).** "Reuses assets we own" is not "cheap
> now." A real harness must faithfully encode, into a solver, the semantics of: **Django-*generated*
> SQL** (not hand-written — we'd model what the ORM emits), **SQL bag semantics** (multiset, not
> set — duplicates count), **three-valued NULL logic**, **aggregation** (grouping + `COUNT`/filter),
> and Gryphon's **multi-statement captures** (a single query emits several `SELECT`s, staged — the
> capture is a *sequence*, not one statement). Each of those is a known-hard modeling problem on its
> own; together they are a **named frontier**, on par with the SQLancer/Cosette research programs,
> not a near-term bolt-on. The honest claim is *direction*, not *cost*: this is where formal effort
> should point when it is spent — and rung 0 (§8) is what to actually build now.

## 4. The when/where decision map — three regimes

This is the core of the take: formal value is not uniform across the executor's trajectory. It
concentrates, hits a wall, then re-appears in a different form.

### 4a. The read core, NOW — the formal sweet spot

The current surface is select–project–join + aggregation + a specified null logic. SQL-equivalence
provers exist for a useful slice of exactly this — the **bag-SPJ fragment under U-semirings**
(HoTTSQL/Cosette, UW: Chu, Weitz, Cheung, Suciu). And the *hard edges* of that whole literature are
**nulls/3VL and aggregation** — which are precisely Gryphon's recurring hotspots (`gryphon-findings-ledger`).
So the formal payoff lands where the bugs already live, not off in some corner. Two Gryphon assets
make this unusually reachable:

- The **2VL-literal / 3VL-field boundary** is already a *written, specified* semantics
  (`doc-dev-gryphon-vs-cypher.md` Ledger B) — a candidate to mechanize as the reference denotation
  a checker validates against, rather than an implicit rule.
- The **model oracle already is an executable denotation** of the subset. It is the reference side
  of a translation-validation check for free — provided it stays zero-shared-code with the
  executor (the property the whole ladder rests on).

Read-core is where to start, and null/3VL + aggregation is the first fragment to point a bounded-
exhaustive harness at.

### 4b. Recursion is the wall

The moment variable-length paths land (E1 → `WITH RECURSIVE` CTEs), the ground shifts. Equivalence
of recursive queries is **undecidable in general**, and the equivalence provers fall off a cliff
there. This defines the window precisely: **formalize the non-recursive core while it is still the
whole language; do not wait for E1.** For recursion itself, the honest posture is *not* proof — it
is (i) bounded-exhaustive checking of fixed unrollings (depth ≤ k over DBs ≤ N, which the small-model
argument still supports) plus (ii) **oracle-first** semantics pinned before the lowering exists
(OPP-05 in the roadmap — and note the correction: bounded `*1..3` is *rejected* today, so this is
E1-prep, exactly the right time to state the semantics a checker would use). DuckPGQ #67 — a
var-length semantic *suspected wrong in writing for years* because no oracle could settle it — is
the exhibit for why the semantics must be stated *before* the code, recursion-undecidability or not.

### 4c. Writes flip the problem — the biggest prize, eventual

If Gryphon ever grows writes (the roadmap and language spec keep them firmly out of v0), the formal
question **changes shape entirely**, and this is the most important thing to say about the future:

- Read-path formalism is about **query equivalence** (does the SQL mean the query).
- Write-path formalism is about **invariant preservation**: does a mutation keep Entity/Edge
  referential integrity, dimension scoping, FLIP/provenance coherence, no-orphan-edges — and, once
  there is any concurrency, isolation and serializability. That is a **state-transition**
  verification problem, not a query-equivalence one. The tools are different: a bounded relational
  model of the schema + operations in **Alloy**, or a **TLA+** model when concurrency enters, or
  **refinement types** on the service-layer write API.

The stakes are also different, and higher: a read bug returns wrong rows for one query; a **write
bug corrupts the graph permanently.** The comparative study is blunt on this — the entire
write/MVCC/eager-eval/visibility bug family was one of the *largest* classes in the two Postgres
peers (AgensGraph ~15 fixes over 8 years, two in its final week; AGE ~52), and it is *inexpressible*
in read-only Gryphon today (a banked credit). If writes come, that credit is spent, and this is the
one place a modest formal model earns its keep *up front* — the **cheap-edge argument** (security
posture) applies exactly: the graph invariants are easiest to state while designing the write path
and impossible to retrofit onto a mature one. Model the invariants in Alloy/TLA+ *as part of*
designing writes, or not at all.

## 5. The IR connection — why this is the study's question from the other side

The comparative study's central verdict was "shrink the glue before building an IR" (OPP-14 deferred
with trigger). The formal lens reaches the *same* conclusion from the other direction, and that
convergence is not a coincidence:

- You cannot prove much about **AST→ORM-string spaghetti**. There is no place to *state* a semantics
  and no clean boundary to *check* at.
- A clean logical-algebra **IR** would give you three things a translation validator wants: (a) a
  place to write the denotational semantics down, (b) a translation-validation boundary at IR→SQL,
  and (c) plan-rewrite rules that are themselves verifiable equivalences.
- But — and this is the load-bearing point — **the roadmap's shrink-the-glue moves buy formal
  coverage without the IR.** Every Python-side assembly that B6 converts into an ORM combinator
  (`_apply_not_exists`→anti-join, the OPTIONAL scoreboard→LEFT-join, `_merge_envelopes`→union) is
  one more construct that the *trusted-substrate + equivalence* argument can cover, instead of an
  **out-of-vocabulary zone the checker cannot reach**. The glue is precisely the part that is
  neither trusted SQL nor checkable denotation. Shrinking it *is* extending the formal frontier.

So the ordering is: **shrink the glue (B6) → state the semantics (B1 conservation invariant + OPP-05
executable var-length semantics) → prove the residue (bounded-exhaustive on the captured SQL).** The
hardening roadmap is the formal-enablement path; you do not choose between them. And when the IR is
finally built (E1 or `WITH` triggers OPP-14), **design it with a semantics in mind** — one middle
layer, invariants at construction (Cytosm is the study's warning: an IR *without* invariant
enforcement merely relocates the bugs; it does not enable proof).

## 6. What the peers actually teach about formal (from the study)

- **openCypherTranspiler** — a rented-Neo4j differential oracle whose proxies false-green where the
  lowering is weakest (§2). *Lesson: a rented oracle is noisy; an executable semantics is precise.*
- **RedisGraph** — its GraphBLAS / sparse-matrix model is the one peer whose *execution* is
  unusually amenable to **algebraic** reasoning (traversal = matrix multiply; correctness = matrix
  identities). Nobody formalized it, and it is EOL. *Lesson: amenability ≠ adoption — and it is not
  our model anyway; do not envy it.*
- **Kùzu** — factorized processing has real formal grounding (f-representations, semiring
  provenance), yet it still shipped a 56-issue wrong-result tail for want of a differential oracle.
  *Lesson: formal grounding of the **execution model** does not substitute for translation-validation
  of the **lowering**. Prove the translation, not the engine.*
- **Francis et al., SIGMOD 2018** (`arXiv:1802.09984`) — the formal denotational semantics of
  Cypher's read core. It is already the thing the model oracle is authored against; it is the
  semantic anchor any equivalence claim would cite. *Lesson: we already have a spec to check
  against, not merely derive from — the rare and valuable half.*
- **Cosette / HoTTSQL / SQLSolver** (UW lineage) — SQL-equivalence provers over the bag-SPJ
  fragment; the frontier the testing philosophy already named. *Lesson: the rung-4 aspiration is
  real but fragment-limited; nulls and aggregation are where it strains — exactly our hotspots.*

## 7. The AI angle — why "now" and not "someday"

The user's framing (the renewed, AI-era interest in proof) is not hype at this scale, for two
concrete reasons and one posture:

1. **LLMs collapse formal's historical killer — authoring cost.** The reason formal methods stayed
   niche was the human cost of writing the encodings and maintaining the semantics↔implementation
   correspondence. Auto-generating an SMT/Alloy encoding from a written semantics, and keeping the
   oracle and the spec in sync, is now cheap. The economics that kept this out of reach for a solo
   project have changed.
2. **A bounded-exhaustive equivalence gate is the correct guardrail for AI-authored lowerings.** As
   more of the executor is AI-written, an *authoring-independent* check that refuses to merge a
   lowering unless it is equivalent to the reference denotation is worth more, not less — its value
   **scales with generation volume.** This is the differential-testing insight (two independent
   implementations converge on truth) hardened into a merge gate for machine-generated code.
3. **A written semantics + solver harness is itself a Player-3 affordance** — a machine-legible,
   AI-operable correctness artifact, exactly the posture `spec-ai-integration.md` asks for. Laying
   it is the AI-legibility cheap edge applied to the compiler's own correctness.

## 8. The staged escalation ladder — what to build, and the trigger for each

Match cost to trigger. Rung 0 is near-free and should be laid now; nothing above it is built ahead
of its trigger (the over-engineering trap the whole codebase guards against).

| Rung | Build | Trigger | Cost | Note |
| :---: | --- | --- | :---: | --- |
| **0** | The denotational **semantics as an artifact** (derive the model oracle from a *written* small-step/denotational spec of the subset) + keep the **capture seam** | **Now** | S | You are ~80% here — the oracle *is* an executable semantics; the gap is writing the spec it derives from. Doubles as oracle hardening. |
| **1** | A **bounded-exhaustive equivalence harness** for the *non-recursive* read core (SMT/Alloy: emitted-SQL ≡ reference-denotation over DBs ≤ N), reusing the oracle as the denotation and the capture as the emitted side | When there is appetite for the first proof-shaped guarantee | **L / research** (not M — a named frontier per §3: Django-generated multi-statement SQL + bag + 3VL + aggregation encoding) | Start with the **null/3VL + aggregation** fragment — highest bug density, hardest by hand. First real "absent up to N." Scope it as a spike, not a sprint. |
| **2** | **Bounded unrollings + oracle-first** for variable-length; NOT a recursion-equivalence proof | **E1** (var-length) picked up | M | Undecidable to prove; bounded-check depth ≤ k, and pin the semantics before the code (OPP-05). |
| **3** | An **invariant-preservation model** (Alloy, then TLA+ for concurrency) of the service-layer graph invariants | **Writes** seriously proposed | M–L | The biggest prize; laid *while designing writes*, never retrofitted. Different problem, different tool. |
| **4** | **SQL-equivalence proving** (Cosette/SQLSolver lineage) of captured SQL vs a reference lowering — proof, not sampling | Only if rung 1 shows its bound is binding | L | Fragment-limited; aspirational. The testing-philosophy frontier's endpoint. |

**If you do one thing:** rung 0 — write the semantics down and keep the capture seam. It is nearly
free, it is *also* the roadmap's B1/OPP-05 work wearing a different hat, and it is the precondition
for every rung above it. Everything formal is gated on having a stated semantics to check against.

## 9. What NOT to do

- **Don't verify the compiler** (CompCert/Coq/Lean mechanization of the whole executor). Wrong cost
  class for a growing Python compiler; translation validation gets the guarantee that matters for
  ~1% of the effort.
- **Don't try to prove recursion equivalence.** It is undecidable; bounded-check unrollings and
  pin the semantics oracle-first instead.
- **Don't rent a stock Cypher engine as the oracle** (OPP-16, rejected). Gryphon's deliberate
  divergences make it a noisy oracle that false-greens on correct behavior.
- **Don't build any rung ahead of its trigger.** Rung 0 now; the rest on demand. Naming the frontier
  is not building it — the same discipline the testing philosophy closes on.
- **Don't treat formal as a substitute for the differential ladder.** It is a new rung *above*
  bounded sampling, not a replacement. Kùzu's 56-bug tail under principled architecture is the
  standing reminder that these are complements.

## 10. Pointers

- **The ladder this extends:** `doc-gryphon-testing-philosophy.md` (esp. §The frontier — Cosette,
  Francis et al., TLP/NoREC/PQS)
- **The structural program this shares a substrate with:** `doc-gryphon-hardening-roadmap.md`
  (B1 conservation, B6 shrink-the-glue, OPP-05 var-length semantics, OPP-14 IR trigger)
- **The evidence:** `doc-gryphon-comparative-findings.md` (OPP-16 rejected-oracle reasoning; the
  peer formal data points) + `comparanda/dossier-{opencyphertranspiler,redisgraph,kuzu}.md`
- **The semantic ground truth:** Francis et al., *Formal Semantics of Cypher*, SIGMOD 2018
  (`arXiv:1802.09984`)
- **The capture seam (the translation-validation hook):** `spec-grid-traversal-execution.md`
  (`req-grid-traversal-exec-sql-capture`); the lowering ladder (rungs 1–5) it would check
- **Null semantics to mechanize first:** `doc-dev-gryphon-vs-cypher.md` Ledger B (2VL/3VL boundary)
