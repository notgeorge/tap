---
name: gryphon-fuzz-soak
description: Run a long unattended Gryphon differential-fuzz campaign soak for a given duration (e.g. "2h", "90m"), grinding fresh seed bands and watching for executor/oracle divergences and crashes. Use when you want to let the fuzzer cook for hours and surface new bugs, then triage what it finds.
allowed-tools: Read Write Edit Glob Grep Bash(scripts/dc *) Bash(scripts/gryphon-fuzz-campaign *) Bash(scripts/gryphon-findings *) Bash(git *) Bash(grep *) Bash(tail *) Bash(cat *) Bash(date *) Bash(mkdir *) Bash(tee *) Bash(wc *) Bash(sort *) Bash(uniq *) Bash(black *) Bash(ruff *) Bash(mypy *)
argument-hint: <duration e.g. 2h | 90m | 30m>  (default 2h)
---

# Gryphon Fuzz-Campaign Soak

Run the Gryphon differential property fuzzer as a **long, unattended campaign** for
the requested wall-clock duration, then triage anything it surfaces. This is the
measurement/discovery complement to the per-commit fuzz *gate*: the gate asserts a
small committed seed band and fails on any divergence; a **campaign** grinds a large
seed band the executor has never seen, classifies every query WITHOUT gating, and
appends one trend row per iteration to an append-only ledger so bug frequency can be
watched trending **down-and-to-the-right** as the executor hardens.

The whole exercise is compute-bound, not token-bound — the point is to let it cook.
Each iteration advances the seed band past every prior campaign (divergences are
deterministic, so re-testing a fixed band always reports zero), which is why it is
safe to loop for hours and why every finding stays replayable from its seed.

