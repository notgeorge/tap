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
| 5. | Predictable Resource Allocation | Ports and namespaces are deterministic and human-memorable, not auto-allocated, while the design leaves room for auto-allocation later. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-dev-multisession-compose-parameterized | [Parameterized Compose Stack](#parameterized-compose-stack) | Implemented | Phase 1 |
| req-dev-multisession-env-cascade | [Env File Cascade](#env-file-cascade) | Implemented | Phase 1 |
| req-dev-multisession-port-registry | [Fixed-by-Name Port Registry](#fixed-by-name-port-registry) | Implemented | Phase 1 |
| req-dev-multisession-browser-disambiguation | [Browser Disambiguation](#browser-disambiguation) | Proposed | Phase 1 |
| req-dev-multisession-spawn-script | [Spawn Script](#spawn-script) | Proposed | Phase 2 |
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

#### Implementation
- `docker-compose.yml` uses `${VAR:-default}` substitution syntax so the file remains valid with no `.env` present.
- A checked-in `.env` carries the defaults so `docker compose up` works out of the box in the primary checkout.
- Container-internal ports (`8000`, `5432`) stay fixed; only host-side mappings move.

#### Future
If we add Redis, mailcatcher, or other host-exposed services, follow the same pattern: add `<SERVICE>_PORT` variable with a default, allocate it a fixed offset in the port registry.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-compose-parameterized-1 | Default behavior unchanged | Proposed | `docker compose up` from a fresh clone with the checked-in `.env` produces containers named `tap-web-1` / `tap-db-1` listening on host `8000` / `5432`. | |
| req-dev-multisession-compose-parameterized-2 | Override applied | Proposed | Setting `COMPOSE_PROJECT_NAME=tap_cli WEB_PORT=8001 POSTGRES_PORT=5433` and running compose produces containers in the `tap_cli` project listening on host `8001` / `5433`. | |
| req-dev-multisession-compose-parameterized-3 | Two stacks coexist | Proposed | Two checkouts running compose with different namespaces produce two simultaneously-running, non-conflicting Docker stacks. | |

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

### Fixed-by-Name Port Registry
----
RID: `req-dev-multisession-port-registry`
Status: `Implemented`

Each session name maps to a fixed port offset to keep ports human-memorable across spawns. The registry lives in `scripts/sessions.txt` (or equivalent), one entry per name, allocated in offsets of 10:

| Name | COMPOSE_PROJECT_NAME | WEB_PORT | POSTGRES_PORT |
| --- | --- | --- | --- |
| (default) | tap | 8000 | 5432 |
| cli | tap_cli | 8010 | 5442 |
| vscode | tap_vscode | 8020 | 5452 |
| (next) | tap_<name> | 80N0 | 54N2 |

The 10-port spacing per session leaves headroom for adding services (Redis, mailcatcher, debugger) without re-numbering.

#### Future
When we move to "make it fast" mode, replace this registry with auto-allocation from a pool (e.g., next free port in 8000–8099), trading determinism for zero-config spawns. The fixed-name registry stays useful for muscle-memory sessions; auto-allocation would be the default for ad hoc ones.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-port-registry-1 | Registry is canonical | Proposed | The port table in this spec matches what spawn script writes to `.env.local`. | |

### Browser Disambiguation
----
RID: `req-dev-multisession-browser-disambiguation`
Status: `Proposed`

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
Status: `Proposed`

`scripts/spawn-session.sh <name>` provisions a new isolated environment in one command:

1. Creates a git worktree at `~/tap-sessions/<name>` on a new branch `session/<name>`.
2. Generates `.env.local` in the worktree with `COMPOSE_PROJECT_NAME`, `WEB_PORT`, `POSTGRES_PORT` from the registry, and a freshly generated `TAP_GRID_ID`.
3. Builds and starts the stack: `scripts/dc up -d --build`.
4. Runs `scripts/dc exec web uv run python manage.py migrate`.
5. Runs `scripts/dc exec web uv run python manage.py import_plugin_grift --all` to seed.
6. Prints next-step instructions: `cd` path, web URL, and the command to attach Claude Code.

Worktrees live **outside** the repo at `~/tap-sessions/<name>` to keep the main tree uncluttered.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-spawn-script-1 | Single-command spawn | Proposed | `scripts/spawn-session.sh foo` produces a running, seeded stack at the registered port. | |
| req-dev-multisession-spawn-script-2 | Idempotent failure | Proposed | Re-running spawn for an existing name fails fast with a clear error rather than partially mutating state. | |

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

After onboarding completes, the developer attaches a Claude Code session inside the new worktree, and that session runs the smoke tests in [spec-dev-multisession-smoketest.md](spec-dev-multisession-smoketest.md). Teardown is documented in [spec-dev-multisession-teardown.md](spec-dev-multisession-teardown.md).

## Operational Notes

### Per-session Claude Code attachment

Each worktree is a self-contained working directory, so attach Claude Code (CLI or VSCode) by `cd`-ing into the worktree before starting it. The VSCode extension picks up the workspace folder it's opened against; the CLI picks up `pwd`.

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
