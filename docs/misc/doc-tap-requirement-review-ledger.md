---
spec: ../../specs/spec-tap-requirement-traceability.md
audience: [developer, llm]
covers:
  - ../../specs/spec-tap-requirement-traceability.md
  - req-tap-traceability-scope
  - req-tap-traceability-disputed
update-triggers:
  - A collapse, refactor, or audit finds code making a choice no requirement governs — add a row here and the detail section in the owning spec
  - A requirement is marked `Disputed` — add its row here in the same change (req-tap-traceability-disputed-3)
  - A listed decision is made — record the outcome in the owning spec, then strike the row
  - An owning spec's "Requirement Review Needed" section is renamed or moved
---

# Requirement Review Ledger

Places where the code makes a choice **no requirement governs**, and someone has to decide
what the requirement should be. This file is the index only — each entry's evidence and
open questions live in a `## Requirement Review Needed` section in the **owning spec**,
because that is where the answer will eventually be written.

## Why this exists

A fact with no governing requirement is a signal, not an obstacle. Either the fact is not
one, or a requirement is missing — and both want a conversation rather than an edit. The
rule that produced this ledger: **when a collapse or a cleanup has no governing
requirement, stop and record it here instead of deciding in the moment.**

It earned its place immediately. The `cytoscape:cose` entry below was collapsed to a single
constant on 2026-08-14 and reverted the same day: the eight sites shared a *value*, not a
*fact*, and merging them coupled a view's own choice of layout algorithm to an unrelated
fallback. No requirement existed to catch that — its absence was the warning.

**The discriminator**, when judging whether sites share a fact: *if the fact changed, would
every site want to change together?* Same purpose is not required — the secret-file suffix
is read by three callers that find, load, and refuse-to-commit, and a rename must move all
three. Same value is not sufficient — see below.

## Ledger rows come in two kinds

1. **Ungoverned choice** — code makes a choice no requirement governs (the placement entry
   below). The question is whether a requirement should exist.
2. **Disputed requirement** — a requirement exists and its implementation disagrees with it.
   The spec entry carries `Status: Disputed` (`req-tap-traceability-disputed`), the owning
   spec's `Requirement Review Needed` section names the code site and the disagreement, and
   the row lands here in the same change. The question is which side is right.

Both kinds resolve the same way: a human ruling recorded in the owning spec, then the row
moves to Resolved.

## Open

| # | Kind | Decision | Owning spec | Surfaced |
| :---: | --- | --- | --- | :---: |
| 1 | Ungoverned choice | Default graph placement — is `cytoscape:cose` a system-wide default, a per-consumer choice, or neither? | [spec-viz-panel.md](../../tap_viz/specs/spec-viz-panel.md) → *Requirement Review Needed* → Default graph placement | 2026-08-14 |

## Related backlogs

These carry their own pre-identified decision points; they are **not** duplicated into the
table above until one is actually opened.

- [doc-duplicate-derivation-backlog.md](doc-duplicate-derivation-backlog.md) — Tier 3 is
  seven findings explicitly flagged "needs a decision before editing"; Tier 4 is three
  refactors. Working a tier is the moment to check whether a finding belongs here instead.

## Resolved

*(none yet — record the outcome in the owning spec, then move the row here with its date)*