Authoritative background (skim before acting; do not guess from memory):
- `plugins/gryphon_playground/specs/spec-gridkin-v0.md` — `req-gridkin-property-fuzz`
  (the fuzzer), `req-gridkin-fuzz-campaign` (this soak's ledger + trend),
  `req-gridkin-findings-ledger` (the bug-locality ledger you append to on a fix).
- `plugins/gryphon_playground/gridkin/fuzz.py` — the generator + oracle + `run_query`
  classifier (`agree` / `diverge` / `rejected` / `crashed` / `unmodeled`).
- `scripts/gryphon-fuzz-campaign` — the one-band orchestrator this skill loops.
- The `build-gryphon-capability` skill — the fix discipline you follow on a real find.

## Step 1: Preflight

1. Confirm you are on a `session/<name>` branch (never soak-and-fix on `main`):
   `git rev-parse --abbrev-ref HEAD`.
2. Confirm the web container answers: `scripts/dc exec -T web true`. If it does not,
   the stack is down — bring it up (`scripts/dc up -d web`) or tell the user; do not
   proceed.
3. Note the working-tree state. The soak appends trend rows to a committed ledger
   (`plugins/gryphon_playground/gridkin/fuzz-campaign-log.jsonl`); a dirty tree is
   fine, but know what was already modified so you can tell soak output from prior work.

## Step 2: Parse the duration and calibrate one iteration

1. Parse the argument (`$ARGUMENTS`, default `2h`) into seconds: `2h`→7200, `90m`→5400,
   `30m`→1800. Reject anything you cannot parse — ask rather than guess.
2. **Time one calibration iteration** so each loop step is a few minutes (frequent
   enough to check the deadline, long enough to amortize pytest + per-graph DB setup):
   ```
   time scripts/dc exec -T -e TAP_FUZZ_COMMIT="$(git rev-parse --short HEAD)" \
       web scripts/gryphon-fuzz-campaign 40 25
   ```
   That is 40 graphs × 25 queries = 1000 queries. Read the printed
   `agree/diverge/rejected/crashed/unmodeled` line and the wall time.
3. **Pick the band size** (`GRAPHS QUERIES`) so one iteration lands around 3–5 minutes.
   If 1000 queries took ~30s, scale up (e.g. `200 50` = 10k queries). The calibration
   iteration is a real campaign — its row already counts; you do not discard it.

Report the calibrated band and the projected iteration count for the duration before
launching.

## Step 3: Launch the soak in the background

Run a bounded loop in the background, teeing to a soak log in the scratchpad. The loop
recomputes a fresh band each iteration (the orchestrator does this via `next_base_seed`)
and emits a **loud marker** the moment an iteration reports a divergence or crash, so
scanning the log later is trivial. Substitute the calibrated `GRAPHS`/`QUERIES` and the
deadline you computed:

```bash
LOG="$SCRATCH/gryphon-soak-$(date +%Y%m%d-%H%M%S).log"   # use the session scratchpad dir
DEADLINE=$(( $(date +%s) + DURATION_SECONDS ))
COMMIT="$(git rev-parse --short HEAD)"
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  OUT="$(scripts/dc exec -T -e TAP_FUZZ_COMMIT="$COMMIT" web scripts/gryphon-fuzz-campaign GRAPHS QUERIES 2>&1)" || true
  echo "$OUT"
  # Loud marker on any red signal — diverge/crashed nonzero, or a new distinct defect.
  echo "$OUT" | grep -E 'diverge=[1-9]|crashed=[1-9]' && echo ">>> SOAK-ALERT: red iteration above <<<"
done
echo ">>> SOAK COMPLETE at $(date -u +%FT%TZ) <<<"
```

Launch it with the Bash tool's **background** mode and tee to `"$LOG"`. Because it is
run in the background, the harness re-invokes you when it exits (at the deadline) — you
do not sit and block on it. `TAP_FUZZ_COMMIT` is stamped from the host because git is
unavailable inside the container.

While it runs you may periodically `tail` the log or `grep SOAK-ALERT "$LOG"` for early
signal, but the durable record is the ledger — you do not need to babysit it.

## Step 4: Triage what it found (the point of the soak)

When the soak completes (or when you check in), read the trend and the ledger:

```bash
scripts/dc exec -T web uv run python -c \
  "from plugins.gryphon_playground.gridkin import fuzz_campaign as c; \
   print(c.trend('plugins/gryphon_playground/gridkin/fuzz-campaign-log.jsonl'))"
```

Read the columns honestly:
- **`new`** — fingerprints not seen in ANY earlier campaign. This is the sharpest
  signal: `new > 0` means the soak found genuinely new territory. `new = 0` across the
  whole soak is a clean result worth stating plainly (the executor held).
- **`asrt%`** — the oracle-asserted fraction. A low defect rate with a *low* asserted
  fraction is exploration collapse (the generator drifted off the modeled surface), not
  hardening. Watch that it stays high; a sudden drop is itself a finding.
- **`def/100k`** — distinct-defect density for that band.

For each campaign row with a nonzero defect count, pull its persisted defects — each
carries a **replaying seed**, so a find survives long after the run:

```bash
scripts/dc exec -T web uv run python -c \
  "import json; \
   rows=[json.loads(l) for l in open('plugins/gryphon_playground/gridkin/fuzz-campaign-log.jsonl')]; \
   [print(r['utc'], d['fingerprint'], 'seed=%s'%d['seed'], d['detail'][:200]) \
    for r in rows for d in r.get('defects',[])]"
```

Classify each distinct defect:
- **`diverge`** — executor and oracle disagree on the answer: a **silent-wrong-answer
  bug**. Highest priority. Real.
- **`crashed`** — an unexpected exception (not a clean rejection): a **crash bug**, or a
  bad generated fixture (the detail names the exception class). Investigate.
- **`rejected`** — the executor cleanly raised `SearchExecutionError`. Usually a
  **deliberate v0 boundary**, not a bug — check it against the known boundaries below
  before chasing it. A rejection of a shape that *should* be supported is a real find.

### Known boundaries — reject/skip, do not "fix"
These are deliberate; a fingerprint that reduces to one of them is expected noise, not a
bug (the fuzzer already suppresses most of them — a leak means the *suppression* slipped,
which is worth a cheap fix, not an executor change):
- **Far-node negation** — `!=` / `NOT (...)` over a multi-valued reverse-FK path is
  deliberately rejected pending F-alias support.
- **Node-only aggregation** — a v0 boundary.
- **`LIMIT` without `ORDER BY`** — a permanent skip (nondeterministic).

## Step 5: Fix a real find (follow the standing discipline)

For each confirmed bug, do NOT just log it — follow the `build-gryphon-capability` fix
cycle, as **one commit** per bug:
1. **Reproduce it as a committed Gridkin scenario first** — replay the seed to get the
   emitted GRIFT + query + both results, then hand-author a `*.gridkin.json` scenario
   (fixture + oracle-computed expected envelope/SQL, or `expected_error` for a rejection
   you are making deliberate). The expected file is an oracle you compute, never a
   capture.
2. **Root-cause and fix** in `tap_grid/gryphon/executor.py` (or `model_oracle.py` if the
   oracle itself is wrong — that is an `oracle-bug`, still a real finding).
3. **In the same commit, append a findings-ledger row** to
   `plugins/gryphon_playground/gridkin/gryphon-findings.jsonl` with `discovery: "campaign"`
   — subsystem + functions + class + tags — so the bug-locality hotspot map stays current
   (`req-gridkin-findings-ledger`). Run `scripts/gryphon-findings` to see the updated map.
4. **Re-enable/extend the fuzzer** if the bug lived in a shape the generator was
   suppressing, so the gate now covers it.
5. `black` / `ruff` / `mypy` clean + the affected gridkin/executor tests green before
   committing.

## Step 6: Record the soak and hand off

1. **Commit the accumulated trend rows** as ONE commit
   (`chore(gridkin): fuzz-campaign soak — <N> bands, <Q> queries, <new> new defects`).
   Do not spam a commit per iteration; the trend is the record, the bands are the rows.
   Bug fixes from Step 5 are their own commits, landed first.
2. Summarize for the user: bands run, total queries, `new` defects across the soak,
   asserted-fraction range, and — for each real find — the bug, the fix commit, and the
   hotspot it landed on. If the soak was clean (`new = 0`), say so plainly; a long clean
   soak is a genuine hardening signal, not a null result.
3. **Do not promote to `main`** unless the user explicitly asks. Leave everything on the
   session branch.

## Common mistakes (do not make these)
- **Chasing `rejected` fingerprints that are known boundaries** — check Step 4's list
  first; most rejections are the contract working.
- **Capturing an oracle instead of authoring it** — a systematic executor bug produces
  a self-consistent wrong expected that passes on rerun. Hand-compute, verify in assert
  mode (see the `build-gryphon-capability` Step 7 discipline).
- **Re-testing a fixed band** — never lower the seed base by hand; the orchestrator's
  `next_base_seed` only advances, and that monotonicity is the honesty of the metric.
- **`git checkout --` on the ledger to "clean up"** — the appended trend rows ARE the
  soak's output; commit them, don't discard them.
- **A commit per iteration** — batch the trend rows into one soak commit.
- **Promoting without being asked.**
