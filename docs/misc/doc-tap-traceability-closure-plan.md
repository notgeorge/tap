---
spec: ../../specs/spec-tap-requirement-traceability.md
audience: [developer, llm]
covers:
  - ../../specs/spec-tap-requirement-traceability.md
  - req-tap-traceability-disposition
  - req-tap-traceability-accounting
update-triggers:
  - A wave lands — mark it, update the Unaccounted numbers, and re-point "current wave"
  - The exclusion vocabulary changes (category added/removed, payload rules changed)
  - The Definition of Done is amended in the owning spec
  - A ledger ruling lands on the sphinx capability-blocks or gridkin rows (they gate batches here)
assumes:
  - The claim system as built — @<spec-hash>/<code-hash> claims, five guards, placeholder-then-resync minting
  - The review-ledger discipline (docs/misc/doc-tap-requirement-review-ledger.md)
provides: |
  The execution plan for the requirement↔code mapping project's Definition of Done: every
  requirement in the tap + plugins corpus bi-directionally mapped or documented-excluded.
  Waves, sequencing constraints, decision log, and the honest effort estimate.
---

# Requirement Traceability — Closure Plan

**Definition of Done** (canonical statement in
[spec-tap-requirement-traceability.md](../../specs/spec-tap-requirement-traceability.md) §Definition
of Done): every requirement in the tap + plugins corpus is either **bi-directionally mapped**
(implementation claim and/or test-cited ACID) or **documented excluded** (a `Trace:` disposition
from the closed vocabulary). The remainder is **Unaccounted**, counted, and ratcheting to zero —
that count is the progress bar.

Total *accounting*, never total *claiming*: scarcity governs which bucket a requirement lands in;
the DoD demands only that it lands in exactly one.

## Decision log

| Date | Decision | By |
| --- | --- | --- |
| 2026-08-20 | DoD declared: whole tap + plugins corpus, mapped-or-excluded | George |
| 2026-08-20 | Doorstop model for code-side staleness (`@<spec-hash>/<code-hash>`), placeholder-then-resync minting | George |
| 2026-08-20 | Exclusion marker lives spec-side: `Trace:` line beside `Status:` in the requirement block | George |
| 2026-08-20 | Exclusion vocabulary: `process`, `narrative`, `non-python` (mandatory path), `external` (mandatory name); doctrine/disputed/archival/mapped derived, never hand-marked | George |

## Waves

### Wave A — accounting model (DONE 2026-08-20)

The DoD into the spec's Philosophy; `req-tap-traceability-disposition` and
`req-tap-traceability-accounting` authored (`Proposed`); `req-tap-traceability-scope` amended —
the "needs no code" deferral expired when the denominator was declared. This document.

### Wave B — the engine (next)

Build what Wave A specified, in this order:

1. **Hash-neutral `Trace:` parsing first** (`req-tap-traceability-disposition-2`) — the exclusion
   from the content hash MUST land before any bulk marker application, or triage churns every
   existing claim's spec hash. This is the one hard sequencing constraint in the plan.
2. The disposition parser: closed vocabulary, near-miss fail-closed, mandatory payloads,
   evidence-contradiction and derived-bucket-rejection checks (`-1`, `-3`, `-4`).
3. The accounting: every requirement in one bucket, generated + drift-tested with per-spec
   sub-counts, Unaccounted baseline ratchet — grandfathered for existing debt, fail-closed for
   new requirements (`req-tap-traceability-accounting`).
4. Flip both requirements to `Implemented`; Validation Map rows land in the same change.

### Wave C — bulk triage, batched by spec (the long middle)

Spec-by-spec lanes, priority order: security-posture / FIPS / service-boundary → `tap_auth` /
`tap_boot` → remaining apps → the tail. For each requirement: claim it, test-cite it, or mark
its `Trace:` disposition. Candidate generation via commit co-occurrence (the RID's authoring
commit shortlists the implementing files — 75% land same-day, measured in
[doc-dev-requirement-traceability.md](doc-dev-requirement-traceability.md) §5b). Sweep findings
are leads, not verdicts — every claim minted is human-verified requirement-body-against-code,
the citation-batch discipline.

Estimate, honestly: ~1,130 core requirements; classification is lighter than deep verification,
so 100–200 per session → **6–12 sessions** for core. Citation batches 1–2 already cleared much
of `tap_grid` and `tap/`.

Gated items: claims on gryphon executor functions wait on ledger row 2 (sphinx
capability-blocks); the core↔plugin RID boundary waits on row 4 (gridkin modeling).

### Wave D — the test direction (folded into C)

Wire `@pytest.mark.spec` ACID citations where tests already exist, in the same batches — you are
already reading each requirement. `Verified` accrues where both classes land; it is the stretch
tier, not the DoD bar.

### Wave E — plugins corpus (last)

Evicted plugins carry their own specs in their own repos. The machinery ships in the core wheel
(`tap.spec_trace` already does); plugin CI gains the guards; each plugin repo drains its own
Unaccounted count against its own specs (the two-mains model). Sequenced last because the
per-repo mechanics are identical once core proves the model.

### Follow-on, on demand only

- Extending the claim grammar to `#`-comment surfaces (shell/YAML/Dockerfile) — measured first:
  the `non-python` payload inventory from Wave C is the demand signal.
- The ACID-diff prompt ("this edits acceptance criteria without a revision bump — intentional?")
  from the design doc's candidate list.

## Standing constraints

- Every claim/marker minted, never hand-typed; near-misses fail closed; one source per fact.
- An exclusion is an assertion something can check: mandatory payloads where the category names
  a thing (LOBSTER's rule).
- The branch ships via the normal promote gate; specs-tier changes ride the test_all lane.
