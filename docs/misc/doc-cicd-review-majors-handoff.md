---
spec: ../../specs/spec-cicd-hardening.md
covers:
  - req-cicd-base-image-lifecycle-1 (auto-merge tail)
  - req-cicd-dep-automation (review cycle)
---

# Handoff: Ruler-Update Review Flow (/review-majors) + Parked PRs #21/#22

Written 2026-08-09 (end of the publish/scan/protect/Renovate build day) so a fresh
session can pick this up cold. State at handoff: the full loop is live and proven —
publish→attest→scan on every main push, `main-required-checks` ruleset enforcing the
`gate` check, self-hosted Renovate in PR-only mode, dependency majors (and mypy
minors) bounded so ruler moves arrive as dedicated PRs. First lockfile refresh (#20)
merged green after the bounds landed. Background: the "MAJOR-BOUND POLICY" comment in
`pyproject.toml`, the "second road" section in `specs/spec-dev-multisession.md`, and
the Renovate wiring rationale in `.github/workflows/renovate.yml`.

## Parked PRs (the first two review customers)

**PR #22 — mypy 2.3 (major).** Take this one FIRST and skip any intermediate
mypy-1.20 PR Renovate may have opened (one triage instead of two; close the 1.20 PR
as superseded). Known content: 6 new baseline findings, of which 3 are
`tap_grid/gryphon/executor.py` `arg-type` (a known bug-locality hotspot — treat as
possibly-real, not noise). Procedure, using the SECOND ROAD (all edits go onto the
PR's own branch — one gate pass):

1. Check out the PR branch; bump `pyproject.toml` mypy bound to `>=2.3,<2.4`
   (minor-bound policy holds at the new level) and `uv lock`.
2. Run `uv run mypy .` canonically in-container (never with path args — see the
   mypy-run-canonically memory/doctrine), diff against
   `tap/guards/baselines/mypy.txt`.
3. For EACH new finding: fix the code, or append to the baseline with a judgment
   (the guard's own error message documents the escalation ladder). The gryphon
   executor arg-type trio deserves a real look before baselining.
4. Push to the PR branch; gate green → merge. Post-merge, delete the parked 1.20 PR.

**PR #21 — ruff >=0.16,<0.17.** Same shape, smaller: new 0.x = new lint rules.
First VERIFY where ruff is actually asserted in CI (the ruler classification assumed
it; if ruff isn't gated anywhere, note that in spec-cicd-hardening and decide whether
to gate it before merging rule changes). Then: fix new violations or add per-rule
ignores in `pyproject.toml` with reasons, on the PR branch, one gate pass.

## Build: /review-majors skill

Repo skill (canonical under an owning app's `skills/` dir — precedent:
`tap_boot/skills/`; wire via `scripts/wire-skills.sh`). The skill drives the review
cycle so "time to major" stops being bottlenecked on human legwork:

- Input: the open Renovate range-bump PRs (dashboard = worklist).
- Per PR: read the changelog + our actual usage of the package; run the gate if not
  already run; for ruler-class, produce the fix-vs-baseline split per finding; end
  with a one-screen accept/defer recommendation. George stays the merge authority.
- Encode the second-road rule (edits onto the PR branch) and the bound-bump step
  (majors need the pyproject ceiling raised IN the same PR).
- Cadence: weekly ritual (calendar-triggered, not event-triggered — majors rot
  silently otherwise).

## Config follow-ups (small, ride the skill wave)

- `minimumReleaseAge: "7 days"` in renovate.json5 (supply-chain soak;
  `vulnerabilityAlerts` are exempt by Renovate default — verify).
- Dependabot-alerts read permission was added to the `tap-renovate` app late on
  2026-08-09 — confirm the next run's dashboard no longer shows the
  vulnerability-alerts WARN, and that OSV PRs actually appear when an alert exists.
- The `aquasecurity/trivy-action` github-tags lookup WARN (renovate#20507 class) is
  cosmetic but watch that it doesn't block the trivy-action's own updates.
- AUTOMERGE FLIP (the end state): after ~a week of quiet signal, enable automerge
  for digest pins + patch updates only; reintroduce schedules THEN (they manage
  automerge noise; in PR-only mode they only ever deferred PRs invisibly — the
  2026-08-09 lesson, five silent runs).

## Operational gotchas (hard-won, don't rediscover)

- App permission truth: `gh api /orgs/unified-systems-com/installations` — a missing
  grant presents as branches-with-no-PRs and info-level logs say NOTHING.
- Dashboard checkboxes are consumed per-run; the PR-body `rebase-check` box +
  a `workflow_dispatch` forces a rebase. `logLevel: debug` dispatch input exists.
- Renovate config gotcha: `config:recommended` ships hidden schedules
  (lockFileMaintenance); override with `schedule: ["at any time"]` explicitly.
- Trivy findings (tap-web ×3: wheel/setuptools/jaraco.context) live in the wolfi apk
  layer — they clear when the next base-image digest PR rebuilds it; that PR is also
  the loop's first fully-automatic exercise. `.trivyignore` stays empty for these.
