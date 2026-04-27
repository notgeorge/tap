---
spec: ../specs/spec-dev-multisession-onboarding-doc.md
audience: [developer, llm]
covers:
  - ../specs/spec-dev-multisession.md
  - ../specs/spec-dev-multisession-smoketest.md
  - ../specs/spec-dev-multisession-teardown.md
  - req-dev-multisession-compose-parameterized
  - req-dev-multisession-env-cascade
  - req-dev-multisession-port-registry
  - req-dev-multisession-browser-disambiguation
update-triggers:
  - scripts/dc behavior or invocation
  - docker-compose.yml env-var contract (new parameterized vars)
  - Port registry table in spec-dev-multisession.md
  - Worktree path or branch convention
  - TAP_GRID_ID generation method
  - TAP_SESSION_LABEL convention or rendering
  - .localhost URL convention or ALLOWED_HOSTS handling
  - Migrate or seed command names (e.g. import_plugin_grift)
  - Restructuring of spec-dev-multisession-smoketest.md or -teardown.md
  - scripts/spawn-session.sh shipping (Phase 2 supersedes this manual procedure)
assumes:
  - basic git fluency (worktrees, branches)
  - basic docker / docker compose familiarity
  - macOS / zsh shell (the only environment exercised today)
  - Python 3.14 available locally for uuid7 generation
provides: |
  Reader can spin up a fully isolated TAP development session — its own worktree,
  Docker stack, database, and grid identity — and attach a Claude Code session
  inside it ready to do work. Hands off to the smoke-test doc-spec for verification.
---

# Onboarding a New Multi-Session Dev Environment

Spec: [spec-dev-multisession-onboarding-doc.md](../specs/spec-dev-multisession-onboarding-doc.md)

This is the canonical procedure for spawning a new isolated TAP dev session by hand. Phase 2's `scripts/spawn-session.sh` will collapse this into a single command; until then, follow these steps. After completion, run the smoke tests in [spec-dev-multisession-smoketest.md](../specs/spec-dev-multisession-smoketest.md) to verify the environment is healthy. Teardown is documented in [spec-dev-multisession-teardown.md](../specs/spec-dev-multisession-teardown.md).

All commands assume macOS / zsh and the primary checkout at `~/Documents/code/tap`.

## 1. Pick a session name and look up its port band

The port band lives in the [Fixed-by-Name Port Registry](../specs/spec-dev-multisession.md#fixed-by-name-port-registry) in `spec-dev-multisession.md`. For this walkthrough we use `cli` (`tap_cli` / `8010` / `5442`).

If your chosen name isn't in the registry yet, add it there first — the registry is authoritative.

## 2. Create the worktree on a new session branch

```bash
cd ~/Documents/code/tap
git worktree add ~/tap-sessions/cli -b session/cli
cd ~/tap-sessions/cli
```

## 3. Generate a fresh TAP_GRID_ID and write `.env.local`

Each isolated stack is logically a separate TAP installation, so it gets its own grid identity:

```bash
TAP_GRID_ID=$(python3 -c "import uuid; print(uuid.uuid7())")
cat > .env.local <<EOF
COMPOSE_PROJECT_NAME=tap_cli
WEB_PORT=8010
POSTGRES_PORT=5442
TAP_GRID_ID=$TAP_GRID_ID
TAP_SESSION_LABEL=cli
EOF
```

`TAP_SESSION_LABEL` is what the browser tab title and the nav bar will display so you can tell at a glance which session a window points at — see [req-dev-multisession-browser-disambiguation](../specs/spec-dev-multisession.md#browser-disambiguation). Use the same string as the session name (here, `cli`).

Confirm `.env.local` is gitignored:

```bash
git status   # .env.local must NOT appear
```

## 4. Build and start the stack

```bash
scripts/dc up -d --build
```

`scripts/dc` is the env-cascade wrapper around `docker compose` — see [req-dev-multisession-env-cascade](../specs/spec-dev-multisession.md#env-file-cascade). First run pulls `postgres:16-alpine` and builds the web image, typically 2–5 minutes. Subsequent runs are fast.

## 5. Apply migrations

```bash
scripts/dc exec web uv run python manage.py migrate
```

## 6. Seed plugin data

```bash
scripts/dc exec web uv run python manage.py import_plugin_grift --all
```

## 7. Attach a Claude Code session inside the new environment

- **CLI:** `cd ~/tap-sessions/cli && claude`
- **VSCode:** open the folder `~/tap-sessions/cli` in a new VSCode window; the Claude extension attaches to that workspace.

The web app is reachable at either of:

- `http://cli.tap.localhost:8010/` — labeled URL (recommended for tab disambiguation; the `*.localhost` subdomain resolves to `127.0.0.1` natively in modern browsers).
- `http://localhost:8010/` — direct port access (still works).

Either URL hits the same session. The browser tab will read `[cli] TAP …` and the nav bar shows a `cli` badge so it's obvious which session you're looking at.

## 8. Run the smoke tests

From inside the attached Claude session (or by hand), follow [spec-dev-multisession-smoketest.md](../specs/spec-dev-multisession-smoketest.md) to verify the environment is healthy and properly isolated from the primary stack. The smoke-test spec gives an in-env Claude session a deterministic top-to-bottom verification procedure.

## When you're done

Tear down the session in one command (once the script ships) per [spec-dev-multisession-teardown.md](../specs/spec-dev-multisession-teardown.md):

```bash
# Future:
scripts/despawn-session.sh cli
```

Until the despawn script lands, follow the [Manual Teardown](../specs/spec-dev-multisession-teardown.md#manual-teardown-until-the-script-lands) section in the teardown spec.
