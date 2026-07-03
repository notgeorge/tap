# Handoff — suite-tiers / per-profile test lanes (coupled to the streamlined boot profiles)

> Tack-on note for the plugins session that is building the streamlined boot
> profiles (`core`, `core_dev`, `gryphon-playground`) to replace the single
> everything-in-it `base`. It exists so that session can **decide** whether to pick
> up the one remaining validation item that is coupled to its work, or leave it for
> a later dedicated pass. Not authoritative spec — `specs/spec-dev-validation.md` is.
> Versioning is git.

## Why you're getting this

`session/validation-creation` is **closing out**. The dev-validation system it was
chartered to build is done and on `origin/main`: cold-boot smoke gate + known-broken
manifest + promote-hook, per-profile boot-resolution guard, `makemigrations --check`,
the mypy ratchet, the unified `tap/ratchet.py` + `tap.guards` harness (all bespoke
ratchets migrated + distributed to their owners), and the **generated Validation Map**
(guards carry an `rid`; the Map is rendered from the guard set + declared surfaces and
a meta-test blocks drift). Spec statuses were reconciled to as-built.

**Exactly one requirement is left partly open and it lands in your lap by topology:**
`req-dev-validation-suite-tiers` — the test-time-reduction lever. It is coupled to the
lean profiles you're building, so you're the right session to decide its fate.

## What's already built (don't rebuild)

- `scripts/test` — the **full** lane (`-n auto`, every test incl. the gryphon_playground
  corpus; the authoritative pre-push lane) and the **`--fast`** inner-loop lane (`-n auto`
  **minus** `gryphon_playground`). Parallelism lives here, not in `addopts`, on purpose
  (the default `pytest` stays serial). See `docs/misc/test-parallelization-xdist-notes.md`.
- `pytest-xdist` per-worker DBs; `max_locks_per_transaction=512` (the real xdist blocker
  was PG lock exhaustion, not mirror isolation).
- The `smoke` marker exists (one user: the web-render login/landing smoke).

## What's left (`req-dev-validation-suite-tiers`, Partially Implemented)

- **Affected/impact lane** — run only the tests touching changed code, for the inner
  loop. Not a gate (the pre-push gate always runs full — `req-dev-validation-suite-tiers-4`).
- **Profiled `slow` designations** — driven by `--durations` evidence, not intuition.
- **The "which runs when" doc** — one table: fast / affected / full, and when each fires.

## The coupling — read this before you decide

Your streamlined profiles are the natural lever for test time, but the win is **not**
"just run the suite against a lean install set." Three load-bearing facts from the
original handoff (agenda item 5 of `doc-dev-validation-make-real-handoff.md`) that bound
what's actually possible:

1. **pytest discovery is pure file-path, not plugin-aware.** There are no
   `importorskip` guards, so an *absent* plugin's test files **hard-error at collection**.
2. **`test_settings` loads whatever is editable-installed in the venv** (entry-point
   discovery), **not a profile.** So the test venv install set — not a boot profile — is
   what pytest sees.
3. **Core suites hardcode plugin fixtures** (lotr ×~22 core-test files, samsite ×5,
   gryphon ×3), and `gryphon_playground` is **build-baked / always-on** precisely because
   the Gridkin corpus needs it.

Consequence: keep **tests = "all plugins"** (a dev/full profile whose install set is the
superset, so entry-point discovery still finds everything), keep **production profiles
minimal**, and bridge the two with the **per-profile boot-smoke** (already built — the
gate cold-boots each shipped profile). The lean profiles make *cold boot / spawn* faster
and let the gate assert each lean profile comes up; they do **not**, by themselves, let a
lean profile run a lean test lane, because of (1)–(3).

## Where the real test-time win is

The dominant time sink in the full lane is the **`gryphon_playground` corpus** (Gridkin
scenarios + the differential fuzzer). `scripts/test --fast` already excludes it by hand.
The clean, principled version of that — and the highest-ROI slice of suite-tiers — is:

- **Make `gryphon-playground` an opt-in profile/lane, not build-baked.** Then the `core` /
  `core_dev` lanes are the default inner loop (no gryphon corpus), and gryphon runs as its
  own lane + always in the pre-push full lane. This realizes suite-tiers-1's "three named
  lanes" honestly instead of via a hand-maintained `--fast` exclusion. **Gate:** moving
  `gryphon_playground` off build-baked is blocked on the held gryphon-engine refactor
  (see the plugin-migration memory) — so this may not be free yet.

## Decision menu for your session

Pick per your appetite; none of these block launch-ready (dev-validation is enabling
infra beneath `step-rampart-launch-ready`, not its Done-Test):

- **A — Do nothing here.** Land the profiles; leave suite-tiers for a later dedicated
  validation pass. Fully legitimate; the `--fast` lane already gives an inner loop.
- **B — Principled core lane (recommended if gryphon can come off build-baked).** As the
  profiles land, replace the hand-rolled `--fast` gryphon exclusion with a profile-driven
  `core`/`core_dev` lane; keep gryphon as its own lane + in the full pre-push lane. Update
  `scripts/test` + the "which runs when" doc; flip `req-dev-validation-suite-tiers-1` →
  Implemented. **Add its Validation Map surface in the same change** (it's a guarded
  surface once it's a lane) — the Map is generated, so this means a guard/`DECLARED_SURFACES`
  entry, then `manage.py guards --sync-map`.
- **C — Affected/impact lane.** Add a changed-files test-selection lane for the inner loop
  (never a gate). Independent of the profiles; smaller.
- **D — Canary-tier governance (independent, small).** `req-dev-validation-canary-tier` is
  still fully Proposed: the `smoke` marker exists but the *set* is ungoverned (~1 test, no
  per-entry blast-radius justification, no fitness cap). Not coupled to profiles; can be
  done anytime by anyone.

## If you touch the validation surface at all

- Adding/'moving/retiring any validation surface REQUIRES its Map row **in the same
  change** — but the Map is now **generated**. So: add/adjust the guard (`tap.guards`, one
  file per guard, carries `slug`/`map_row`/`rid`/`cadence`/`status`/`description`) or the
  `DECLARED_SURFACES` entry (`tap/guards/surfaces.py`), then `manage.py guards --sync-map`.
  `test_spec_map_in_sync` + `test_guard_rid_resolves` enforce it.
- Every guard's `rid` must resolve to a **defined** requirement (an `RID:` heading or a
  requirements-table cell), not just an inline reference.
- Merging un-mypy-gated `main` into this gated tree reliably trips the mypy ratchet on
  incoming test-fixture / skill-script noise. Check the NEW-key diff is noise
  (`no-untyped-call` in tests, `import-not-found` for un-vendored libs), then re-baseline
  with `manage.py guards --sync-mypy`.
