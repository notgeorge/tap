---
audience: [llm, developer]
covers:
  - ../doc-gryphon-commandments.md
  - doc-gryphon-testing-philosophy.md
  - doc-gryphon-formal-validation-hot-take.md
  - ../../plugins/gryphon_playground/specs/spec-gridkin-v0.md
assumes:
  - Reader knows Gryphon (a Cypher-subset language compiling to ORM→SQL, read-only) and its dev-time validation ladder (gridkin scenarios + zero-shared-code model oracle + property fuzzer + TLP — doc-gryphon-testing-philosophy.md)
  - This is an IDEA doc for future consideration, not a spec or a commitment. Nothing here is built.
provides: |
  The concept of "battle-hardening" — on-instance, per-query, live-data, AI-assisted
  validation (and optimization/relief-valve advising) of the specific Gryphon queries a
  customer actually runs — its animating thesis (particular accuracy over general
  accuracy), how it maps onto TAP's existing validation assets, a prior-art map showing
  the spine is field-proven and the AI discipline is settled, what to steal vs avoid, and
  the open questions to resolve before it becomes a spec.
---

# Gryphon Battle-Hardening — Particular Accuracy On-Instance (Idea Doc)

> An idea doc for **future consideration**. Nothing here is built or committed. It captures a
> concept ("battle-hardening"), synthesizes the prior art (a ten-source parallel sweep,
> 2026-07-05), and maps both onto TAP's existing spine so a future spec has a running start.
> The animating thesis is the user's, verbatim: *"I don't need Gryphon to be generally accurate,
> I just need it to be particularly accurate."*

## 1. Thesis — particular accuracy, not general accuracy

Gryphon is a general-purpose graph query language. But **any given customer authors only a tiny
subset of what the grammar can express** — a handful of real queries, often on the critical path
of a real decision. That observation reframes what "correct" has to mean:

- **General accuracy** — the whole grammar, all inputs, correct — is the Dijkstra trap: asymptotic,
  never provably complete, testing shows only the *presence* of bugs. It is the right *floor*
  (the commandments and the dev-time ladder maintain it) but it is unreachable as a *guarantee*.
- **Particular accuracy** — *this* query, on *this* grid's data, at *this* consequence level, is
  correct — is **bounded and verifiable**. You genuinely *can* be damn sure about a specific query
  against specific data. That is a claim you can *make*, not merely approach.

Battle-hardening is the machinery for buying particular accuracy on demand. It is the **runtime,
per-query, live-data cousin** of the dev-time gridkin + model-oracle + fuzzer ladder — the same
differential-oracle spine, relocated to the customer instance and pointed at the queries that
carry real consequence. Three framing moves fall out of the thesis:

1. **It inverts the coverage problem.** Dev-time assurance spreads thin across the whole grammar;
   battle-hardening concentrates the *entire* assurance budget on the few queries that matter —
   assurance proportional to consequence, the discipline safety-critical engineering already
   formalizes (DO-178C design-assurance levels; risk-based testing).
2. **It legitimizes the relief valve.** If the goal were "Gryphon expresses everything correctly,"
   dropping a query to raw ORM or a hand-written module would be a defeat. But the goal is "*this
   decision is backed by a correct answer*." So if a critical query cannot be made *particularly*
   accurate in Gryphon cheaply, moving it to a battle-hardened ORM/module is a rational, honest
   outcome — still surfaced as a demand signal to grow Gryphon ([GRY-LANG-5](../doc-gryphon-commandments.md)),
   but no longer a source of shame.
3. **It is a concentration of assurance, not a replacement for the floor.** Every particular query
   still rides the general executor, so a general bug can surface in a query nobody has hardened
   yet. Battle-hardening's auto-raise-to-ledger ([GRY-TEST-7](../doc-gryphon-commandments.md)) is
   the mechanism that feeds particular findings back into *general* improvement: *particularly
   accurate now, and generally better because of it.*

## 2. What battle-hardening is — three functions

For a specific authored query (say, a critical-path search flagged by the user or the onboard AI):

