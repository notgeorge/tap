---
name: diagnose-failed-session-spawn
description: Diagnose why a multi-session dev spawn (scripts/spawn-session.sh, or a scripts/gate-lean throwaway) failed to stand up — pinpoint the failing spawn step, name the root cause with the load-bearing log excerpt, and say what to fix. Use whenever a spawn aborts, boots UNHEALTHY, hangs, or the lean-boot gate goes RED.
allowed-tools: Read Grep Glob Bash(scripts/dc *) Bash(docker *) Bash(docker compose *) Bash(git *) Bash(grep *) Bash(tail *) Bash(cat *) Bash(sed *) Bash(ls *) Bash(cut *)
argument-hint: [session-name | compose-project | path-to-diag-log]  (default: infer the most recent failed spawn)
---

# Diagnose a Failed Session Spawn

> **Skill source-of-truth.** Canonical location: `tap_boot/skills/diagnose-failed-session-spawn/SKILL.md`. `.claude/skills/…` is a wiring symlink (`scripts/wire-skills.sh`). Edit the canonical.

A spawn (`scripts/spawn-session.sh`) stands an instance up through a fixed ordered sequence; a `scripts/gate-lean` throwaway drives that same sequence with a lean, isolated venv. When one fails, the failure is almost always at a **specific step**, and the web container's logs name it. This skill is the standardized read of that sequence so we stop re-deriving it by hand each time. Produce a **verdict**: failing step → root cause → the log line that proves it → the fix → whether to nuke.

Authoritative background (skim, do not guess): `scripts/spawn-session.sh` (the step sequence), `scripts/despawn-session.sh` (teardown), `scripts/gate-lean` (the lean-boot gate + its `*-diag.log`), `specs/spec-dev-multisession.md`, `specs/spec-tap-boot-v0.md` (boot phases), `specs/spec-dev-validation.md`.

## Step 0 — Establish the target

Identify the failed session's **compose project** (`tap_<name>`) and where its worktree lives:

1. If given a `*-diag.log` path (a `gate-lean` failure capture), read it first — it already holds `compose ps` + `web logs`. Then continue for anything it doesn't cover.
2. Else resolve the project. From inside a session worktree, `scripts/dc` targets it; otherwise use `docker compose -p tap_<name>`. List candidates: `docker ps -a --format '{{.Names}}\t{{.Status}}' | grep -E 'tap_'`. A failed spawn appends **no** registry row (`~/tap-sessions/.registry` is append-on-success), so a container present but absent from the registry is itself a signal of a partial spawn.
3. Note the worktree base: default `~/tap-sessions/<name>`, but a `gate-lean` throwaway lives under `WORKTREE_BASE` (system tmp). `git worktree list` shows live ones.

## Step 1 — Read container state (which step died)

```
docker compose -p tap_<name> ps          # container states + exit codes
docker compose -p tap_<name> logs --tail 300 web
docker compose -p tap_<name> logs --tail 80 db
```

Map the last successful line in the `web` log to the spawn step. The failure-prone steps, in order:

| Step | What runs | Typical failure signature |
| --- | --- | --- |
| **4** Build & start | `docker compose build` + `up` | image build error (dep resolution); **port already allocated** (`bind: address already in use`); a stale prior stack on the band |
| **5** Entrypoint | uv sync → **pre-boot** (install plugins, conformance/reconcile/dep/coherence gates, snapshot) → **migrate** → runserver | see Step 2 below — this is where most real failures land |
| **6** `manage.py boot` | auth → population (seed-plugin / fire-collector) | population **abort**: unknown plugin/collector/bundle key; a seed bundle raised; a `fire-collector` step timed out (`req-boot-collector-timeout`) |
| **6.5** Health gate | `manage.py health --json` | a critical probe UNHEALTHY: db / cache (`tap_cache` table) / queue / secrets |

## Step 2 — Classify the root cause (pre-boot / migrate / boot / health)

Match the `web` log against these signatures — most-common first:

- **Import leakage (the `requests` / `jwt` class).** `ModuleNotFoundError: No module named '<pkg>'` raised from a **core** (`tap_*`) module during pre-boot / migrate / boot, in a **lean** profile (`core` / `core_dev`) where that package isn't installed. This is exactly what `gate-lean` exists to catch: a core module imports a **plugin-only** dependency. Root cause is the offending `import` in core, not the venv. Fix: move the dependency out of the core import path (lazy-import it inside the plugin, or declare it as a core dep if it truly is one). Confirm with `grep -rn "import <pkg>" tap*/` to find the leak.
- **Pre-boot gate abort.** A `[hex]` `pre-boot … gate` line at ERROR: identity/reconciliation/dependency/coherence mismatch (e.g. `installed != declared`, a collector-scope drift, an undeclared cross-plugin import edge). Root cause is a manifest ↔ install ↔ code disagreement; the message names the mismatch. (See the collector-identity / validate_plugin work.)
- **Migration drift / failure.** `makemigrations --check` would flag model drift; a `migrate` traceback names the failing migration/SQL. Fix: generate + commit the migration, or repair the bad one.
- **Boot population abort.** `BootError` naming an unknown plugin/collector/bundle, or a seed bundle exception. Root cause is the profile referencing something the install set / registry doesn't provide, or bad GRIFT.
- **Health red.** Read the probe JSON: `docker compose -p tap_<name> exec -T web uv run python manage.py health --json`. `tap_cache` missing ⇒ createcachetable ordering; a secrets probe ⇒ a required secret absent under `TAP_SECRETS_ROOT`; db/queue ⇒ backend down.
- **Infra, not app.** Port collision (Step 4): another stack holds the band — `docker ps --format '{{.Names}} {{.Ports}}' | grep <port>`. DB unhealthy: read `logs db`. Stale volume from a prior aborted run: a `_venv` / `_postgres_data` volume for the project lingering (`docker volume ls | grep tap_<name>`).

## Step 3 — Verdict

State plainly: **failing step**, **root cause**, the **one log line** that proves it, the **fix**, and **whether the throwaway/session should be nuked** (`WORKTREE_BASE=<base> scripts/despawn-session.sh <name> --yes` — clean throwaways tear down unattended; a session with unpushed commits is HARD-STOPPED by despawn, report that instead of forcing). If diagnosing a `gate-lean` RED, note that gate-lean nukes on exit — so diagnose from the captured `*-diag.log` unless you caught it live.

## Step 4 — Reflect and evolve this skill (do every run)

Before finishing, reflect on the diagnostic session itself:

- Did the failure fit a signature above, or was it a **new** class? If new, add a row/bullet (signature → root cause → fix) so the next run catches it in one pass.
- Did a step's evidence command come up short (wrong log depth, a state `ps`/`logs` didn't reveal, a probe you had to reach for)? Improve the command.
- Was the target hard to resolve (naming, tmp base, no registry row)? Sharpen Step 0.

Make the edit to **this** SKILL.md in the same change (it is the standard we are iterating), and note in your summary what you changed and why — so the skill compounds instead of staying frozen at its first draft.
