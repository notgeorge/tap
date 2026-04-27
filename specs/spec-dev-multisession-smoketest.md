# Multi-Session Dev Environment — Smoke Test

## Philosophy

After a developer follows the onboarding procedure in [spec-dev-multisession.md](spec-dev-multisession.md) and attaches a Claude Code session inside the new worktree, that session needs a fast, deterministic way to verify the environment is healthy: namespaced correctly, reachable on the assigned ports, migrated, seeded, and not colliding with the primary stack. This spec captures the smoke test as an ordered set of checks with exact commands and expected output. The attached Claude session (or developer) runs them top-to-bottom; any failure halts and is reported.

The smoke test is also the regression harness for `req-dev-multisession-compose-parameterized-3` (two stacks coexist) and the future spawn-script's success criterion.

## Goals

|   |   |  |
| :---: | --- | --- |
| 1. | Detect Misconfig | Catch wrong project namespace, wrong host ports, missing env vars, or broken `.env.local`. |
| 2. | Prove Isolation | Confirm the new stack does not share containers, networks, volumes, or ports with the primary stack. |
| 3. | Prove Data Pipeline | Confirm migrations applied and plugin data seeded. |
| 4. | Fast Feedback | Whole suite runs in under a minute on a warm machine. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-dev-multisession-smoketest-runtime | [Runtime Reachability](#runtime-reachability) | Proposed | Stack up + responsive |
| req-dev-multisession-smoketest-isolation | [Isolation](#isolation) | Proposed | No collision with primary |
| req-dev-multisession-smoketest-data | [Data Plane](#data-plane) | Proposed | Migrations + seed |

### Runtime Reachability
----
RID: `req-dev-multisession-smoketest-runtime`
Status: `Proposed`

The new session's stack must be running with the namespace and ports declared in `.env.local`, and Django must respond on the configured `WEB_PORT`.

#### Procedure

Run from inside the new worktree (`~/tap-sessions/<name>`):

```bash
# 1. Resolve the override layer correctly.
scripts/dc config | grep -E '^(name:|        published:)' | head -5
```

Expected: `name:` matches your `COMPOSE_PROJECT_NAME` (e.g. `tap_cli`), and the two `published:` lines match your `WEB_PORT` and `POSTGRES_PORT`.

```bash
# 2. Both services are running and healthy.
scripts/dc ps
```

Expected: 2 services (`db`, `web`), `db` shows `(healthy)`, `web` shows `running`.

```bash
# 3. Web responds on the assigned host port.
WEB_PORT=$(grep ^WEB_PORT .env.local | cut -d= -f2)
curl -sI http://localhost:${WEB_PORT}/ | head -1
```

Expected: an HTTP status line (200/302/etc — any response proves the port is bound and Django is serving).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-smoketest-runtime-1 | Override resolved | Proposed | `scripts/dc config` shows the project name and ports from `.env.local`. | |
| req-dev-multisession-smoketest-runtime-2 | Services up | Proposed | `scripts/dc ps` shows `db` healthy and `web` running. | |
| req-dev-multisession-smoketest-runtime-3 | Web responds | Proposed | `curl http://localhost:${WEB_PORT}/` returns an HTTP status line. | |

### Isolation
----
RID: `req-dev-multisession-smoketest-isolation`
Status: `Proposed`

The new stack must not share containers, networks, volumes, or host ports with the primary `tap` stack. If the primary is up, both must be up simultaneously without conflict; if the primary is down, that's fine — the check is about absence of collision artifacts.

#### Procedure

```bash
# 1. Container names are namespaced (prefixed with COMPOSE_PROJECT_NAME).
docker ps --format '{{.Names}}' | grep -E '^(tap-|tap_)'
```

Expected: at least one row prefixed with your `COMPOSE_PROJECT_NAME` (e.g. `tap_cli-web-1`); no other project's container names overlap.

```bash
# 2. Volumes are namespaced.
docker volume ls --format '{{.Name}}' | grep -E '^(tap_|tap-)'
```

Expected: a `<project>_postgres_data` volume for your project. If the primary `tap` stack is also up, you'll see `tap_postgres_data` as a separate row.

```bash
# 3. Host ports do not collide.
PROJECT=$(grep ^COMPOSE_PROJECT_NAME .env.local | cut -d= -f2)
docker compose -p "$PROJECT" port web 8000
docker compose -p "$PROJECT" port db 5432
```

Expected: each prints `0.0.0.0:<your-port>`. The reported ports must match your `.env.local`.

```bash
# 4. If the primary is up, confirm both projects coexist with distinct ports.
docker compose -p tap ps 2>/dev/null && docker compose -p "$PROJECT" ps
```

Expected (if primary is up): both project listings show 2 services each, with non-overlapping host ports.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-smoketest-isolation-1 | Containers namespaced | Proposed | Container names carry the project prefix. | |
| req-dev-multisession-smoketest-isolation-2 | Volumes namespaced | Proposed | Postgres volume name is project-scoped. | |
| req-dev-multisession-smoketest-isolation-3 | Ports match `.env.local` | Proposed | `docker compose port` returns the configured host ports. | |
| req-dev-multisession-smoketest-isolation-4 | Coexistence with primary | Proposed | When primary is up, both projects run simultaneously. | Skip if primary is down |

### Data Plane
----
RID: `req-dev-multisession-smoketest-data`
Status: `Proposed`

Migrations must be applied and plugin seed data loaded.

#### Procedure

```bash
# 1. No unapplied migrations.
scripts/dc exec web uv run python manage.py migrate --check
```

Expected: exits 0 with no "would apply" output. Non-zero means migrations are pending — return to onboarding step 5.

```bash
# 2. Seed data present (Entity table non-empty).
scripts/dc exec web uv run python manage.py shell -c \
  "from tap_grid.models import Entity; print(Entity.all_objects.count())"
```

Expected: a positive integer (typically dozens to thousands depending on what plugins are installed). Zero means seed didn't run — return to onboarding step 6.

```bash
# 3. TAP_GRID_ID is the value from .env.local (not the default).
scripts/dc exec web env | grep ^TAP_GRID_ID=
EXPECTED=$(grep ^TAP_GRID_ID .env.local | cut -d= -f2)
echo "Expected: $EXPECTED"
```

Expected: the two values match. Mismatch means the override didn't apply — most likely `.env.local` is missing or `scripts/dc` wasn't used.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-multisession-smoketest-data-1 | Migrations applied | Proposed | `migrate --check` exits 0. | |
| req-dev-multisession-smoketest-data-2 | Seed loaded | Proposed | `Entity.all_objects.count()` > 0. | |
| req-dev-multisession-smoketest-data-3 | Grid ID matches override | Proposed | Container env `TAP_GRID_ID` matches `.env.local`. | |

## Status Vocabulary

Standard TAP states: `Proposed`, `Approved for Development`, `In Development`, `Implemented`, `Verified`, `Refactoring`, `Deprecating`, `Deprecated`.