- **Generate-from-intent.** Read the query, the live grid schema, the actual data distribution, the
  existing gridkin scenarios, and optional user "expectations about the future," and synthesize
  validation scenarios *for that query* — metamorphic relations (TLP partitions, direction-reversal,
  graph-structure relations) plus boundary/edge cases the query's intent implies. This is where the
  AI (Player 3) earns its keep.
- **Validate.** Run the query differentially — Gryphon vs the independent model oracle, and/or vs an
  equivalent raw-ORM formulation — over live + synthesized data, and **auto-raise** into the findings
  ledger on any divergence that survives noise-cancellation. This is the existing oracle/fuzzer,
  relocated on-instance and aimed at one real query.
- **Advise / relief-valve.** Detect when the query would be better served by raw ORM or a hand-written
  module, and say so — a *validated* escape hatch (prove the alternative returns the same answer before
  trusting it). The preference remains to improve Gryphon for everyone; the escape is a governed
  exception, not a silent bypass generator.

It runs **read-only, on the host instance, out-of-band** of the live request — which Gryphon's
read-only construction ([GRY-ARCH-7](../doc-gryphon-commandments.md)) makes safe by default.

## 3. How it maps onto what TAP already has

Battle-hardening is mostly a *relocation and composition* of assets TAP already owns — which is why
it is plausible rather than speculative:

| Battle-hardening needs | TAP already has | Note |
| --- | --- | --- |
| An independent reference to diff against | The **zero-shared-code model oracle** (`gridkin/model_oracle.py`) | The "second engine" most prior-art tools *lack*; TAP ships it. Must stay zero-shared-code on-instance ([GRY-TEST-2](../doc-gryphon-commandments.md)). |
| A wrong-answer verdict without a second engine | **TLP** (2VL/3VL partitioning) + the property fuzzer | Metamorphic oracles give a verdict on a single query with no second engine (see prior art). |
| A place to raise detected bugs | The **findings ledger** + [GRY-TEST-7](../doc-gryphon-commandments.md) (never normalize a Gryphon wrong-answer) | Auto-raise is the runtime feed into the same ledger dev-time uses. |
| Safety on live data | **Read-only execution** (`search_readonly`) | Istio-mirror-level isolation for free; a hardening run cannot mutate state. |
| A "should this leave Gryphon?" signal | [GRY-LANG-5](../doc-gryphon-commandments.md) ("raw-ORM reach is a demand signal") | The relief-valve *is* GRY-LANG-5 automated and validated. |
| An authored-scenario format | **Gridkin** (fixture + query + expected envelope + expected SQL) | The unit a generated case would materialize into; gridkin is the dev-time analog of the whole loop. |
| An AI actor to run it | **Player-3 posture** (`spec-ai-integration.md`) | The onboard AI proposing hardening for high-consequence queries is exactly the named AI consumer. |

The **net-new** part — what no single prior-art system does as a whole — is the *composition*:
per-query + live-data + **translation-fidelity** validation (not data-quality, not
service-behavior) + AI-generate-from-intent + validated relief-valve, on the customer instance.
The pieces are all field-proven; the assembly is the novelty.

## 4. Prior art — the spine is field-proven, the AI discipline is settled

A parallel sweep across six domains (production-differential testing, assured LLM test-gen,
data-expectation frameworks, DBMS metamorphic testing, contract/workload testing, query advisors)
returned a consistent picture. Two findings dominate.

**(A) The spine — differential comparison against an independent reference on live data — is a
decade-proven pattern for catching *silently-wrong* results**, in exactly Gryphon's shape:

- **Twitter Diffy** — multicasts each live request to primary/candidate/shadow and diffs; uses the
  primary-vs-shadow diff as **noise cancellation** so it flags only meaningful regressions. *Steal:*
  the noise-cancellation trick is how battle-hardening decides an oracle mismatch is a real bug vs.
  incidental ordering/timestamp variance. (github.com/opendiffy/diffy)
