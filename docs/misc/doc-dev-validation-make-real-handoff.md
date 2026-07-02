# Handoff — make the dev-validation system real

Session-priming note for the fresh session that picks up the validation build.
Not authoritative spec (`specs/spec-dev-validation.md` is). Versioning is git.

**Goal:** discuss and then make TAP's development-validation system real — move
`spec-dev-validation.md` from mostly-Proposed to built, scoped deliberately (don't
overbuild; server-side CI is post-July). The keystone is the cold-boot smoke gate +
its promote-path enforcement.

## Ground first (in this order — per the "ground in canon" discipline)

1. **`specs/spec-dev-validation.md`** — the center of gravity. Read every
   requirement + the Validation Map. Status today: `collection-complete` =
   Implemented; ALL others Proposed (map, smoke-gate, real-backend, canary-tier,
   known-broken, promote-hook, ratchet-harness, suite-tiers).
2. **`tap_cares/management/commands/dev_validation_spike.py`** — the Phase-0 spike.
   ALREADY PROVES the load-bearing mechanism: a collector driven through the REAL
   `SteadyQueueBackend` via an in-process drain (dispatch→claim→perform), with teeth
   (`--skip-drain` ⇒ job stays READY ⇒ non-zero exit). Phase 1 wraps this into the
   ordered cold-boot cycle.
3. **`specs/spec-dev-multisession.md` `req-dev-multisession-promote-gate`** — the
   reciprocal. `scripts/promote-to-main.sh` is the wiring point: the gate runs
   between Step 2 (pre-push merge) and Step 3 (atomic push).
4. **`plan/road-rampart.md`** active step + doctrine (strategic filter).
5. **`docs/misc/doc-dev-validation-enterprise-ci-strategy.md`** — the longer-horizon
   "outside the laptop" sibling (server CI, PR-gated promote, AI-in-pipeline).
   Optional deeper reading; trigger-gated, NOT this scope.
6. MEMORY entry "Validation: xdist lanes + read-only Flaw promoted" — latest state.

## Current state (real vs to-build)

- **REAL:** Validation Map + collection-completeness guard; the ratchet family
  (log-site, authz, direct-write, json-files, gryphon stage+branch); pytest-xdist
  parallel lanes (`scripts/test` full / `--fast`); the `smoke` marker; the Phase-0
  real-backend spike; the read-only-search-write Flaw.
- **TO BUILD (the work):** cold-boot smoke gate (Phase 1), known-broken manifest,
  promote-hook enforcement, ratchet-harness extraction (`tap/ratchet.py` — already
  past its 3rd caller), canary-tier membership discipline, suite-tiers affected lane.

## Prior art already gathered (NetBox + Nautobot — DON'T re-research)

- Both: real Postgres/Redis containers (not mocks) + `makemigrations --check` +
  a consolidated Ruff gate. Neither runs mypy; neither enforces a coverage floor
  (Nautobot has none) — TAP's ratchets are ABOVE their bar.
- Both take the low-fidelity async path (NetBox RQ-inline / Nautobot Celery-eager)
  that upstream docs warn against — TAP's real-backend spike is genuinely ahead.
- Nautobot's invoke-tasks = CI≡local is the gold standard; `scripts/dc` +
  `scripts/test` already lean that way. Steal later (trigger-gated): frozen-dataset
  migration-upgrade test.
- Cheap table-stakes TAP still lacks: `makemigrations --check` (#1 Django gap),
  a dependency scan (pip-audit), pre-commit≡CI mirror.

## Decisions/framing to carry forward

- The gate MUST run inside the compose image, never a reimplemented env.
- **One gate, many invokers:** build it as a SINGLE artifact (`manage.py`
  command or `scripts/gate`) that local + promote + future CI invoke identically.
- Server-CI's real trigger is the TRUST BOUNDARY (a 2nd contributor — human or
  agent — makes "did you run it?" unverifiable); TAP's multi-session AI model may
  have half-fired it. But that's post-July; THIS scope is the LOCAL gate.
- Ratchets are the AI-specific guardrail (they mechanically block the silent
  quality-erosion an agent would otherwise slip in). Frame new mechanisms this way.
- Fold `makemigrations --check` into the cold-boot cycle (cheap asymmetric edge).
- Honest-coverage rule: anything guarded only by "the suite passes" is labeled
  CI-unguarded, by design.

## Motivating data point

The 2026-07-02 clean-path merge caught that `main`'s `base` boot profile was briefly
broken post-package-mode-migration (preboot coherence abort) — a cold-boot gate
running preboot in a rebuilt image would have caught it MECHANICALLY before a spawn.
Second such data point. Use as the scope-setter for "what the gate must exercise."

## Discussion agenda

1. What "real" means for gate v0 — MVP scope (cold-boot cycle + known-broken
   manifest + promote-hook wiring, built on the Phase-0 mechanism)?
2. Gate-as-single-artifact shape: `manage.py` command vs script; how
   `promote-to-main.sh` invokes it; wall-clock budget (fidelity > speed).
3. Known-broken manifest format (follow the house ratcheting-baseline convention).
4. Sequencing: gate first vs extract `tap/ratchet.py` first vs the makemigrations
   edge — and what stays trigger-gated (server CI, frozen-dataset migration test).
5. **Per-profile cold-boot validation (validation in a world of variable plugins).**
   Today the gate/test model is "all plugins installed" — pytest discovery is pure
   file-path (not plugin-aware; no `importorskip` guards, so an absent plugin's
   test files hard-error at collection), and `test_settings` loads whatever is
   editable-installed in the venv (entry-point discovery), NOT a profile. Core
   suites hardcode plugin fixtures (lotr ×22 core-test files, samsite ×5, gryphon
   ×3), and `gryphon_playground` is build-baked (always-on) precisely because the
   Gridkin suite needs it. That's fine for CI correctness, but nothing asserts a
   *minimal* profile (e.g. no gryphon) actually cold-boots and works — the same bug
   class as the 2026-07-02 `base`-profile break (65ab633b "guard all shipped
   profiles"). Decide:
   - The gate should **cold-boot each shipped profile and assert it comes up** (the
     missing axis), rather than making pytest discovery plugin-aware (that fights
     the design and would require de-hardcoding lotr from the core suites).
   - As profiles diverge (lean customer profiles vs. dev), the **test/dev
     environment needs a "full/dev" profile whose install set is the superset**, so
     entry-point discovery still finds every plugin in the test venv (else the
     Gridkin/plugin suites red). Keep tests = "all plugins"; keep production
     profiles minimal; bridge with a dev/full profile + per-profile boot-smoke.
   - Making a plugin profile-optional in production follows the **lotr pattern**
     (package-mode + in a profile's `install`, editable-installed in the test venv);
     `gryphon_playground`'s move off build-baked is gated on the held gryphon-engine
     refactor.
</content>
