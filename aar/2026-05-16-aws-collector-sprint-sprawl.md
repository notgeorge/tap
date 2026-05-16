# AAR — AWS Collector Sprint Sprawl

| | |
| --- | --- |
| **Date** | 2026-05-16 (incident span ~2 days) |
| **Severity** | Medium — no data loss; ~2 dev-days of churn; stated goal unmet |
| **Status** | Recovered; corrective actions open |
| **Author** | Claude (`session/codex-prime`) |
| **Critical-path authority** | Pending strategy doc (separate session); see Corrective Actions |

This is the first report filed under `aar/`. Its section structure is the
intended standard for future after-action reports (see *Standardized Format*
at the end).

## 1. Goal vs. Outcome (read this first)

**Goal:** "Get the AWS Steampipe collector working" — verify it against a real
AWS account.

**Outcome:** The collector is **still unverified**. The ~2 days produced,
all *off the roadmap critical path* but useful eventually:

- async collector self-test contract + default-on phase-1 run gate
- AWS collector zero-config secret-discovery pivot
- doc-reference resolution architecture (3-concern split, all Backlog)
- sandbox-aware test exclusion backlog
- a full spec reconciliation pass + anti-pattern rules in AGENTS.md/memory

One sentence: *we sat down to verify one collector and stood up three pieces
of adjacent infrastructure while the original question — does the collector
work — went unanswered.*

## 2. Timeline

- Autonomy granted to codex on a loosely-specified, critical-path task
  ("make the collector work"), with no definition-of-done, scope fence, or
  commit cadence.
- Codex drift accumulated, uncommitted: plugin config written into
  `docker-compose.yml`; an unjustified `boto3` dependency added when
  Steampipe was already the standard; an unprompted revert of
  `run_collection`'s task backend to an `ImmediateBackend` branch
  (violating an `Implemented` requirement); a Python-2 `except` syntax
  error left in a panel module; multi-spec drift
  (`grift_batches`↔`PRODUCED_BATCH`, dangling "future docs surface");
  a duplicate logging site-ID.
- **Detection was luck:** the operator noticed odd config variables in the
  compose file, not a gate or a test.
- Codex exhausted its token budget mid-flight, forcing an unplanned handoff
  with the work as a single uncommitted, unattributable blob.
- Claude recovery: spec review + reconciliation, revert of the
  spec-violating backend change, the zero-config pivot, the self-test
  build, and finally a clean 6-commit series. **The recovery itself
  drifted off the critical path** (designed and *built* the self-test
  capability rather than parking it).

## 3. What Went Well

- Recovery quality: specs are now internally consistent, the work is a
  clean atomic commit series, and the anti-patterns are captured as durable
  rules (AGENTS.md + agent memory + the new-plugin skill).
- The cross-session logging merge is being handled with an explicit
  ownership rule and a verification protocol rather than a blind merge.
- The off-path artifacts were *deferred deliberately* (Backlog RIDs with
  named seams) rather than left as silent half-work.

## 4. What Went Wrong

- The original acceptance criterion was never met; the collector is
  unverified.
- ~2 dev-days produced net-zero on the roadmap critical path.
- Anti-patterns were caught by human vigilance on a diff, not by any
  automated or review gate — i.e. detection is currently unreliable.
- A hard syntax error survived because no test imported the affected
  module; the test suite gave false confidence.

## 5. Root Causes (blameless, multi-cause)

No single cause; the failure was the *combination*:

1. **Progress pressure.** A desire to show daily output made unsupervised
   autonomy on the critical path feel acceptable.
2. **No definition-of-done.** "Collector works" was never expressed as a
   checkable acceptance criterion.
3. **R&D and delivery conflated.** "See what codex can do" (exploration)
   and "ship the collector" (delivery) ran on the same live branch, so
   exploration had no blast-radius limit.
4. **No scope fence / stop conditions.** The agent was not told to stop and
   ask before adding a dependency, editing core infra, or changing a spec.
5. **No incremental-commit discipline.** Zero commits turned a routine
   token timeout into an unattributable blob and made bad changes
   non-atomic to revert.
6. **Spec looseness.** Underspecified areas (collector config) were vacuums
   that an autonomous agent filled with anti-patterns.
7. **Existing discipline not enforced.** A standing rule
   (`feedback-future-seam-discipline`: name premature ideas as a seam and
   defer, don't build) already covered the self-test sprawl. It was not
   applied. This is an **enforcement gap, not a knowledge gap** — the most
   important finding.

On *"codex can't be allowed to just cook"*: the evidence supports
codex-specific guardrails (it produced the dependency, core-infra, spec
violation, and syntax-error failures, and never committed). But that is
**necessary and insufficient** — the same loose-spec / no-fence / no-commit
setup sprawled under Claude during recovery too. The systemic fix is
process discipline; tighter codex autonomy is one corrective among several,
not the conclusion.

## 6. Impact

~2 dev-days of churn; stated goal unmet; net-positive but off-roadmap
artifacts produced; a delicate cross-session logging merge now required to
land the recovery.

## 7. Corrective / Preventive Actions

- [ ] **Define-done before any autonomous run.** No agent starts a
      critical-path task without a written, checkable acceptance criterion.
      Resolves to the strategy doc once it exists.
- [ ] **Scope fence + stop conditions in the agent prompt.** Explicit
      "stop and ask before: new dependency, core-infra/`docker-compose`
      edit, spec change."
- [ ] **Mandatory incremental commits for autonomous runs** — logical
      units, so a timeout degrades gracefully and reverts stay atomic.
- [ ] **R&D only on a throwaway branch.** "See what it can do" never runs
      on a delivery branch.
- [ ] **Pre-merge anti-pattern gate** so detection is a check, not luck
      (compose-config, undeclared deps, spec contradictions, syntax).
- [ ] **Recovery discipline.** When untangling, triage to the critical
      path and *park the rest as backlog before building it*; enforce the
      future-seam rule.
- [ ] **Next action is set by the strategy doc, not by assumption.**
      *(Self-correction: an earlier draft of this AAR pre-committed "verify
      the collector next" — that repeats root cause #2/#4. The next action
      will be chosen from the incoming strategy doc, which is canonical for
      sequence/priority. Until it lands, no new scope is started.)*

## 8. Lessons → Durable Rules

- Agent memory: autonomy without definition-of-done + scope-fence +
  incremental-commits sprawls; conflating R&D and delivery on a live branch
  is the failure mode; codex specifically needs guardrails. (Mirrored to
  AGENTS.md per the established mirror rule — deferred to a post-merge
  commit to avoid adding pre-merge delta to a branch facing a delicate
  cross-session merge: practicing the discipline this report is about.)
- This document's structure is the standardized AAR format.

## Standardized Format (for future reports)

Every AAR under `aar/` uses these sections, in order:

1. **Goal vs. Outcome** — one sentence, first. What we set out to do vs.
   what we got.
2. **Timeline** — terse, factual.
3. **What Went Well** — name it; recovery and good calls count.
4. **What Went Wrong** — including where detection/tests gave false
   confidence.
5. **Root Causes** — *blameless and plural*. No single scapegoat; include
   process and spec causes, not just "the agent."
6. **Impact** — time, scope, roadmap effect.
7. **Corrective / Preventive Actions** — owned, checkable items.
8. **Lessons → Durable Rules** — the report is not closed until lessons are
   mirrored to agent memory and AGENTS.md.

Filing convention: `aar/<YYYY-MM-DD>-<short-slug>.md`.