- **GitHub Scientist** — wraps a critical path in control (old) + candidate (new), runs both on real
  calls, always returns control, compares asynchronously. *This is the validated relief-valve,
  exactly*: Gryphon = control, raw-ORM/module = candidate; cut over only when diffs are clean.
  (github.com/github/scientist)
- **Kayenta / Spinnaker Automated Canary Analysis** — a statistical judge scores the diff and routes
  **success / marginal / failure** → auto-promote / **escalate-to-human** / auto-rollback. *Steal:*
  the marginal→human tier is the design for "suspect but not certain" Gryphon divergences.
- **Istio/Envoy traffic mirroring** — fire-and-forget shadow, responses discarded, zero user impact.
  *Steal:* the safety posture for running validation against live data (Gryphon's read-only makes it
  even safer). **GoReplay** is the capture/replay substrate; **Datafold data-diff** does value-level
  result-set diffing with recursive-checksum bisection to localize the exact differing row/predicate.
- **SQLxDiff / GDBMeter / Gamera / SQLancer (TLP/NoREC/PQS)** — the academic core: an independent
  reference (or a metamorphic relation) over the *same query* catching silent logic bugs. **GDBMeter**
  is a query-partitioning metamorphic oracle over *Cypher-shaped* queries — the closest analog to
  Gryphon; **Gamera** builds *graph-aware* metamorphic relations (paths, neighborhoods). *Key insight:*
  **metamorphic/equivalence oracles are the only way to get a wrong-answer verdict without a second
  engine, and they apply to a single authored query over real data** — and TAP already has *both* a
  second engine (the model oracle) *and* TLP, so it starts ahead.

**(B) The AI discipline is unanimous: let the LLM generate candidates; never let it be its own
judge.** Every credible AI-test-gen system pairs LLM creativity with an *independent, deterministic*
filter:

- **Meta TestGen-LLM (assured offline LLMSE)** — the LLM proposes tests; a deterministic filter keeps
  **only** those that build, pass, and raise coverage. The canonical "assured" pattern battle-hardening
  must mirror: a generated scenario is kept only if it survives the independent oracle. **Qodo
  Cover-Agent** is the open-source, model-agnostic (LiteLLM) implementation you could embed in a
  plugin.
- **E-Test (ICSE 2026)** — LLMs (1) detect *production* execution scenarios the test suite doesn't
  cover, then (2) generate cases for them. The **closest published work to battle-hardening's core
  loop**: compare authored usage to existing coverage (≈ gridkin scenarios), LLM-generate the gap.
- **Argus** (LLM discovers test *oracles* for DBMSs), **ShQveL** (LLM widens SQL feature coverage
  while a deterministic metamorphic oracle judges), **OSS-Fuzz-Gen** (LLM writes fuzz targets for an
  under-fuzzed high-value region), **Fuzz4All** (LLM takes NL/example *intent* + user guidance →
  synthesizes inputs — literally generate-from-intent). *Contrast note:* **pganalyze deliberately does
  NOT use an LLM** for its query/index advisor — a credibility signal that the *validation* half
  should stay deterministic even as the *generation* half goes AI.
- The whole **data-quality industry has already built battle-hardening's NL loop**: **Great
  Expectations + ExpectAI**, **Soda + SodaGPT**, **AWS Deequ** (profile→suggest→human-review),
  **Monte Carlo** (runtime, live-data, auto-raise) — *profile live data → user/LLM states intent in
  natural language → generate editable assertions → run on live data → auto-raise*. Battle-hardening
  is that exact loop applied to a query language's **correctness** instead of a warehouse's data
  quality. **dbt unit tests** (mocked input + expected output) are the closest existing pattern to a
  customer-authored gridkin scenario.

**(C) "Particular, not general" is itself prior art.** **Pact / consumer-driven contract testing**
formalizes "test only the subset the consumer actually exercises, derived from real usage."
**AutoGraphQL (ASSERT-KTH)** harvests *real production queries* to auto-derive tests for a query
language (GraphQL) — the nearest non-LLM analog to battle-hardening's harvest-real-queries loop.
**SQLsmith / Schemathesis** seed generation from a live schema.

