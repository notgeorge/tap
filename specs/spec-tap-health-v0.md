# TAP Health v0 Specification

## Philosophy

A TAP instance can stand up "successfully" — migrations applied, server listening, boot profile applied — and still be subtly broken in a way nothing exercises until a user trips over it. That is exactly what happened on 2026-06-26: a fresh instance booted green but 500'd on the first login because the `DatabaseCache` table (`tap_cache`) is provisioned outside migrations and nothing wired it in (`docs/aar/2026-06-26-tap-cache-latent-provisioning.md`). The class is **latent provisioning faults**, and every guard in place at the time was blind to it by construction: the test suite swaps `DatabaseCache` for `LocMemCache`, and `spawn-session.sh`'s post-boot check treated any HTTP response — including a 500 — as "up."

This spec defines the **health system** that closes that class: a deliberately small, dependency-free pair that exercises the *real* assembled instance.

- A **fail-at-boot system check** that refuses to come up when a known provisioning precondition is missing — the precondition becomes a loud startup error, not a latent runtime fault.
- A **verify-and-monitor endpoint** (`/healthz`) that probes the real backends (database, cache round-trip, queue) and reports a machine-readable status — the single surface that serves the spawn post-boot gate, container readiness probes, future CI smoke, and a pre-demo readiness check.

The guiding principle: **a comment asserting an operational guarantee is a latent lie until a step or test fails when it is false.** The health system turns "provisioning is supposed to have happened" into something that actually fails loudly when it has not. It is intentionally hand-rolled (no `django-health-check` dependency) — the surface is ~50 lines and TAP owns it, matching the no-external-dependency posture that also keeps cache and sessions DB-backed rather than on Redis.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Real Backends | Health is judged by exercising the actual db / cache / queue, not by "the process is listening." |
| 2. | Fail Loud, Fail Early | A missing provisioning precondition is a startup error, not a latent runtime 500. |
| 3. | One Surface, Many Uses | `/healthz` serves the spawn gate, readiness probes, CI smoke, and pre-demo checks alike. |
| 4. | Dependency-Free | The system is hand-rolled in TAP core; it adds no third-party health dependency. |
| 5. | Safe To Expose | The endpoint answers unauthenticated but leaks only coarse status, never secrets or internals. |

## Prior Art

