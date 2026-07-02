# Test parallelization (pytest-xdist) — diagnosis, fix, remaining

Forward note for the validation-focused work. Seeds the second half of
`req-dev-validation-suite-tiers` (spec-dev-validation.md): flipping the inner-loop
default to parallel. `pytest-xdist` is added (dev group, commit `d4ffebe4`); the
`-n auto` blocker is now **fixed** (see below); the default `addopts` is still
serial pending the deliberate lane split (remaining task).

## Why (the measured story)

Profiling inside the compose image:

- **Serial full run:** `2266 passed in 1754s (0:29:14)` (`pytest --durations=25`).
- **Parallel full run (`-n auto`, after the fix):** `2269 passed in 554s (0:09:14)`
  — **~3.2×**. `-n 2` on `tap_grid` alone: `982 passed`, clean.
- **Cost shape:** dominated by per-test DB `setup`/`teardown` (`transaction=True`
  table truncation), a *fat tail* — the top-25 slowest are only ~14% of wall-clock.
  A per-test tax across ~2,270 tests parallelizes near-linearly, which is why xdist
  is the lever. One outlier worth a look:
  `tap_grid/tests/test_batch.py::TestCreateBatch::test_creates_batch_with_entity`
  setup = **47s**.

## The blocker was lock-table exhaustion, NOT mirror isolation

An initial `-n auto` run produced `46 failed, 178 errors`. First hypothesis — that
the `search_readonly` `TEST: {"MIRROR": "default"}` alias wasn't isolating per
xdist worker — was **wrong**. The error breakdown settled it:

| signature | count |
| --- | --- |
| `out of shared memory` / `increase max_locks_per_transaction` | **356** |
| `database ... is being accessed by other users` (mirror teardown) | 2 |
| actual `ReadOnlySqlTransaction` (real read-only rejection) | 0 |

Root cause: the public schema has **247 tables**. Each `transaction=True` flush
`TRUNCATE`s the full set — one `AccessExclusiveLock` per table — and 8 xdist
workers doing that concurrently (plus FK/index/history locks, and the mirror's
second connection) exhausts PostgreSQL's shared lock pool. That pool is
`max_locks_per_transaction × max_connections`; at the defaults (`64 × 100`) it is
~6,400 slots, far too small for this workload at 8-way parallelism. The mirror's
extra connection contributes marginally but was not the cause (0 of the failures
were real read-only rejections; the 2 mirror-teardown errors vanished once the
lock pressure was relieved).

## The fix (landed)

`docker-compose.yml` db service: `command: ["postgres", "-c",
"max_locks_per_transaction=512"]` → a ~51k-slot pool. Test/dev infra only; the
extra shared memory is negligible. Recreate the db container (`scripts/dc up -d
db`) for it to take effect. Validated: **`out of shared memory` 356 → 0**,
mirror-teardown errors 2 → 0, `-n auto` green at 9:14.

## Lanes (implemented) — parallelism in a script, NOT in `addopts`

`-n auto` was **deliberately kept out of pyproject `addopts`**: it adds a
per-worker DB-build tax that penalizes small runs — a single test file measured
**4.3s serial vs 14.9s under `-n auto`** (~3.5×). So the default `pytest` stays
serial (best for single-test debugging), and the parallel lanes are explicit in
`scripts/test`:

- **`scripts/test`** — FULL lane: every test incl. the gryphon corpus, `-n auto`.
  The authoritative lane the promote gate uses (~9 min). The gryphon executor
  stage/branch-coverage guards ride this lane.
- **`scripts/test --fast`** — INNER-LOOP lane: `-n auto` minus
  `plugins/gryphon_playground`. A local accelerator, explicitly **not** a gate
  (`req-dev-validation-suite-tiers-4`), so it skips the gryphon guards — which the
  full lane still runs. **No Map-row cadence change needed**: the guards remain
  per-commit in the authoritative full lane; only this opt-in fast lane skips them.
- Single-test debugging: bare `scripts/dc exec web uv run pytest <path::test>` —
  serial, no worker/DB startup tax.

`scripts/test` allocates a TTY interactively and falls back to `-T` when piped/under
automation, so the same script serves both the human inner loop and the future gate.

## Remaining

1. **Record the 9:14 wall-clock in `req-dev-validation-suite-tiers`** — that section
   lives on `origin/main`, not this branch, so it is recorded here for now and
   flows into the spec on merge-up.
2. **Adjacent/optional:** `--reuse-db` for warm local runs; the 47s `test_batch`
   setup outlier; the `affected` lane (`-m "not slow"` / testmon) is a later phase.

## Unrelated note

Two ratchet tests (`test_authz_coverage_ratchet`, `test_json_filename_convention`)
are red on this branch — stale-baseline drift from being behind `origin/main`
(the authz baseline is line-number-anchored; a symbol-anchored baseline is the
durability fix, see `req-dev-validation-ratchet-harness`). They clear on merge-up
and are unrelated to xdist.
</content>