**(D) The relief-valve/optimize half is also proven.** **Oracle SQL Tuning Advisor** targets one
statement and validates its recommendation empirically; **Bao (MIT)** is architecturally "a validated
learned override on top of a general optimizer" — the exact "validated escape hatch on a general
engine" shape; **R-Bot / LLM-R2 / GenRewrite** are LLM query-rewrite advisors, and the sound ones
**verify equivalence before trusting the rewrite**; **AMOEBA** generates equivalent query pairs (the
machinery for "is there a better-but-equivalent formulation?").

## 5. What to steal, what to avoid

**Steal:**
- **Assured generation** (TestGen-LLM): LLM generates, independent oracle judges, keep-only-what-holds.
  Non-negotiable — it is the difference between hardening and hallucinated confidence.
- **Noise cancellation** (Diffy): subtract inherent non-determinism (ordering, LIMIT-without-ORDER-BY,
  timestamps) before calling a divergence a bug — otherwise every run is a false alarm.
- **Judge-and-route with a human tier** (Kayenta): success → record; marginal → escalate to user/AI;
  failure → auto-raise. Don't binary-classify a probabilistic signal.
- **Metamorphic-oracle-per-query** (GDBMeter/Gamera/TLP): the way to a verdict on one query with no
  second engine — and a way to keep generation honest when the model oracle can't model a shape.
- **Validated relief valve** (Scientist): never cut a query over to ORM/module without a clean
  differential first.
- **Deterministic validation, AI generation** (pganalyze contrast): the AI proposes; the math decides.

**Avoid:**
- **LLM-as-its-own-judge** — the failure mode the whole assured-testing literature exists to prevent.
- **Self-healing that hides real bugs** (Mabl/Testim boundary): an AI that "adapts the test when the
  app changes" must never silently absorb a *genuine* regression. Battle-hardening adapts scenarios to
  *data* change, never to executor-behavior change.
- **Relief-valve sprawl** — an escape hatch that fragments the canonical read path. Every escape is a
  logged GRY-LANG-5 demand signal, reviewed, and preferentially closed by growing Gryphon.
- **Trusting a rewrite advisor's equivalence claim** — verify it (AMOEBA/differential), don't assume it.

## 6. Open questions for future consideration

- **Privacy.** Generating scenarios from *real customer data* on a customer instance: what leaves the
  instance (nothing, ideally — hardening is local), what the AI generator may see, how synthesized
  fixtures are scrubbed if ever exported to the general corpus.
- **On-instance oracle independence.** The model oracle would ship to the instance and **must stay
  zero-shared-code** with the executor ([GRY-TEST-2](../doc-gryphon-commandments.md)) — the guarantee
  is worthless the moment they share lowering. Does the oracle model enough of the *specific* query's
  shape, or does it `OracleUnmodeled`-skip it (in which case metamorphic relations carry the load)?
- **"Expectations about the future" = a customer-authored contract.** This is the dbt/GE/Pact insight:
  the user's guidance *is* a spec. What is its format (declarative expectations? example rows? NL the
  AI compiles?), and how is it versioned against grid evolution?
- **The marginal tier.** Who adjudicates "suspect but not certain" — the user, the onboard AI, or a
  ratchet? (Kayenta routes to a human; TAP's Player-3 posture suggests the AI triages, the human
  rules.)
- **Cost/cadence on a live instance.** When does hardening run — on query authorship, on a schedule,
  on data-distribution drift, on demand? What is the budget, and is it proportional to the query's
  declared consequence tier?
- **Relief-valve governance.** The escape must be a *governed exception* with an owner and a review,
  not an easy default — or the canonical read path erodes.
- **Relationship to the formal thread.** Battle-hardening is the *empirical, data-driven, per-query*
  cousin of `doc-gryphon-formal-validation-hot-take.md`'s bounded-exhaustive equivalence. They share a
  substrate (an executable semantics + the capture seam); the formal harness proves a *fragment* for
  *all* small data, battle-hardening proves a *specific query* for *this* data and *plausible* future
  data. They compose: formal for the language, battle-hardening for the query-in-context.

## 7. Prior-art index

