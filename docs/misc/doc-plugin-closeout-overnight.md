---
title: Plugins Effort — Overnight Close-Out Plan
spec: specs/spec-tap-boot-v0.md
audience:
  - llm
  - developer
status: runbook
---

# Plugins Effort — Overnight Close-Out Plan

The fire-and-forget checklist for the `session/plugins` work discussed this session. George
triggers it once the other sessions have concluded and it is safe to run **last-session-standing**;
Claude executes Phases 0–2 autonomously, leaving the repo green and promoted at each phase boundary.
Phase 3 is a **supervised follow-on**, deliberately out of the autonomous scope (it rewires the
test/promote workflow — human eyes wanted).

## Trigger condition

Do **not** start until ALL of:

1. Every other session is concluded/promoted (`~/tap-sessions/.registry` shows only this session; no
   sibling branches with unpromoted work that would collide).
2. This session is genuinely last-standing — the type sweep (Phase 2) is a wide string-rewrite that
   collides catastrophically with any concurrent edit to tests/fixtures/GRIFT.
3. George has said go.

## Standing guardrails (apply to every phase)

- **Never promote red.** Each phase gates on a green FULL lane (`scripts/test`) before its promote.
- **Atomic per-phase promote.** Each phase commits + promotes on its own so partial success banks
  value; a later phase failing never un-banks an earlier one.
- **Leave-green-and-report.** If a phase can't reach green after a bounded number of iterations
  (~3 full-lane cycles), STOP: reset to the last green commit, leave the tree clean, write a status
  note (what was attempted, where it stuck, the failing output), and do **not** proceed to a
  dependent phase. Independent later phases may still run only if their preconditions hold.
- **Use `scripts/dc`**, never raw `docker compose`. Validate in-container; the host has no venv.
- **One thing at a time.** Do not interleave Phase 2 and Phase 3 — they both churn tests/profiles.

## Phase 0 — Preflight (gate the whole run)

1. Confirm last-standing (registry + `git branch -r` / sibling worktrees).
2. Merge fresh `origin/main` into `session/plugins`; resolve conflicts.
3. Rebuild + reset: `scripts/dc up -d --build web`, drop stale `test_*` DBs, `scripts/dc exec web uv sync`.
4. Run the FULL lane (`scripts/test`) on the merged base. **Must be green before touching anything.**
   If red on merge (someone else's breakage), stop and report — do not build on red.

## Phase 1 — Bank the staged work (low risk, do first)

Six commits are already staged + individually verified on `session/plugins`:

- `gryphon` playground profile; dropped from samsite
- headless surface-disable backlog (tap_web + tap_api)
- core auth dependency chain fix (`requests` + `django-allauth[socialaccount]`) — surfaced by the
  minimal boot; a real latent-dep fix
- `core` (zero plugins) + `core_dev` (core + grid_fixtures) profiles
- `req-boot-minimal-baseline` spec + `req-plugin-arch-core-packaging` backlog

Steps:

1. FULL lane green (from Phase 0).
2. (Optional, cheap) Live-verify `core_dev` boots — throwaway spawn `--boot core_dev`, confirm health
   + reconciliation `1 == 1`, then despawn. (`core` zero-plugin already live-verified this session.)
3. Promote (`scripts/promote-to-main.sh`).

## Phase 2 — Type-ownership rename sweep (the flagship)

The main event. Execute **`docs/misc/doc-plugin-type-sweep-runbook.md`** verbatim — decisions are
already ratified (2026-07-02): **verbatim prepend `<slug>__<name>` everywhere, no stripping**
(`aws_account → aws_core__aws_account`, edges `NAME → NAME__<slug>`, fedramp bare types prepended,
sigstore `sigstore_`/`rekor_` kept). No ratification step remains.

1. Run order per the runbook: leaves → samsite-consumed producers → `lotr` last. `lotr` now has
   **zero core ripple** (untangle severed it) — a clean per-plugin rename.
2. Context-aware rewrite (NOT blind sed): only `ENTITY_TYPE`/edge-slug *values*, `db_table` values,
   manifest keys, edge endpoints, GRIFT/fixture/expected `type` fields, Gryphon query strings. Leave
   module paths, filenames, class names alone.
3. Cross-plugin ripple: `samsite` consumes aws/github/sigstore/roscale types by string — update in the
   same atomic sweep.
4. Regenerate migrations (table renames), reset the dev DB.
5. FULL lane between iterations; the corpus is the net — a missed reference fails loud. Iterate to green.
6. Flip the type-collision lint `warn-now → fail-CI` (`req-plugin-type-collision-loud`); set
   `req-plugin-type-node-prefix` / `-edge-suffix` → Implemented in `spec-plugin-type-ownership-v0`.
7. One atomic promote.

Sizing: ~90 node + ~77 edge types across 6 plugins, dominated by string-reference substitution the
suite validates. A full night's execute-and-validate — provided it runs uncontended.

## Phase 3 — Minimal-baseline follow-on (SUPERVISED — out of autonomous scope)

`req-boot-minimal-baseline` ACs 3/4/5. **Not** part of the overnight run: it rewires the test/promote
workflow (the FULL lane's "one container, everything imported" model), which wants human review. Left
here so the full close-out set is captured. When picked up (supervised):

1. Repoint the default spawn/entrypoint profile `base → core` (`spawn-session.sh`, `docker-entrypoint`
   default, docs, the `test_shipped_profiles_exist`/tap_boot tests that reference `"base"`).
2. Retire `base`: rename → `test_all` (the transitional union); point the FULL-lane/promote-gate test
   invocation at `test_all` explicitly (it can no longer rely on the default, which is now empty `core`).
3. Tier plugin tests into per-plugin profiles (`core` + `grid_fixtures` + one plugin each — the
   `gryphon` profile is the pattern); reclassify fleet-asserting tests (e.g.
   `tap_plugins/tests/test_report.py`) to the `test_all` tier. Restructure `scripts/test` to run the
   tiers (core_dev / per-plugin / test_all).
4. Remove `base`/`test_all` once every tier has a home. Mark the ACs Implemented.

Pairs with `req-dev-validation-suite-tiers`.

## Explicitly NOT in this close-out

- Building the headless toggle (`req-web-rendering-headless` + tap_api) — backlog build, demand-gated.
- Core apps as workspace members (`req-plugin-arch-core-packaging`) — backlog, downstream of
  app-interdependency reduction.
- Slim-install / airgapped wheelhouse — backlog, demand-gated.

## Definition of done (overnight = Phases 0–2)

`origin/main` carries: the gryphon/core/core_dev profiles + the auth-deps fix + the specs (Phase 1),
and the completed type-ownership sweep with the collision lint flipped to fail-CI (Phase 2) — all
behind green FULL lanes, each phase atomically promoted. Phase 3 remains open as a supervised
follow-on with a clear status note if anything stuck.