- **Django system check framework** (`django.core.checks`) — static, registerable checks that run before/at `migrate` and on explicit `check`. Database-tagged checks (`Tags.database`) only run when a DB alias is in play, so a DB-touching check does not run on every management command and does not violate TAP's "no DB access in `AppConfig.ready()`" rule. This is the mechanism behind the fail-at-boot half.
- **NetBox** — ships no health endpoint in core (long-standing requests: netbox-community/netbox #3291, #8831); the community `netbox-healthcheck-plugin` (built on `django-health-check`) probes db + a real cache set/get + the Redis queue, exposed as JSON for monitoring. TAP adopts the *probe shape* (real cache round-trip is the key idea) but bakes a minimal version into core rather than taking a dependency or a plugin.
- **Kubernetes liveness/readiness probes** — the `/healthz` spelling and the 200/503 contract follow the conventional readiness-probe shape so container orchestration can consume it directly.

## Relationship To Other Specs

- **`docs/aar/2026-06-26-tap-cache-latent-provisioning.md`** — the incident this system answers; the source of the "pair" framing (fail-at-boot check + verify/monitor endpoint).
- **`specs/spec-dev-validation.md`** — the Validation Map carries the "assembled-instance health" surface and its honest guard status; `/healthz` + the boot check + the spawn gate are the guards that row tracks.
- **`specs/spec-tap-boot-v0.md`** — boot converges *instance state*; this system guards the *schema/provisioning preconditions* beneath it. The cache-table check is the boot-time counterpart to the runtime endpoint. The standing convergence target (one canonical provisioning sequence) is recorded in the AAR and carried toward the plugin-config / pre-Django-install work.
- **CLAUDE.md logging conventions** — probe diagnostics use the bare `[<hex>]` site-token convention and `%s` placeholders.

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-tap-health-endpoint | [Health Endpoint](#health-endpoint) | Implemented | `/healthz` JSON, 200/503 contract, never-cached |
| req-tap-health-probes | [Real-Backend Probes](#real-backend-probes) | Implemented | Independent db / cache-round-trip / queue probes; report never raise |
| req-tap-health-unauth | [Unauthenticated, Coarse-Status Only](#unauthenticated-coarse-status-only) | Implemented | Login-exempt; exposes only status strings + error detail |
| req-tap-health-bootcheck | [Boot-Time Provisioning Check](#boot-time-provisioning-check) | Implemented | DB-tagged system check; missing `tap_cache` → loud `tap_boot.E001` |
| req-tap-health-nongoals | [v0 Non-Goals](#v0-non-goals) | Proposed | Metrics, auth'd diagnostics, worker-liveness, plugin probes deferred |

### Health Endpoint
----
RID: `req-tap-health-endpoint`
Status: `Implemented`

TAP core exposes a health endpoint at the stable path `/healthz` that reports the instance's real backend health as JSON with an HTTP status code consumable by an orchestrator or a script.

#### Implementation

- The view is `tap/health.py:health_view`, mounted in `tap/urls.py` at `/healthz`, **before** the `tap_web` catch-all so the path is never shadowed.
- The response body is `{"status": "healthy"|"unhealthy", "checks": {<name>: {"status": ..., ["detail": ...]}}}`.
- HTTP status is **200** when every *critical* probe is healthy, **503** otherwise (`req-tap-health-probes` defines the critical set).
- The view is decorated `@never_cache` so an intermediary or the browser never serves a stale health verdict.
- The endpoint takes no input; the request object is unused.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-health-endpoint-1 | Stable Path | Implemented | `/healthz` is mounted ahead of the catch-all and resolves by the name `healthz`. | |
| req-tap-health-endpoint-2 | JSON Shape | Implemented | The body is `{"status", "checks"}` with one entry per probe. | |
| req-tap-health-endpoint-3 | 200/503 Contract | Implemented | 200 when all critical probes healthy; 503 otherwise. | tests: all-healthy, cache-broken |
| req-tap-health-endpoint-4 | Never Cached | Implemented | The response carries no-cache semantics. | |

### Real-Backend Probes
----
RID: `req-tap-health-probes`
Status: `Implemented`

Health is judged by exercising the real backends independently. Each probe reports its own status and never raises — a probe failure is data, not an exception.

#### Implementation

- **db** (`_check_db`) — a trivial `SELECT 1` over the default connection.
- **cache** (`_check_cache`) — a real `cache.set` then `cache.get` round-trip with a unique probe key; the observed value must equal the written token, else `unhealthy`. This is the probe that catches the `tap_cache` fault: a missing `DatabaseCache` table surfaces here as an `unhealthy` cache probe (with the `relation "tap_cache" does not exist` detail) instead of a 500 on the first real cache access. The probe key is deleted after the round-trip.
- **queue** (`_check_queue`) — a light, best-effort reachability check (the DB-backed Steady Queue's `steady_queue_job` table is present). It is **non-critical**: any indeterminate result reports `"unknown"` and never flips the overall status. It deliberately does not probe worker liveness.
- **Critical set** = `(db, cache)`. Only critical probes affect the 200/503 verdict; `queue` is informational.
- Every probe wraps its work in a `try/except` that logs at the appropriate level (`warning` for critical, `info` for the non-critical queue) and returns a status dict — the view can never 500 on a probe error.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-health-probes-1 | DB Probe | Implemented | The db probe issues a trivial query over the default connection. | |
| req-tap-health-probes-2 | Cache Round-Trip | Implemented | The cache probe is a real set→get round-trip whose value must match. | the demo-fault catcher; tests: all-healthy, cache-broken |
| req-tap-health-probes-3 | Queue Best-Effort | Implemented | The queue probe is non-critical and reports `unknown` rather than failing on an indeterminate result. | |
| req-tap-health-probes-4 | Critical Set | Implemented | Only db and cache are critical; queue never flips the overall status. | |
| req-tap-health-probes-5 | Probes Report, Never Raise | Implemented | A probe error is caught and reported, never propagated as a 500. | test: cache-broken |

### Unauthenticated, Coarse-Status Only
----
RID: `req-tap-health-unauth`
Status: `Implemented`

The endpoint must answer without authentication so an orchestrator or a pre-auth boot gate can probe it, while exposing only coarse status — never secrets, configuration, or internal topology.

#### Implementation

- `/healthz` is added to `settings.TAP_LOGIN_EXEMPT_PREFIXES` so the login-wall middleware lets it through; an anonymous request gets the health verdict, not a 302 to login.
- The payload contains only probe status strings (`healthy`/`unhealthy`/`unknown`) and a short error `detail` string for a failed probe. It exposes no secret material, no settings values, and no per-record data. The error `detail` is the exception's message (e.g. a missing-table name) — coarse operational signal, deliberately not a stack trace or configuration dump.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-health-unauth-1 | Login-Exempt | Implemented | An anonymous request is answered (200/503), not redirected to login. | test: login-exempt |
| req-tap-health-unauth-2 | Coarse Status Only | Implemented | The payload carries only status strings and short error details — no secrets, settings, or record data. | |

### Boot-Time Provisioning Check
----
RID: `req-tap-health-bootcheck`
Status: `Implemented`

The fail-at-boot half of the pair: a Django system check that turns a known latent provisioning precondition into a loud startup error.

#### Implementation

- `tap_boot/checks.py:check_database_cache_table`, registered `@register(Tags.database)` and wired in `tap_boot.apps.TapBootConfig.ready()` by *importing* the module (import registers; the DB access happens later when the check runs — so it does not breach the "no DB in `ready()`" rule).
- When the default cache backend is `DatabaseCache`, the table named by its `LOCATION` must exist on the default database; otherwise the check returns a single `checks.Error` `tap_boot.E001` whose hint points at `manage.py createcachetable` and notes it is wired into `docker/entrypoint.sh`.
- Because it is database-tagged, Django passes the permitted `databases` aliases; the check no-ops when the default alias is not among them (e.g. a non-DB command, or a check run without DB access) rather than guessing.
- It runs at `migrate` and on explicit `manage.py check --database <alias>`, so a fresh standup that skipped cache provisioning fails loudly before serving instead of 500'ing a user later.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-health-bootcheck-1 | Missing Table Errors | Implemented | DatabaseCache + a non-existent table yields exactly one `tap_boot.E001` with a `createcachetable` hint. | test: table-missing |
| req-tap-health-bootcheck-2 | Present Table Clean | Implemented | DatabaseCache pointed at an existing table produces no error. | test: table-exists |
| req-tap-health-bootcheck-3 | Non-DatabaseCache Skips | Implemented | A non-DatabaseCache backend is irrelevant — no error, no introspection. | test: non-db-backend |
| req-tap-health-bootcheck-4 | No DB Access Without Permission | Implemented | With no permitted DB alias the check skips rather than introspecting. | test: db-unavailable; respects no-DB-in-ready |

### v0 Non-Goals
----
RID: `req-tap-health-nongoals`
Status: `Proposed`

This specification does not define:

- per-component latency or metrics (timing histograms, Prometheus exposition)
- an authenticated, detailed-diagnostics variant of the endpoint
- worker / scheduler liveness probing beyond the light queue-table reachability check
- plugin-contributed health probes (a plugin registering its own `/healthz` checks)
- a split between distinct liveness and readiness endpoints
- a durable health history / boot report

Those may become later layers, but they are intentionally outside this v0 surface.

#### Future

- **Plugin-contributed probes.** A registry by which a plugin contributes a named probe to `/healthz` (the baked-in core analogue of NetBox's pluggable health checks) — graduates when a plugin has a backend whose health is not visible to the core db/cache/queue probes.
- **Convergence with the boot report and provisioning sequence.** `/healthz`, the deferred boot report (`req-boot-report`), and the running-plugin registry/report are all facets of "observable assembled-instance truth" and should share a shape rather than proliferate; the canonical-provisioning-sequence work (carried into plugin-config / the pre-Django install wrapper) is the natural home to unify them.
- **Liveness vs readiness split** and **metrics/latency** if an orchestrator or monitoring stack demands the finer signal.

## Status Vocabulary

| Status States |  |
| --- | --- |
| Proposed | Requirement has been designed but not yet accepted for implementation. |
| Approved for Development | Requirement is accepted and ready to be implemented. |
| In Development | Actively being worked on. |
| Implemented | Has been written. |
| Verified | Has met the acceptance criteria via linked passing tests. |
| Refactoring | In the process of being re-worked. |
| Deprecating | In the process of being deprecated. |
| Deprecated | No longer part of the current architecture. |