| System | Cluster | AI? | Informs | Cite |
| --- | --- | :---: | --- | --- |
| Twitter Diffy | prod-differential | no | validate + noise-cancellation | github.com/opendiffy/diffy |
| GitHub Scientist | prod-differential | no | relief-valve (validated escape hatch) | github.com/github/scientist |
| Kayenta (Spinnaker ACA) | prod-differential | statistical | judge-and-route + human tier | github.com/spinnaker/kayenta |
| Istio/Envoy mirroring; GoReplay | prod-differential | no | on-instance safety; capture/replay | istio.io traffic-mirroring; github.com/buger/goreplay |
| Datafold data-diff | prod-differential | no (OSS core) | result-set diff + row localization | github.com/datafold/data-diff |
| SQLxDiff | prod/dbms | minor | reference-oracle-over-SQL, auto-raise | arxiv.org/abs/2501.01236 |
| E-Test (ICSE 2026) | assured-llm | core LLM | generate-from-production-gap | E-Test, ICSE 2026 |
| Meta TestGen-LLM; Qodo Cover-Agent | assured-llm | core LLM | **assured** generate+keep-only-passing | arxiv.org/abs/2402.09171; github.com/qodo-ai/qodo-cover |
| OSS-Fuzz-Gen; Fuzz4All | assured-llm | core LLM | LLM-writes-target; generate-from-intent | github.com/google/oss-fuzz-gen; Fuzz4All (ICSE'24) |
| Argus; ShQveL; MIST | dbms-metamorphic | core LLM | LLM oracle/query generation for DBMSs | arxiv.org/abs/2510.06663; ShQveL; MIST |
| SQLancer (TLP/NoREC/PQS) | dbms-metamorphic | no | single-query metamorphic oracle | github.com/sqlancer/sqlancer |
| GDBMeter; Gamera | dbms-metamorphic | no | **graph/Cypher** metamorphic oracle | GDBMeter; Gamera (graph MRs) |
| AMOEBA | dbms/advisors | no | equivalent-query mutation (optimize) | AMOEBA, ICSE 2022 (39 perf bugs) |
| Great Expectations + ExpectAI; Soda + SodaGPT | data-expectations | LLM assist | NL-intent → editable assertions on live data | greatexpectations.io; soda.io |
| AWS Deequ; Monte Carlo | data-expectations | stat / LLM | profile→suggest→review; runtime auto-raise | github.com/awslabs/deequ; montecarlodata.com |
| dbt tests + dbt unit tests | data-expectations | no (core) | assertion-on-output; mocked-input scenario | docs.getdbt.com |
| Pact + Pact Broker | contract | no | consumer-driven "particular not general" | pact.io |
| AutoGraphQL (ASSERT-KTH) | contract | no | harvest real queries → auto tests | ASSERT-KTH/AutoGraphQL |
| Schemathesis; Dredd; SQLsmith | contract/fuzz | no | schema/grammar-seeded generation | schemathesis.io; github.com/anse1/sqlsmith |
| Oracle SQL Tuning Advisor; pganalyze; Bao; R-Bot/LLM-R2 | advisors | mixed | per-query optimize advisor (validate first) | Oracle docs; pganalyze.com; Bao (SIGMOD'21) |

*Verify-pass corrections folded in:* "Argus" and "Automated Discovery of Test Oracles for DBMS Using
LLMs" are the same paper (arXiv:2510.06663); AMOEBA reported ~39 potential performance bugs (not 20).

## 8. Pointers

- **The doctrine it extends:** `doc-gryphon-commandments.md` (esp. GRY-TEST-2/7, GRY-LANG-5, GRY-ARCH-7)
- **The dev-time ladder it relocates:** `doc-gryphon-testing-philosophy.md`
- **Its formal cousin:** `doc-gryphon-formal-validation-hot-take.md`
- **The scenario format a generated case materializes into:** `spec-gridkin-v0.md`
- **The AI actor that would run it:** `spec-ai-integration.md` (Player 3)
- **Where auto-raised findings land:** `gryphon-findings-ledger` (agent memory)
