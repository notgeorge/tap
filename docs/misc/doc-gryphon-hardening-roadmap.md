---
audience: [llm, developer]
covers:
  - ../../tap_grid/specs/spec-grid-traversal-language.md
  - ../../tap_grid/specs/spec-grid-traversal-execution.md
  - ../../tap_grid/specs/spec-grid-gryphon-multihop-aggregation.md
  - ../../plugins/gryphon_playground/specs/spec-gridkin-v0.md
  - doc-gryphon-comparative-findings.md
  - doc-gryphon-comparative-eval-protocol.md
assumes:
  - Reader has read doc-gryphon-comparative-findings.md (the ranked OPP-01..18 backlog + credits) and doc-gryphon-testing-philosophy.md (the existing ladder). This doc RE-RANKS that backlog against two specific goals; it does not restate the anchors — every OPP cite resolves there.
provides: |
  The decision-grade hardening roadmap for Gryphon, distilled from the ten-peer
  comparative study into two rank-ordered, bang-for-token tiers keyed to the goals
  the work actually serves: (A) be damn sure the executor works as spec'd NOW, and
  (B) give future updates the highest chance of retaining that reliability. Includes
  the meta-finding that reframes "testing" (reliability was won by structure, not
  tests), the highest-value validation PROCESSES not yet built, a concrete "do this
  first" sequence, and the sequencing traps to avoid.
---

# Gryphon Hardening & Validation Roadmap — Bang-for-Token, Ranked by Goal

> Distilled 2026-07-04 from `doc-gryphon-comparative-findings.md` (the ten-peer study) in
> answer to two questions: *what validation processes should we build that we haven't*, and
> *what are the biggest bang-for-token next steps to (A) verify the engine works as spec'd
> now and (B) keep it reliable as it grows*. Every `OPP-nn` resolves to the findings doc,
> which anchors it to a peer SHA/issue/paper. "Bang-for-token" = expected reliability gain ÷
> implementation cost in AI-authoring tokens (roughly: S ≈ one focused session, M ≈ a couple,
> L ≈ a multi-session sprint with a spec decision inside it).

## 0. The meta-finding that reframes "testing"

The single most important thing the study says about *validation* is not a technique — it is a
correction of instinct:

