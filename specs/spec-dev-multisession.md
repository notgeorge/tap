# Multi-Session Development Environment

## Philosophy

Multiple concurrent Claude Code sessions (CLI + VSCode extension, and eventually three or more) need to operate on the TAP codebase without colliding. Two collisions happen today: file-system races on the same working tree, and Docker collisions on shared container names, networks, volumes, and host ports. The fix is full-stack isolation per session — separate working tree, separate Docker stack, separate database — orchestrated by repeatable spawn/despawn scripts so adding a third or fourth session is a one-command operation.

The Playwright MCP server is stateless per call and remains shared across sessions.

## Goals

|   |   |  |
| :---: | --- | --- |
| 1. | Stack Isolation | Each session runs its own Docker Compose project with its own containers, network, volumes, and host ports. |
| 2. | Working Tree Isolation | Each session has its own checkout (git worktree) so file edits never overlap. |
| 3. | Repeatable Spawn | Adding a new session is a single command that produces a working environment seeded with current data. |
| 4. | Zero-Setup Default | The primary checkout works with `docker compose up` and no manual env configuration, preserving today's developer experience. |
| 5. | Demand-Driven Allocation | Sessions get a port band the first time they're spawned, recorded in a per-machine registry. The primary's reservation (8000/5432) is fixed; everything else is allocated on demand. Ephemeral by default — despawn frees the band. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-dev-multisession-compose-parameterized | [Parameterized Compose Stack](#parameterized-compose-stack) | Implemented | Phase 1 |
| req-dev-multisession-env-cascade | [Env File Cascade](#env-file-cascade) | Implemented | Phase 1 |
| req-dev-multisession-port-registry | [Per-Machine Session Registry](#per-machine-session-registry) | Implemented | Phase 1 |
| req-dev-multisession-browser-disambiguation | [Browser Disambiguation](#browser-disambiguation) | Implemented | Phase 1 |
| req-dev-multisession-spawn-script | [Spawn Script](#spawn-script) | Implemented | Phase 2; interactive |
| req-dev-multisession-admin-bootstrap | [Admin User Bootstrap](#admin-user-bootstrap) | Implemented | Phase 2, sub-feature of spawn |
| req-dev-multisession-spawn-import-strict | [Granular Grift Import Failure Mode](#granular-grift-import-failure-mode) | Backlog | Phase 3 polish on top of fail-fast |
| req-dev-multisession-push-workflow | [Session → Main Push Workflow](#session-→-main-push-workflow) | Implemented | Always-on discipline; codifies how session worktrees advance origin/main and keep the local main worktree current |
| req-dev-multisession-list-script | [List Script](#list-script) | Proposed | Phase 3 |
| req-dev-multisession-named-routing | [Name-Based Routing via Reverse Proxy](#name-based-routing-via-reverse-proxy) | Backlog | Phase 3 polish |

Teardown is tracked separately in [spec-dev-multisession-teardown.md](spec-dev-multisession-teardown.md). Smoke tests live in [spec-dev-multisession-smoketest.md](spec-dev-multisession-smoketest.md).

### Parameterized Compose Stack
----
RID: `req-dev-multisession-compose-parameterized`
Status: `Implemented`

`docker-compose.yml` MUST read `COMPOSE_PROJECT_NAME` and host port mappings from environment variables, with sensible defaults preserving the current `tap` / `8000` / `5432` behavior. Variables to parameterize:

- `COMPOSE_PROJECT_NAME` — namespace for containers, networks, volumes (Compose reads this natively).
- `WEB_PORT` — host port mapped to Django container `8000`. Default `8000`.
- `POSTGRES_PORT` — host port mapped to Postgres container `5432`. Default `5432`.
- `TAP_GRID_ID` — installation identity. Default the current hardcoded UUID; spawn script (Phase 2) generates a new one per session.
- `TAP_PRODUCT_NAME` — product name shown in the UI title bar, header, and `<title>` element. Default `"TAP"`. Set per-session in `.env.local` (e.g. `RAMPART`) for branded demo instances; the value is read by `tap_web/context_processors.py` and exposed to every template as `{{ product_name }}`.

#### Implementation
- `docker-compose.yml` uses `${VAR:-default}` substitution syntax so the file remains valid with no `.env` present.
- A checked-in `.env` carries the defaults so `docker compose up` works out of the box in the primary checkout.
- Container-internal ports (`8000`, `5432`) stay fixed; only host-side mappings move.
- **uv cache lives in a per-project named volume** (`uv_cache:/root/.cache/uv`) rather than being baked into the image at build time. This is a deliberate isolation choice: image layers carrying uv's cache caused Docker's build cache to fossilize corrupted uv state and replay it across every rebuild (a real problem hit during multi-session debugging on 2026-04-27). Per-project named volumes mean (a) cache corruption can't leak between sessions, (b) `dc down -v` (already part of despawn) clears it, and (c) image rebuilds don't carry old cache state forward.
- **Dependency sync runs in the entrypoint, not the Dockerfile.** Because both `/app/.venv` (worktree bind mount) and `/root/.cache/uv` (named volume) are runtime mounts that hide image content, build-time `uv sync` is wasted work — anything installed lands in image layers nobody can read at runtime. `docker/entrypoint.sh` runs `uv sync` on first container start; subsequent starts are near-instant no-ops because the venv and cache persist in their respective mounts.

#### Future
If we add Redis, mailcatcher, or other host-exposed services, follow the same pattern: add `<SERVICE>_PORT` variable with a default, allocate it a fixed offset in the port registry.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-compose-parameterized-1 | Default behavior unchanged | Proposed | `docker compose up` from a fresh clone with the checked-in `.env` produces containers named `tap-web-1` / `tap-db-1` listening on host `8000` / `5432`. | |
| req-dev-multisession-compose-parameterized-2 | Override applied | Proposed | Setting `COMPOSE_PROJECT_NAME=tap_cli WEB_PORT=8001 POSTGRES_PORT=5433` and running compose produces containers in the `tap_cli` project listening on host `8001` / `5433`. | |
| req-dev-multisession-compose-parameterized-3 | Two stacks coexist | Proposed | Two checkouts running compose with different namespaces produce two simultaneously-running, non-conflicting Docker stacks. | |
| req-dev-multisession-compose-parameterized-4 | uv cache is a per-project named volume | Proposed | The web service mounts `uv_cache:/root/.cache/uv`. Each compose project gets its own volume; cache corruption is per-session and cleared by `dc down -v`. | |
| req-dev-multisession-compose-parameterized-5 | Dependency sync at entrypoint | Proposed | `uv sync` runs from `docker/entrypoint.sh`, not the Dockerfile, so the install lands in the bind-mounted worktree and the named-volume cache rather than in image layers. | |

### Env File Cascade
----
RID: `req-dev-multisession-env-cascade`
Status: `Implemented`

A small `scripts/dc` wrapper invokes Docker Compose with `--env-file .env --env-file .env.local` (the latter included only when present), so `.env` provides defaults and `.env.local` overrides them per worktree. Direct `docker compose` invocations still work using only `.env`.

#### Implementation
- `.env` is **checked in** with defaults (`COMPOSE_PROJECT_NAME`, `WEB_PORT`, `POSTGRES_PORT`, `TAP_GRID_ID`).
- `.env.local` is **gitignored** (`.gitignore` updated accordingly).
- `scripts/dc` is a thin shell script: cascades env files and forwards arguments to `docker compose`.
- Documented usage: `scripts/dc up`, `scripts/dc exec web ...`, etc. — drop-in for `docker compose`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-env-cascade-1 | Wrapper cascades env files | Proposed | `scripts/dc config` resolves variables from `.env.local` when present, falling back to `.env`. | |
| req-dev-multisession-env-cascade-2 | `.env.local` not tracked | Proposed | `git status` is clean after creating a `.env.local` file. | |

### Per-Machine Session Registry
----
RID: `req-dev-multisession-port-registry`
Status: `Implemented`

Sessions are allocated port bands on demand at spawn time and recorded in a per-machine registry at `~/tap-sessions/.registry`. The primary stack's reservation is fixed; session names are otherwise arbitrary and chosen by the developer.

#### Reserved

| Name | COMPOSE_PROJECT_NAME | WEB_PORT | POSTGRES_PORT |
| --- | --- | --- | --- |
| (default — primary stack) | tap | 8000 | 5432 |

#### Allocation algorithm

For session band `N` (1 ≤ N ≤ 50): `WEB_PORT = 8000 + 10N`, `POSTGRES_PORT = 5432 + 10N`. So band 1 = 8010 / 5442, band 2 = 8020 / 5452, etc.

On `scripts/spawn-session.sh`, the script:
1. Reads the registry.
2. Rejects the chosen name if it already has a row.
3. Walks bands 1..50 and picks the smallest one whose ports are not already in any registry row.
4. After a successful spawn, appends the new row to the registry.

The 10-port spacing per band leaves headroom for additional host-exposed services (Redis, mailcatcher, debugger) within a session without renumbering.

The cap (50) exists to fail loudly rather than allocate into someone else's well-known port range. If you genuinely need more concurrent sessions than that, you have bigger problems than a script error.

#### Format

Line-delimited, single-space-separated columns: `name web db branch spawned`. Comment lines start with `#`. Example:

```
# name web db branch spawned
cli 8010 5442 session/cli 2026-04-27T15:00:00Z
vscode 8020 5452 session/vscode 2026-04-27T15:30:00Z
```

#### Ephemeral by default

Despawn removes the row, freeing the band for reuse. Re-spawning the same name later may or may not return the same band depending on what else has been spawned since. If sticky-band behavior is wanted, a future `--retain` flag on despawn could preserve the row while removing everything else.

#### Concurrency

Two simultaneous spawns could race and pick the same band. This is genuinely rare in practice and not worth a `flock` (which isn't in macOS's base system anyway). If it becomes a real problem we'll add a lock-directory pattern (`mkdir`-based, portable).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-port-registry-1 | Registry is canonical for live sessions | Proposed | Every active session has exactly one row in `~/tap-sessions/.registry`; despawn removes it. | |
| req-dev-multisession-port-registry-2 | Allocation finds smallest free band | Proposed | Spawn picks the lowest-numbered free band, not a random one. | |
| req-dev-multisession-port-registry-3 | Cap enforced | Proposed | Spawn fails with a clear error when all 50 bands are occupied. | |

### Browser Disambiguation
----
RID: `req-dev-multisession-browser-disambiguation`
Status: `Implemented`

Two zero-infra mechanisms let the developer tell at a glance which session a browser tab points at:

1. **`*.localhost` URL convention.** Modern browsers resolve any `*.localhost` subdomain to `127.0.0.1` natively per RFC 6761 — no `/etc/hosts` edits, no DNS server. Each session is reachable at `http://<name>.tap.localhost:<WEB_PORT>/` (e.g. `http://cli.tap.localhost:8010/`). The hostname is purely a label in the URL bar; the port still does the actual routing. Django's `ALLOWED_HOSTS` includes `.localhost` (leading-dot wildcard) so subdomain access is permitted without per-session config.

2. **`TAP_SESSION_LABEL` env var rendered in the UI.** When set (typically to the same name as the session, e.g. `cli`), the value renders as a `[label]` prefix in the `<title>` (browser tab) and as a colored badge next to the product name in the nav bar. Empty for the primary stack so default behavior is unchanged.

The two mechanisms are independent and complementary — the URL labels the address bar, the badge labels the page chrome. Together they make tab-switching unambiguous without any new infrastructure.

#### Implementation
- `tap/settings.py`: `ALLOWED_HOSTS` default extended to include `.localhost`. New `TAP_SESSION_LABEL` setting reads `TAP_SESSION_LABEL` env var (empty default).
- `tap_web/context_processors.py`: `branding` exposes `session_label` to all templates.
- `tap_web/templates/tap_web/base.html`: title prefix `[label] ` (outside the `{% block title %}` so it applies to all child templates) and a small amber badge in the nav.
- `docker-compose.yml`: `ALLOWED_HOSTS` default updated; `TAP_SESSION_LABEL` passed through with `${TAP_SESSION_LABEL:-}`.
- Per-session `.env.local` (set during onboarding): `TAP_SESSION_LABEL=<name>`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-browser-disambiguation-1 | Subdomain access works | Proposed | `http://cli.tap.localhost:8010/` reaches the session's Django when `ALLOWED_HOSTS` includes `.localhost`. | |
| req-dev-multisession-browser-disambiguation-2 | Title shows label | Proposed | When `TAP_SESSION_LABEL=cli`, the page `<title>` is prefixed with `[cli]`. | |
| req-dev-multisession-browser-disambiguation-3 | Nav shows badge | Proposed | When `TAP_SESSION_LABEL=cli`, the nav bar shows a `cli` badge next to the product name. | |
| req-dev-multisession-browser-disambiguation-4 | Primary stack unchanged | Proposed | With no `TAP_SESSION_LABEL` set, no prefix or badge appears — primary UI is unchanged. | |

### Spawn Script
----
RID: `req-dev-multisession-spawn-script`
Status: `Implemented`

`scripts/spawn-session.sh` provisions a new isolated environment interactively. The script prompts only for decisions the developer must make (Keychain setup if missing, session name) and runs everything else automatically:

1. **Step 0 — Keychain check.** If `tap-dev-default` is missing, offers to set it. macOS-only; non-Darwin platforms skip this step and fall back to env var or random per session.
2. **Step 1 — Session name and band allocation.** Displays the current live sessions from `~/tap-sessions/.registry` (initializing the file with a header on first use). Prompts for a name; validates against `^[a-z][a-z0-9_-]*$` and rejects `default` (reserved for the primary stack). Rejects names already in the registry. Allocates the smallest free band (per [Per-Machine Session Registry](#per-machine-session-registry)) and computes web/db ports. Also runs the stale-Docker pre-check so leftover state from a prior failed spawn (volume or containers under `tap_<name>`) aborts the run cleanly with a "remove this first" message.
3. **Step 2 — Worktree.** Creates the worktree at `~/tap-sessions/<name>` on a new branch `session/<name>`. Aborts if the worktree path already exists. All plugins live in-tree under `plugins/` (no submodules), so no additional worktree setup is needed.
4. **Step 3 — `.env.local`.** Generates fresh `TAP_GRID_ID` via Python's `uuid.uuid7()`. Writes `COMPOSE_PROJECT_NAME`, `WEB_PORT`, `POSTGRES_PORT`, `TAP_GRID_ID`, `TAP_SESSION_LABEL`.
5. **Step 4 — Build + start.** `scripts/dc up -d --build`.
6. **Step 5 — Migrate.** `scripts/dc exec web uv run python manage.py migrate`.
7. **Step 6 — Seed.** `scripts/dc exec web uv run python manage.py import_plugin_grift --all`.
8. **Step 7 — Admin user.** Implements [req-dev-multisession-admin-bootstrap](#admin-user-bootstrap): resolves password (env var → Keychain → random), writes `.dev-credentials`, runs `createsuperuser --noinput`.
9. **Done.** Prints labeled URL, direct URL, admin URL, admin credentials, credentials-file path, and how to attach Claude Code.

The script wires a failure trap that, on any non-zero exit, prints recovery commands for the partial state (despawn + worktree-remove + branch-delete). This isolates the developer from "where did spawn fail and what do I do now" guesswork.

Worktrees live **outside** the repo at `~/tap-sessions/<name>` to keep the main tree uncluttered.

#### Future

A `--non-interactive` mode (taking `--name`, `--admin-password` flags) would make the script CI-friendly. Not v1. Auto-allocation of new port bands (when "make it fast" mode lands) would skip the registry-edit-first requirement for ad-hoc names.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-spawn-script-1 | Single-command spawn | Proposed | `scripts/spawn-session.sh` produces a running, seeded stack with admin user at the registered port band. | |
| req-dev-multisession-spawn-script-2 | Idempotent failure | Proposed | Re-running spawn for a session with an existing worktree aborts before any mutation. | |
| req-dev-multisession-spawn-script-3 | Registry collision rejection | Proposed | Names already present in `~/tap-sessions/.registry` are rejected with a clear error pointing at despawn. | |
| req-dev-multisession-spawn-script-4 | Failure trap recovery | Proposed | On non-zero exit during spawn, the script prints recovery commands for the partial state. | |

### Granular Grift Import Failure Mode
----
RID: `req-dev-multisession-spawn-import-strict`
Status: `Backlog`

Today, step 6 of the spawn script (`import_plugin_grift --all`) is fail-fast: any bundle failing validation raises `CommandError` and aborts the spawn so the developer doesn't end up in a session with borked data. That's the right default but it has one obvious downside — a single bad bundle aborts the whole spawn, even when nineteen others would have imported fine.

This requirement adds an opt-in continue-on-error mode so developers iterating on a single plugin can still get a session up:

- `--strict` (default for spawn): exit non-zero on the first failed bundle and abort. Matches today's behavior.
- `--continue-on-error`: import every bundle the validator accepts, log each failure inline, and exit non-zero at the end with a one-line summary of what failed. Spawn does **not** use this mode by default — it's invoked manually after spawn (`scripts/dc exec web uv run python manage.py import_plugin_grift --all --continue-on-error`) when the developer wants a partial seed for plugin development.

The motivating event: 2026-05-06, a `genericom/ec2-internals.grift.json` bundle failed `envelope_payload_name_mismatch` validation; spawn step 6 wrote a red error line but exited 0, and the session looked "ready" with silently-missing data. Layer 1 of the fix (`req-dev-multisession-spawn-script-5` below) made the import command exit non-zero. This requirement is the optional layer 2.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-spawn-import-strict-1 | Strict-by-default | Backlog | `import_plugin_grift` exits non-zero on first failed bundle when `--continue-on-error` is not passed. | Already implemented as part of req-dev-multisession-spawn-script-5. |
| req-dev-multisession-spawn-import-strict-2 | Continue-on-error flag | Backlog | `--continue-on-error` causes the command to attempt every bundle and exit non-zero at the end with a per-bundle summary. | |
| req-dev-multisession-spawn-import-strict-3 | Spawn defaults to strict | Backlog | `scripts/spawn-session.sh` invokes import without `--continue-on-error`, so a bad bundle aborts the spawn and fires the failure trap. | |

### Session → Main Push Workflow
----
RID: `req-dev-multisession-push-workflow`
Status: `Implemented`

Multi-worktree development needs an unambiguous rule for how changes leave a session and become part of `main`. Without it, parallel sessions race each other on `origin/main`, new session spawns start from stale code, and the discipline becomes "whatever the current developer remembers." This requirement codifies the rule so every session — human or agent — follows the same four-step pattern.

#### The discipline

1. **Never edit `main` directly.** All work happens on a `session/<name>` branch inside a session worktree under `~/tap-sessions/<name>/`. The primary worktree at `~/tap-sessions/main/` is a passive reflection of `origin/main`; its working tree should never have uncommitted changes. Following this rule alone makes everything below succeed by default.
2. **Pre-push merge.** Before pushing to advance `main`, the session worktree must catch up to whatever sibling sessions have already landed:

   ```
   git fetch origin main
   git merge origin/main
   ```

   Resolve any conflicts on the session branch, commit, then continue. Skipping this step risks a non-fast-forward rejection at push time or, worse, silent overwrite of another session's work if anyone ever uses `--force`.
3. **Push.** Advance `origin/main` directly from the session branch's tip:

   ```
   git push origin session/<name>:main
   ```

   This pattern keeps the session branch alive on origin under its own name *and* fast-forwards `origin/main`, all in one operation. There is no separate "merge into main" commit.
4. **Sync the primary worktree.** Immediately after the push, advance the local `main` ref in the primary worktree so it matches `origin/main`:

   ```
   git -C /Users/george/tap-sessions/main pull --ff-only
   ```

   This step is load-bearing: `scripts/spawn-session.sh` runs `git worktree add <path> -b session/<name>` with no starting-point argument, which means new session branches start from whatever the local `main` ref currently points at. A stale local main = every newly-spawned session starts from old code. The post-push pull is the discipline that keeps spawn-session always-current.

#### Why the naive form does not work

The intuitive command for step 4 is `git fetch origin main:main` from inside the session worktree. Git rejects it:

```
fatal: refusing to fetch into branch 'refs/heads/main' checked out at '/Users/george/tap-sessions/main'
```

A branch ref cannot be advanced from outside the worktree that has it checked out — git enforces this to prevent the working tree and the ref from desynchronizing. The fetch-and-fast-forward has to happen *inside* the main worktree, which is exactly what `git -C /path/to/main pull --ff-only` does without requiring a `cd`.

If `pull --ff-only` ever fails with "not a fast-forward", it means a sibling worktree pushed to main between this session's pre-push merge and this push. Surface the error, re-merge `origin/main` into the session branch, and re-run the push + post-push pull.

#### What a partial workaround looks like

`git fetch origin main` (no refspec) updates only the remote-tracking branch `origin/main`. It avoids the "refusing to fetch into checked-out branch" error but does **not** advance local `main`. It's a safe fallback that keeps `origin/main` current for the *next* session's pre-push merge, but it leaves the spawn-session staleness problem unsolved. Use only when `pull --ff-only` itself fails (e.g. someone forgot the "never edit on main" rule and left uncommitted changes); fix the underlying issue rather than relying on this fallback.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-push-workflow-1 | Never edit on main | Implemented | The primary worktree at `~/tap-sessions/main/` MUST NOT carry uncommitted changes or local commits that haven't traveled through a session branch. All edits live on `session/<name>` branches. | |
| req-dev-multisession-push-workflow-2 | Pre-push merge required | Implemented | Before advancing `origin/main`, the session branch MUST be fast-forwardable to its target by merging `origin/main` first. | Prevents non-fast-forward push rejections and overwrites. |
| req-dev-multisession-push-workflow-3 | Push form is `session:main` | Implemented | The push command is `git push origin session/<name>:main`. This advances `origin/main` and preserves the session branch on origin in one operation. | No separate merge commit; no checkout of `main`. |
| req-dev-multisession-push-workflow-4 | Post-push primary sync | Implemented | After the push, the local `main` ref MUST be advanced via `git -C /Users/george/tap-sessions/main pull --ff-only`. | Load-bearing for `scripts/spawn-session.sh` correctness. |
| req-dev-multisession-push-workflow-5 | Naive fetch form is wrong | Implemented | `git fetch origin main:main` from a session worktree is explicitly NOT the post-push sync. Git refuses to fast-forward a ref that's checked out elsewhere; the operation must run inside the main worktree (via `git -C`). | Documented so agents don't reinvent the workaround. |
| req-dev-multisession-push-workflow-6 | Spawn-side guard | Implemented | `scripts/spawn-session.sh` refreshes local `main` from `origin/main` BEFORE creating the new session worktree. The pull MUST run inside the main worktree (via `git -C "$HOME/tap-sessions/main" pull --ff-only origin main`), not via `$REPO` — `$REPO` is wherever the script was invoked from (possibly a session worktree), and pulling there would advance the session branch rather than main. A non-fast-forward (uncommitted changes on main, divergent local main) aborts the spawn loudly rather than silently starting a session from stale code. If the main worktree is missing at `$HOME/tap-sessions/main` (non-standard layout), the guard warns and skips rather than aborting. | Belt-and-suspenders with the post-push sync: that keeps siblings current between spawns; this guard ensures the *next* spawn is current even if the discipline slipped. |

#### Future

- A `scripts/promote-to-main.sh` wrapper could codify steps 2–4 as one invocation. Out of scope for v0 because the four commands are short and the discipline is the point; agents that follow the spec verbatim already get the right behavior. If multiple humans start landing work without agent assistance, the wrapper becomes more valuable.
- A pre-push git hook could refuse `session/<name>:main` if the pre-push merge step was skipped, but hook installation in fresh worktrees is its own coordination problem.

### Admin User Bootstrap
----
RID: `req-dev-multisession-admin-bootstrap`
Status: `Implemented`

The spawn script must create a Django admin superuser in each new session's database, unattended, without prompting. This is a sub-feature of [Spawn Script](#spawn-script) but specified separately because the credential resolution model has its own design surface.

#### Username and email — fixed

- **Username:** `admin`.
- **Email:** `admin@<session>.tap.localhost` (e.g. `admin@cli.tap.localhost`).

Both are deterministic from the session name. Not configurable in v0 to keep the spawn flow simple.

#### Password resolution order

The spawn script resolves the admin password by checking these sources in order; the first that yields a value wins:

1. `--admin-password=<value>` flag passed to spawn (explicit, highest priority).
2. `TAP_DEV_ADMIN_PASSWORD` environment variable.
3. **macOS Keychain** (Darwin only): `security find-generic-password -s tap-dev-default -a admin -w 2>/dev/null`. Silently falls through if Keychain is locked, the entry is missing, or the platform is not Darwin.
4. **Default:** generate a fresh random password — `python3 -c "import secrets; print(secrets.token_urlsafe(18))"`.

Sources 1–3 give the developer a way to pin a stable password across sessions when convenience matters. Source 4 keeps the secure default in place.

#### Credentials file

Whatever password is resolved, the spawn script writes it (along with username, email, session name, and timestamp) to `<worktree>/.dev-credentials`. The file is the runtime interface — both the attached Claude session and the developer read it from a known path. Format mirrors `.env`:

```
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_PASSWORD=<resolved>
DJANGO_SUPERUSER_EMAIL=admin@<session>.tap.localhost
SESSION_NAME=<session>
GENERATED_AT=<ISO-8601>
```

`.dev-credentials` is gitignored (a `.dev-credentials` rule is added to `.gitignore` alongside `.env.local`).

#### Superuser creation

The spawn script invokes Django's built-in unattended path:

```bash
scripts/dc exec \
  -e DJANGO_SUPERUSER_USERNAME \
  -e DJANGO_SUPERUSER_PASSWORD \
  -e DJANGO_SUPERUSER_EMAIL \
  web uv run python manage.py createsuperuser --noinput
```

Env vars are sourced from `.dev-credentials`. The command is idempotent in spawn flow because the database is freshly migrated (no existing admin user).

#### Echo at completion

Spawn ends by printing the resolved credentials and the session URL to stdout once, so a developer running spawn from a terminal sees them without having to read the file. The credentials file is named in the output ("Saved to `<worktree>/.dev-credentials`") so terminal-loss is recoverable.

#### Despawn behavior

`scripts/despawn-session.sh` removes the worktree, which deletes `.dev-credentials` along with everything else. The macOS Keychain entry (if used) is **not** touched by default — it's intended to outlive sessions. A `--purge-keychain` flag on despawn explicitly removes the `tap-dev-default` Keychain entry when the developer wants a clean slate.

#### Threat model and limits

`.dev-credentials` is a plaintext password on disk. This is acceptable for dev environments (no worse than `.env.local` carrying database credentials) but worth being explicit:

- **In scope:** preventing accidental commit (gitignored), preventing cross-session leakage (per-worktree, random by default).
- **Out of scope:** protecting against an attacker with filesystem access to the dev machine. Anyone who can read `.env.local` can read `.dev-credentials`, and anyone who can run shell commands as the developer can read the macOS Keychain (eventually, after Keychain auth — Keychain raises the bar but does not eliminate the threat).

Hardening beyond this (e.g. SSH-key-encrypted credentials, ephemeral admin tokens) is a Phase 4 concern, not Phase 2.

#### Cross-platform note

The Keychain branch (#3 above) is wrapped in a Darwin check. Linux / Windows dev machines fall through to env var or random — same UX, different ceiling on convenience.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-admin-bootstrap-1 | Admin user created unattended | Proposed | After spawn, `admin` superuser exists in the session DB and can log in to `/admin/`. | |
| req-dev-multisession-admin-bootstrap-2 | Resolution order honored | Proposed | `--admin-password`, `TAP_DEV_ADMIN_PASSWORD`, Keychain, random — checked in that order; first hit wins. | |
| req-dev-multisession-admin-bootstrap-3 | Credentials file written | Proposed | `<worktree>/.dev-credentials` exists with all five fields and is gitignored. | |
| req-dev-multisession-admin-bootstrap-4 | Echoed once at spawn | Proposed | Spawn output names the username, password, email, URL, and credentials-file path. | |
| req-dev-multisession-admin-bootstrap-5 | Keychain optional | Proposed | Spawn succeeds on a machine with no `tap-dev-default` Keychain entry by falling through to random generation. | |
| req-dev-multisession-admin-bootstrap-6 | Despawn cleans up | Proposed | After despawn, `.dev-credentials` is gone (worktree removed). Keychain entry remains unless `--purge-keychain`. | |

### List Script
----
RID: `req-dev-multisession-list-script`
Status: `Proposed`

`scripts/list-sessions.sh` shows live state across all sessions: name, worktree path, branch, project name, ports, container status. Convenience for when 3+ sessions are running.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-list-script-1 | Live status | Proposed | List script shows running and stopped sessions with their ports and worktree paths. | |

### Name-Based Routing via Reverse Proxy
----
RID: `req-dev-multisession-named-routing`
Status: `Backlog`

A shared Traefik (or nginx-proxy) container running on the host outside any session's compose stack listens on `:80` and routes by `Host` header. Each session's compose adds router labels (e.g. `Host(\`cli.tap.localhost\`)`) and joins a shared `tap_proxy` network. Result: each session is reachable at `http://<name>.tap.localhost/` — **no port** in the URL — and Traefik forwards to the right `tap_<name>-web-1`. Direct `localhost:<WEB_PORT>` access continues to work as a fallback.

#### Status Details

Backlog because [Browser Disambiguation](#browser-disambiguation) already gives us human-readable URLs (`<name>.tap.localhost:<port>`) and visual labels in the UI without any new infrastructure. Traefik adds clean port-free URLs but introduces a shared singleton with its own lifecycle; promote when port management becomes the friction point or we cross enough sessions that remembering `:8010` vs `:8020` is the bottleneck.

#### Future Implementation Sketch

- Top-level `docker/proxy/` directory holds a Traefik compose file and config.
- A `scripts/proxy.sh up|down` controls the singleton.
- Spawn script adds Traefik labels to the new session's compose override and joins the shared network.
- Smoke test grows an ACID that verifies `curl -H 'Host: <name>.tap.localhost' http://localhost/` reaches the right session.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-named-routing-1 | Port-free URL works | Backlog | `http://<name>.tap.localhost/` reaches the named session via the proxy. | |
| req-dev-multisession-named-routing-2 | Direct port still works | Backlog | `http://localhost:<WEB_PORT>/` continues to work as a fallback. | |
| req-dev-multisession-named-routing-3 | Proxy lifecycle script | Backlog | `scripts/proxy.sh up|down` controls the shared Traefik singleton. | |

## Developer Onboarding

The canonical, step-by-step procedure for spawning a new isolated session lives in the doc [docs/doc-dev-multisession-onboarding.md](../docs/doc-dev-multisession-onboarding.md), owned by [spec-dev-multisession-onboarding-doc.md](spec-dev-multisession-onboarding-doc.md). Read the doc to onboard; this spec stays focused on *what* the system does, not *how* to use it.

After onboarding completes, the developer attaches an agent/editor session inside the new worktree, and that session runs the smoke tests in [spec-dev-multisession-smoketest.md](spec-dev-multisession-smoketest.md). Teardown is documented in [spec-dev-multisession-teardown.md](spec-dev-multisession-teardown.md).

## Operational Notes

### Per-session Claude Code attachment

Each worktree is a self-contained working directory, so attach Claude Code or Codex against the worktree before starting work. Claude CLI picks up `pwd`, Codex Desktop picks up the path passed to `codex app <worktree>`, and VSCode picks up the workspace folder it's opened against.

### Shared infrastructure

- **Playwright MCP**: stateless per call, safe to share across sessions. Each Claude session points at the same MCP server.
- **`.git`**: worktrees share the underlying repo, so commits/branches are visible across sessions immediately. Cross-session merges happen locally without a GitHub round-trip.

### Future services

To add a new host-exposed service (Redis, mailcatcher, debugger):
1. Add the service to `docker-compose.yml` with `${SERVICE_PORT:-<default>}:<container-port>` mapping.
2. Allocate a fixed offset within each session's 10-port band (e.g., session `cli` = `tap_cli`, ports `8010` web, `5442` postgres, `6310` redis).
3. Update the port registry table in this spec.
4. Update spawn script's `.env.local` template.

## Status Vocabulary

Standard TAP states: `Proposed`, `Approved for Development`, `In Development`, `Implemented`, `Verified`, `Refactoring`, `Deprecating`, `Deprecated`, `Backlog`.