**Reliability, in every peer that achieved it, was won by architecture far more than by tests.**
Kùzu is the sharpest exhibit: a worst-case-optimal-join, factorized-execution engine with the
best-engineered compiler pipeline in the whole comparison set — and it still accumulated a
**56-issue wrong-result tail**, because it had no independent differential oracle. AgensGraph and
Apache AGE carry *enormous* golden-file corpora and bled silent-wrong-answer bugs for a **decade**,
because a committed golden file is a **ratchet, not an oracle** — it faithfully protects
first-write wrongness (AGE's `count(*)` fix had to *rewrite* the goldens the bug had been guarding).

Three consequences set the priorities in this whole doc:

1. **The marginal hand-authored scenario is near the bottom of the value stack.** Gryphon already
   has the strongest test ladder in the comparison set (the only independent zero-shared-code
   oracle; the only differential property fuzzer with replay; the only TLP). Adding more authored
   scenarios of shapes we already cover buys little. The study's guardrail — *don't re-import a
   rung we have* — means the "what haven't we built" list is deliberately **short**.
2. **The highest-value "validation" investments are structural.** A conservation invariant that
   makes silent predicate-drop *inexpressible* (OPP-01) is a validation win an order of magnitude
   above any test that merely *catches* a drop — because it holds for every future path too. This
   is why Goal B below is dominated by executor-architecture moves, not test moves.
3. **Where tests still matter, only two kinds pull their weight:** *authoring-independent* ones
   (oracle / fuzz / metamorphic — they fire no matter what shape a human wrote) and *ratchets*
   that force a known gap to shrink. Everything else is documentation of today's understanding.

Read Goal A as "*close the gap between spec'd and verified*" and Goal B as "*make the current
reliability survive the next feature*." Several items serve both; each is filed under its dominant
goal and cross-referenced.

---

## 1. Highest-value validation PROCESSES not yet built (answering Q1)

Ranked by value, with the honest note that #1–#2 are really *architecture that validates*, and the
lower ones are the few genuinely-new authoring-independent rungs that survived the "don't
re-import" filter. (Peer anchors: see the cited OPP in the findings doc.)

| # | Process | What it is / catches | Kind | Cost | Serves |
| :---: | --- | --- | --- | :---: | :---: |
| 1 | **Predicate/attribute conservation invariant** (OPP-01) | Every predicate leaf *and* every parsed attribute (direction, edge-type, optional flag) is consumed by exactly one lowering site or the query **rejects**. Generalizes the single-hop collapse to a global rule → silent-drop becomes inexpressible on all current *and future* paths. | Structure-as-validation | M | B (+A) |
| 2 | **Oracle-first for every new feature** + extend the model oracle over bounded `*1..3` (OPP-05) | Model the semantics in the independent oracle *before* the executor lowers them, so the code is written against a check it can't define-away. **NB (corrected): bounded `*1..3` is executor-*rejected* today (`executor.py:412,1652`), not shipped — so this is E1-readiness *prep*, not a current verification gap.** The general principle (oracle-before-lowering) applies to every future feature. | Authoring-independent | M | B (E1-prep) |
| 3 | **Must-fail ratchets for every known-broken / xfail list** (OPP-11) | Each `OracleUnmodeled` skip, fuzz known-issue, and dev-validation known-broken entry is *executed and must still fail*; the ratchet lights up the moment a bug is silently fixed or a skip becomes stale. Turns three comment-lists into shrink-forced gates. | Ratchet | S | B |
| 4 | **Pattern-direction-reversal metamorphic** (OPP-08) | Flip every arrow in a MATCH; assert the identical result set. Probes the direction/undirected dispatch surface (`_single_hop_directed`/`_redirect_single_hop`) that **TLP does not touch** and that Kùzu + GraphFrames both shipped src/dst-swap bugs on. | Authoring-independent | S | A |
| 5 | **Pairwise feature-composition fuzz coverage** (OPP-10) | Teach the generator to emit *two composed features per query* (OPTIONAL×WHERE-scope, NOT-EXISTS×multi-hop, bounded-rep×far-node-WHERE). Feature-interaction seams are the **empirically dominant peer bug locus** (GraphFrames' entire modern stream, Kùzu #4966, DuckPGQ #94). | Authoring-independent | S–M | A |
| 6 | **Generated null-matrix suite** (operator × null-position) (OPP-12) | One generated cross-product instead of per-scenario null coverage; feeds the standing null hotspot as the operator set grows. | Authoring-independent | S | A |

**Rejected/deferred processes** (recorded so they aren't re-proposed): renting a stock Cypher
engine (Neo4j/Memgraph) as a third oracle — *reject*, Gryphon's deliberate divergences make it a
**noisy** oracle (OPP-16); scenario-count conservation through corpus transforms — *reject*,
already covered by the coverage-ledger drift guard (OPP-17); NoREC — *defer*, single-hop
projections degrade to envelopes so it yields no distinct check (OPP-18).

**The honest headline for Q1:** the top two "validation processes" are the two structural moves
(OPP-01, OPP-05). The three cheap authoring-independent rungs (OPP-08/10/12) and the ratchet
(OPP-11) are the genuinely-new *test* additions and they are all **S/S–M** — cheap, and worth
doing, but they *catch*; they do not *foreclose*. Spend the structural budget first.

---

## 2. Bang-for-token hardening roadmap (answering Q2), ranked by goal

### Goal A — "Be damn sure it works as spec'd NOW" (the verification tier)

The framing that makes this tractable — **corrected after the 2026-07-04 code-check**: the
oracle's `OracleUnmodeled` skip-set is *almost* the manifest of "spec'd but unverified," but not
quite, and the difference is the whole game. Many skips (bounded `*1..3`, cross-type comparisons,
multi-step JSON paths) are skipped *because the executor also **rejects** them* — those are
fail-closed **credits**, not gaps. A real verify-now gap is only where the executor **executes**
something the oracle does **not** model. So Goal A's keystone is the audit that *separates the two*.
(This is the exact error the study's own synthesis made — it read "oracle skips bounded `*1..3`" as
"shipped but unchecked" when the feature is executor-rejected. The audit is what prevents that class
of false alarm — and finds the true ones.)

| Rank | Item | Why it's the sharpest "sure it works now" move | Effort | B4T |
| :---: | --- | --- | :---: | :---: |
| A1 | **Audit `OracleUnmodeled` vs what the executor actually executes** — publish the true "executed ∧ unverified" map | The keystone. Walk each oracle skip and each dispatch path; label every skip *executor-rejected* (credit) or *executor-executed-but-unmodeled* (real gap). You cannot claim "damn sure" without this list, and it converts the skip-set from a vague worry into a bounded worklist. Feeds A2–A5 and the OPP-11 ratchet. | S | ★★★ |
| A2 | **Pattern-direction-reversal metamorphic** (OPP-08) | Cheapest authoring-independent probe of a real *executed* dispatch surface (direction) that TLP never touches; Kùzu + GraphFrames both shipped src/dst-swap bugs here. | S | ★★★ |
| A3 | **Cyclic / duplicate-edge inflation probe** (verify-first half of OPP-03) | A single cyclic fixture + a multi-hop COUNT: does Gryphon *inflate on duplicate-edge shapes today*? This is a cheap **today-check** that both settles whether B4 is a live bug or preventive architecture, and exercises a real executed path. | S | ★★★ |
| A4 | **Pairwise-composition fuzz** (OPP-10) | Directly targets the dominant peer bug locus (feature seams: OPTIONAL×WHERE-scope, NOT-EXISTS×multi-hop); extends an asset you already own. | S–M | ★★ |
| A5 | **Generated null-matrix** (operator × null-position) (OPP-12) | Cheap exhaustive coverage of the null hotspot across the *executed* operator set. | S | ★★ |
| A6 | **Differential agreement across scan variants** (verify precursor to OPP-09) | Assert `_execute_type_scan` / `_execute_bare_type_scan` and the two order/limit appliers (`executor.py:556/665/718/1040`) agree on overlapping inputs — a today-check they haven't already diverged, *before* collapsing them. | S | ★★ |

> **Moved out of Goal A:** *oracle over bounded `*1..3`* (OPP-05) is **not** a verify-now item —
> the executor rejects bounded repetition today (`executor.py:412,1652`; rejection tests
> `test_gryphon.py:328,1440`), so there is nothing shipped to verify. It is **E1-readiness prep**
> and moves to the E1 bundle in §3.

### Goal B — "Future updates retain reliability" (the foreclosure tier)

Ranked by **structural-foreclosure-per-token**: the moves that make a bug class *inexpressible* so
a future edit (human or AI) cannot reintroduce it. This tier is where the study says the real
money is.

| Rank | Item | What it forecloses, forever | Effort | B4T |
| :---: | --- | --- | :---: | :---: |
| B1 | **Predicate/attribute conservation invariant** (OPP-01) | Silent predicate/attribute drop on *every* current and future dispatch path and future clause (WITH, per-MATCH WHERE). The keystone: generalizes the one move the testing philosophy already canonizes (§9). | M | ★★★ |
| B2 | **Must-fail ratchets** (OPP-11) | Stale known-broken entries silently hiding a regression or an accidental fix. Cheapest durability mechanism in the study. | S | ★★★ |
| B3 | **Skip-work-optimization doctrine + design-note-at-site** (OPP-13 + OPP-15) | The "transparent optimization that silently returns wrong results" class — which **every single peer** hit. A doctrine note now (soundness-argument + own-corpus + fail-closed-sentinel, or delete-don't-gate) is near-free insurance before the first fast path lands. | S | ★★★ |
| B4 | **Edge-uniqueness / row-identity at the chain choke point** (OPP-03) | **[downgraded — verify-verdict WEAK]** Forecloses a *distinct, currently-latent* duplicate-edge inflation (five peers emit this structurally). NOT "the top recurrent hotspot" — that was the far-node-WHERE **duplicate-JOIN**, a different mechanism **already fixed**. Gate on A3: if the cyclic probe shows Gryphon inflates today, this is ★★★ and needs a spec decision on repetition semantics; if not, it's preventive, bundle with E1. | M | ★★ (★★★ if A3 fires) |
| B5 | **Pin var-length as in-plan (rung-4 CTE), forbid an out-of-plan cache** (OPP-04) | The entire cache-coherence/consistency bug family that appears the moment traversal leaves the relational plan (AGE's 5-fix cache saga, AgensGraph's 2 VLE rewrites). A **spec constraint, not code** — cheapest structural foreclosure of the #1 predicted hotspot's worst failure mode. Do it while E1 is still on paper. | S | ★★★ |
| B6 | **Shrink residual glue — probe-first, don't refactor on spec** (OPP-02) | **[corrected — mostly already done]** The peers' "shrink the glue" collapse is largely *already implemented*: `_apply_not_exists` is already `~Exists()` anti-join over `_build_chain_queryset` (`executor.py:1999`), and `_execute_optional_match` is already `Count(edge, filter=Q)` over a LEFT JOIN with the filter-placement gotcha handled (`:2847`). So this is **not** a standing collapse task — it's a *probe each remaining path* task: refactor only where a function is genuinely Python-side assembly, not where it's already an ORM combinator. `_merge_envelopes` is legitimate multi-MATCH union dedup, not divergence-prone. The real generalizable win here is OPP-01/B1, not a broad collapse. | S (probe) → M (only if a probe finds real glue) | ★ |
| B7 | **Centralize null-strictness as per-operator metadata + one wrapper** (OPP-07) | A new operator can't silently re-open the 2VL/3VL class; it declares strict/non-strict and inherits the boundary from one enforced site. TLP already *probes* the boundary — this makes it *hold*. | M | ★★ |
| B8 | **One AST→AST normalization choke point** (OPP-06) | Degenerate/sugar shapes (self-loop, inline maps, anchor forms, `*1..k` expansion) collapse into the uniform path *before* dispatch, so per-shape arms (and their drop bugs) become unnecessary. Bundle with E1's expansion. | M | ★★ |
| B9 | **Collapse the scan-variant duplication** (OPP-09) | One scan lowering narrowed by label/order/limit as *data* → no sibling path to forget an application. Smaller blast radius than B1/B6. | M | ★ |

**Deferred with trigger — the full IR (OPP-14).** A thin invariant-bearing operator layer (schema-
carrying ops + throwing expression→column registry + per-operator prerequisites at one construction
choke point — Morpheus/Kùzu's real lesson, *not* a cost optimizer) is the largest structural prize,
but B1/B3/B4/B7 deliver most of its value incrementally. **Build it only when E1 var-length or
`WITH` multi-stage pipelining forces genuine multi-operator plans** — and if built, follow the
peers: exactly one middle layer (Morpheus deleted a redundant one), invariants at construction, and
plan-shape tests *beneath* (never instead of) the oracle rungs (Cytosm is the warning — an IR
*without* invariant enforcement merely relocates the bugs).

---

## 3. The "do this first" sequence (interleaving A and B by bang-for-token)

Not strict-priority order — *token-efficient* order. Lead with the near-free structural/durability
foundation, then the keystone, then the verify-now closes, then the medium structural work.

1. **The near-free foundation (all S):** B5 (in-plan var-length *constraint* — pure spec, do before
   any E1 code) · B3 (skip-work doctrine + design-note practice) · B2 (must-fail ratchets) ·
   A1 (audit: the true "executed ∧ unverified" map). One short session each; permanent leverage;
   nothing to retrofit later. A1 first — it tells you which of the rest are live vs preventive.
2. **The keystone (M):** B1 (conservation invariant). The highest structural payoff in the study;
   generalizes a move you've already proven safe on single-hop. Everything downstream is safer once
   silent-drop is inexpressible.
3. **The cheap verify-now probes (all S):** A2 (direction-reversal metamorphic) · A3 (cyclic
   duplicate-edge inflation probe) · A6 (scan-variant differential agreement). Authoring-independent,
   each exercises an *executed* dispatch surface no current rung touches — and A3's result decides
   whether B4 is a live fix or preventive.
4. **Conditionally, foreclose duplicate-edge inflation (M):** B4 (edge-uniqueness at the chain choke
   point) — **only if A3 shows Gryphon inflates today**; then spec the repetition semantics and emit
   the qual. If A3 is clean, defer B4 into the E1 bundle.
5. **Probe residual glue — don't refactor on spec (S):** B6. NOT-EXISTS and OPTIONAL are *already*
   ORM combinators (`~Exists()`, `Count(filter=Q)` LEFT JOIN); the collapse is largely done. Probe
   each remaining path and refactor only where a function is genuinely Python-side assembly — most
   are not. The generalizable win here is B1, not a broad collapse.
6. **Then, as capacity allows:** A4/A5 (composition fuzz, null-matrix), B7 (null centralization).

**The E1-readiness bundle (do together, only when var-length is picked up):** B5 (in-plan
constraint — but *record the spec line now*, step 1) · OPP-05 (oracle over bounded repetition +
var-length scenario battery, *before* the lowering code) · B8/OPP-06 (AST normalization choke
point, so `*1..k` desugars at one place). This is where the bounded-repetition work lives — it is
**not** a standing verify-now item, because nothing bounded executes today.

If only **five things** get done: **B5, B2+B3, A1, B1, A2.** Four are S, one is M; together they
record the two cheapest permanent foreclosures (B5 spec-line, B1 conservation), the durability
ratchet + doctrine (B2/B3), the honest "what's actually unverified" map (A1), and the cheapest
authoring-independent verify-now probe on an executed surface (A2). That is the maximum
reliability-per-token the study can name — and note that *four of the five are structural or
process, not tests*, which is the meta-finding (§0) made operational.

---

## 4. Sequencing traps (what NOT to do)

- **Don't build the IR now.** It's the biggest structural prize *and* the biggest token sink, and
  B1/B3/B4/B7 capture most of its value incrementally. Deferring it is the bang-for-token call.
  (OPP-14 trigger: E1 or WITH.)
- **Don't pour the budget into hand-authored scenarios.** Lowest ROI in the study; Gryphon's
  oracle+fuzzer already dominate every peer's authored corpus. New coverage should come from
  *generators and metamorphic relations* (A3/A4/A5), not hand-written cases.
- **Don't ship E1 (var-length) before its oracle (OPP-05) and its in-plan constraint (B5).** Every
  peer that lowered var-length *before* it could independently check it paid a multi-year fix tail;
  DuckPGQ #67 is the open-across-releases exhibit. Oracle-first is not optional here. (This is why
  bounded `*1..3` correctly *rejects* today rather than shipping half-checked — a credit to protect,
  not a gap to rush.)
- **Don't gate a future fast path without the OPP-13 discipline.** The "transparent optimization →
  silent wrong answer" class caught *every* peer; a soundness argument + own corpus + fail-closed
  sentinel (or deletion) is the price of admission.
- **Don't refactor "glue" that's already a combinator.** NOT-EXISTS (`~Exists()`) and OPTIONAL
  (`Count(filter=Q)` LEFT JOIN) are already ORM-combinator lowerings — the "shrink the glue" work is
  mostly *done*, a credit the synthesis under-counted. Probe before touching them (B6); and any
  collapse that *is* warranted (B8/B9) is safe only under the existing model-oracle net that made
  the single-hop collapse safe.

---

## 5. Connection to the formal-validation thread

The owed formal-validation section (`doc-gryphon-formal-validation-hot-take.md`, pending) rests on
this roadmap, not beside it. Its thesis — *bounded-exhaustive / SMT equivalence checking on the
already-captured emitted SQL* — gets **higher-coverage the more the executor stays inside ORM-
expressible constructs** (already largely true: NOT-EXISTS and OPTIONAL are ORM combinators today).
Every construct that lives as an ORM combinator rather than Python-side assembly is one the
trusted-substrate + equivalence argument can reach, instead of an out-of-vocabulary zone the checker
can't. B1's conservation invariant and OPP-05's executable var-length semantics are exactly the
*stated semantics* a translation validator checks against. In short: **the hardening roadmap and the
formal frontier share one substrate** — keep constructs ORM-expressible, state the semantics, then
prove the residue. **But note the cost caveat the formal doc now carries:** rung-0 (writing the
semantics down) is genuinely cheap; the bounded-exhaustive equivalence harness itself is a *named
frontier*, not a cheap near-term build.

## 6. Pointers

- **The evidence + anchored backlog:** `doc-gryphon-comparative-findings.md` (OPP-01..18, credits)
- **Per-system dossiers:** `comparanda/dossier-*.md`
- **Existing test ladder (don't re-import):** `doc-gryphon-testing-philosophy.md`
- **Study rubric:** `doc-gryphon-comparative-eval-protocol.md`
- **Execution seams the OPPs target:** `tap_grid/specs/spec-grid-traversal-execution.md`, `spec-grid-gryphon-multihop-aggregation.md`
- **Hotspot map:** `gryphon-findings-ledger` (agent memory)
