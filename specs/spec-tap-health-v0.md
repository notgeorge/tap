# TAP Health v0 Specification

## Philosophy

A TAP instance can stand up "successfully" — migrations applied, server listening, boot profile applied — and still be subtly broken in a way nothing exercises until a user trips over it. That is exactly what happened on 2026-06-26: a fresh instance booted green but 500'd on the first login because the `DatabaseCache` table (`tap_cache`) is provisioned outside migrations and nothing wired it in (`docs/aar/2026-06-26-tap-cache-latent-provisioning.md`). The class is **latent provisioning faults**, and every guard in place at the time was blind to it by construction: the test suite swaps `DatabaseCache` for `LocMemCache`, and `spawn-session.sh`'s post-boot check treated any HTTP response — including a 500 — as "up."

This spec defines the **health system** that closes that class: a deliberately small, dependency-free pair that exercises the *real* assembled instance.

- A **fail-at-boot system check** that refuses to come up when a known provisioning precondition is missing — the precondition becomes a loud startup error, not a latent runtime fault.
- An **internal health service** that probes the real backends (database, cache round-trip, queue, secrets) and returns a rich, machine-readable report the instance uses to **introspect itself** — first as it comes up (so faults are caught and handled by AI + human review at standup) and, later, as the surface AI agents and authorized users/plugins query to understand system status. The CLI (`manage.py health`), a future authorized API, and the HTTP `/healthz` endpoint are **projections** of this service.

> **v0 framing correction.** The first draft of this spec made the unauthenticated `/healthz` endpoint the foundation ("one surface, many uses"). That is inverted here (`req-tap-health-service`, `req-tap-health-exposure`): the **internal service is the foundation**, and an unauthenticated network endpoint is a *narrow, optional, coarse* projection — because the primary need is the system introspecting *itself*, not an external network probe finding it. Standing up an always-available unauthenticated endpoint on the web service, by default, is more exposure than the current need warrants.

The guiding principle: **a comment asserting an operational guarantee is a latent lie until a step or test fails when it is false.** The health system turns "provisioning is supposed to have happened" into something that actually fails loudly when it has not. It is intentionally hand-rolled (no `django-health-check` dependency) and lives in its own `tap_health` app — TAP owns the surface, matching the no-external-dependency posture that also keeps cache and sessions DB-backed rather than on Redis.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Real Backends | Health is judged by exercising the actual db / cache / queue, not by "the process is listening." |
| 2. | Fail Loud, Fail Early | A missing provisioning precondition is a startup error, not a latent runtime 500. |
| 3. | Internal Service First | The foundation is an in-process health service the instance uses to introspect itself; the CLI, an authorized API, and the HTTP endpoint are *projections* of it, not the foundation (`req-tap-health-service`). |
| 4. | Dependency-Free | The system is hand-rolled in TAP core (its own `tap_health` app); it adds no third-party health dependency. |
| 5. | Tiered Exposure, Coarse Outside | Each surface projects only what its caller is trusted with; the unauthenticated projection emits a coarse scorecard and nothing else, and is itself an optional, deliberate exposure — not a default (`req-tap-health-exposure`). |
| 6. | Rich Inside | Probes collect status *plus* reasoning and structured context for internal comprehension (operator + AI agent); the projection boundary decides what escapes. |

## Prior Art

- **Django system check framework** (`django.core.checks`) — static, registerable checks that run before/at `migrate` and on explicit `check`. Database-tagged checks (`Tags.database`) only run when a DB alias is in play, so a DB-touching check does not run on every management command and does not violate TAP's "no DB access in `AppConfig.ready()`" rule. This is the mechanism behind the fail-at-boot half.
- **NetBox** — ships no health endpoint in core (long-standing requests: netbox-community/netbox #3291, #8831); the community `netbox-healthcheck-plugin` (built on `django-health-check`) probes db + a real cache set/get + the Redis queue, exposed as JSON for monitoring. TAP adopts the *probe shape* (real cache round-trip is the key idea) but bakes a minimal version into core rather than taking a dependency or a plugin.
- **Kubernetes liveness/readiness probes** — the `/healthz` spelling and the 200/503 contract follow the conventional readiness-probe shape so container orchestration can consume it directly.

### Pluggable health systems (informing `req-tap-health-probe-registry`)

A survey of systems that actually ship a *registry* of named, component-contributed checks (not just a probe contract), with the design lesson each carries:

- **Kubernetes — two distinct things.** The *kubelet probe model* (liveness/readiness/startup; httpGet/tcp/exec/grpc) is a config-declared probe against an app endpoint, status-code only — **not** a registry. The *kube-apiserver's own* framework **is** a named-check registry: `/livez`, `/readyz`, `/healthz` over named checks (`etcd`, `log`, `poststarthook/...`), with subset selection by **separate endpoint per role**, **`?exclude=<check>`**, **`?verbose`** (lists `[+]name ok`), and per-check sub-path `/livez/<name>`. Lesson: caller-vs-internal split, and three composable selection idioms. (https://kubernetes.io/docs/reference/using-api/health-checks/)
- **Spring Boot Actuator — the canonical grouping model.** `HealthIndicator` beans → `HealthContributorRegistry`; **health groups** are named include/exclude sets (`management.endpoint.health.group.<g>.include=db,diskSpace`) each exposed at **`/actuator/health/<g>`**, with built-in `liveness`/`readiness` groups. Lesson: a group is an **include/exclude set over check names**, defined separately from the checks — *not* a field on each check. (https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- **ASP.NET Core — tags + predicate.** `IHealthCheck` registered via `AddCheck(name, …, tags: ["ready"])`; subset selection is a `Predicate` over tags mapped to one endpoint per role (`MapHealthChecks("/healthz/ready", Predicate = c => c.Tags.Contains("ready"))`). Lesson: a check carries **multiple tags**; selection is a predicate, one endpoint per subset. (https://learn.microsoft.com/en-us/aspnet/core/host-and-deploy/health-checks)
- **django-health-check — the closest ecosystem precedent.** Subclass `BaseHealthCheckBackend` with `check_status()` and a **`critical_service = True/False`** flag, registered from `AppConfig.ready()` via `plugin_dir.register(...)`. Lesson: our `register_health_probe(... critical=)` from `ready()` directly mirrors this established Django pattern (and our `critical` flag ≙ its `critical_service`); we bake a minimal version into core rather than take the dependency. (https://github.com/revsys/django-health-check)
- **gRPC Health Checking Protocol** (`grpc.health.v1.Health`) — per-**service** status via `Check(service)` → `SERVING|NOT_SERVING|SERVICE_UNKNOWN`; the service name is the namespace; `Check("")` = overall. Lesson: name-as-namespace, one status per call. (https://github.com/grpc/grpc/blob/master/doc/health-checking.md)
- **Go libraries** — `heptiolabs/healthcheck` (two fixed buckets via `AddLivenessCheck`/`AddReadinessCheck`, `/live`+`/ready`, `?full=1` JSON) and `AppsFlyer/go-sundheit` (a true registry that runs checks **async on a schedule and caches** results, so the endpoint returns cached state — one way to bound request-path cost, relevant to the deferred per-probe time-budget risk). (https://github.com/heptiolabs/healthcheck , https://github.com/AppsFlyer/go-sundheit)

**Design lessons taken:** (1) the universal primitive is a *named check → {status, optional detail}* aggregated worst-wins — which TAP already has; (2) **grouping/ownership and subset-selection are separate concerns** — Spring/ASP.NET express liveness-vs-readiness as include/exclude sets or multi-tags over check *names*, independent of a check's single owning namespace; (3) the dominant subset-selection convention is **a role → its own endpoint path** (`/livez`, `/readyz`, `/actuator/health/<g>`), optionally augmented by a k8s-style `?verbose`/`?exclude=` query layer.

## Relationship To Other Specs

- **`docs/aar/2026-06-26-tap-cache-latent-provisioning.md`** — the incident this system answers; the source of the "pair" framing (fail-at-boot check + verify/monitor endpoint).
- **`specs/spec-dev-validation.md`** — the Validation Map carries the "assembled-instance health" surface and its honest guard status; the internal service, the boot check, and the spawn gate are the guards that row tracks. The spawn gate **migrates** from an unauthenticated `/healthz` curl to a `dc exec … manage.py health` exec (`req-tap-health-exposure-2`, agreed); this removes the gate's dependency on a network endpoint and is the prerequisite that lets the unauthenticated `/healthz` be deleted (`req-tap-health-exposure-4`). The spawn-gate change touches `spec-dev-multisession.md` (Step 6.5).
- **`specs/spec-tap-boot-v0.md`** — boot converges *instance state*; this system guards the *schema/provisioning preconditions* beneath it. The cache-table system check is the boot-time counterpart to the runtime health service; its home **moves from `tap_boot` to `tap_health`** (`req-tap-health-service-2`) while staying a `Tags.database` check that fires at `migrate` (its id namespace moves accordingly, `tap_boot.E001` → `tap_health.E001`). The standing convergence target (one canonical provisioning sequence) is recorded in the AAR and carried toward the plugin-config / pre-Django-install work.
- **CLAUDE.md logging conventions** — probe diagnostics use the bare `[<hex>]` site-token convention and `%s` placeholders.
- **`docs/misc/agent-affordance-laws.md`** — the programmatic-actor design lens (not a spec) behind the structured-result, projection-boundary, and truth-preservation requirements here. Health is its first concrete pressure test: stable `code`s over prose (Law 4), tested projection boundaries (Law 5), `unknown` never silently dropped (Law 1), declared capabilities/effect-class for the deferred plugin tier (Laws 2/7). This spec deliberately stops at "don't foreclose those affordances" — it builds none of the AI-specific fields, per the doc's own guidance.

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-tap-health-service | [Internal Health Service](#internal-health-service) | Proposed | `tap_health` app; in-process pure-producer `run_health() → HealthReport` is the foundation; structured results (status/critical/group/code + projected detail/context); CLI/API are projections |
| req-tap-health-exposure | [Tiered Exposure And Projections](#tiered-exposure-and-projections) | Proposed | One rich report, projected per caller trust; CLI is network-free; unauth scorecard is a demoted, optional projection; projection boundary is a security boundary |
| req-tap-health-endpoint | [Health Endpoint](#health-endpoint) | Deprecating | unauthenticated `/healthz` **parked / being removed**; replaced by the internal service + `manage.py health` |
| req-tap-health-probes | [Real-Backend Probes](#real-backend-probes) | Implemented | Independent db / cache-round-trip / secrets / queue probes; report never raise |
| req-tap-health-probe-registry | [Pluggable Health-Probe Registry](#pluggable-health-probe-registry) | Proposed | First-party apps register named probes from `ready()`, grouped; verdict derived from `critical=` flags; inverts the core→app dependency |
| req-tap-health-probe-actor | [Probe Execution Identity](#probe-execution-identity) | Proposed | Anonymous caller never becomes an actor; service-boundary probe work runs as a named `tap_health.health_probe` program actor, materialized lazily |
| req-tap-health-unauth | [Unauthenticated, Coarse-Status Only](#unauthenticated-coarse-status-only) | Deprecating | parked with the endpoint; no unauthenticated surface remains |
| req-tap-health-bootcheck | [Boot-Time Provisioning Check](#boot-time-provisioning-check) | Implemented | DB-tagged system check; missing `tap_cache` → loud `tap_boot.E001`; **home moves to `tap_health`** |
| req-tap-health-nongoals | [v0 Non-Goals](#v0-non-goals) | Proposed | Metrics, auth'd diagnostics, worker-liveness, plugin probes deferred |

### Internal Health Service
----
RID: `req-tap-health-service`
Status: `Proposed`

Health is, first, an **in-process service the instance uses to introspect itself** — not an HTTP endpoint. The endpoint and the CLI are *projections* of this service (`req-tap-health-exposure`), not the other way round. This inverts the original framing that made the unauthenticated `/healthz` the foundation. The primary consumers are internal: the instance checking itself as it comes up (so faults are handled by AI + human review at standup), and — later — AI agents and authorized users/plugins introspecting system status.

#### The `tap_health` app

Health gets its own Django app, `tap_health`, which buys:

- a real `AppConfig.ready()` to register the core probes (`db`, `cache`, `queue`) — resolving the earlier open question (the `tap` package is not an app and has no `ready()`; `tap_health` is a cleaner home than borrowing `tap_boot`'s).
- a single owner for the health domain: the probe registry (`req-tap-health-probe-registry`), the `HealthReport` model, the `run_health` service entrypoint, the `manage.py health` command, the endpoint view, and the health program actor (`tap_health.health_probe`, `req-tap-health-probe-actor`). Health logic stops being scattered across `tap/` and `tap_boot/`.
- the boot-time provisioning check (`req-tap-health-bootcheck`), today in `tap_boot/checks.py`, **consolidates into `tap_health`** (resolved): it is a health/provisioning check by nature, so the health app owns it. It stays a Django system check registered from `tap_health`'s `ready()` (it remains `Tags.database`-tagged and fires at `migrate` / `check --database` exactly as before); only its home moves.

#### Entry point and report shape

- `run_health(*, selection=None) -> HealthReport` — the service entrypoint, a **pure producer**. It runs the registered probes and returns a structured `HealthReport`. It takes **no caller and no actor**: the v0 (below-boundary) probes resolve no actor, so the liveness path stays runnable when auth/DB/grid is broken (`req-tap-health-probe-actor`). Caller identity and projection are *not* parameters here — they are a **surface** concern (`req-tap-health-exposure`); probe *execution* identity, when a boundary-crossing probe eventually needs it, is internal to that probe. `selection` (which groups/probes to run) is a future subset-selection hook.
- A probe returns a structured result — `{status, critical, group, code?, detail?, reasoning?, context?}` — built so a programmatic actor never has to parse prose to know what happened (Law 4, `docs/misc/agent-affordance-laws.md`):
  - `status` ∈ `{healthy, degraded, unhealthy, unknown}` — the machine status value.
  - `critical` — explicit boolean; criticality is a field, never hidden in prose.
  - `group` — the owning namespace (`req-tap-health-probe-registry`).
  - `code` — a **stable, machine-readable code** for a non-healthy result (e.g. `secrets.required_for_boot_failed`, `cache.roundtrip_mismatch`). Probe-owned, snake_case, probe-namespaced; no central code registry in v0, just the convention. This is what a future Paladin branches on — not the `detail` string.
  - `detail` — a short human string (human support only, never the machine contract).
  - `reasoning` — optional prose: *why* the probe reached its status (human/agent comprehension).
  - `context` — optional **structured dict** of diagnostics collected while executing (timings, observed values, table names, counts, the secrets probe's failing-file list) that a trusted caller can inspect.
- The rich fields (`reasoning`, `context`) are **collected modestly** in v0; what is *exposed* is decided by the projection, not the probe. Collecting `context` is safe **only because** the coarse projection strips it — and that stripping is proven by a load-bearing projection test (`req-tap-health-exposure-3`), which must exist before rich collection is enabled. No remediation / AI-specific fields in v0 (named, deferred — `agent-affordance-laws.md` "Future Spec Hooks").

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-health-service-1 | Service Is The Foundation | Proposed | `run_health()` is the primary health surface; HTTP / CLI / API are projections of it. | inverts the endpoint-first framing |
| req-tap-health-service-2 | tap_health App | Proposed | A `tap_health` app owns the registry, report model, service, command, the boot check, and the health actor, and registers the core probes from its `ready()`. | resolves the registration-home question |
| req-tap-health-service-3 | Structured Probe Result | Proposed | A probe result carries explicit `status`, `critical`, `group`, a stable machine `code` for non-healthy results, plus optional prose `detail`/`reasoning` and a structured `context` dict. | Law 4: structure before prose; criticality is a field, not prose |
| req-tap-health-service-4 | Collect Behind A Tested Boundary | Proposed | Rich `reasoning`/`context` are collected only once a load-bearing projection test proves the coarse projection strips them; exposure is the projection's call, never the probe's. | gated on `req-tap-health-exposure-3` |
| req-tap-health-service-5 | Pure Producer, Actor-Free Liveness | Proposed | `run_health()` takes no caller and no actor; the liveness path resolves no actor. Projection/authorization is a surface concern; probe execution identity (if any) is internal to a boundary-crossing probe. | resolves the caller/identity conflation |

### Tiered Exposure And Projections
----
RID: `req-tap-health-exposure`
Status: `Proposed`

The internal service produces one rich `HealthReport`; how much of it a caller sees depends on the caller, via explicit **projections**. This is Spring Boot Actuator's `show-details: never | when-authorized | always` pattern made the center of the design — and the reason an unauthenticated network endpoint is a *narrow, deliberate* projection, not the default surface.

#### Surfaces (most-trusted to least)

0. **Internal service** — in-process `run_health()`. Returns the full `HealthReport`; `report.full()` and `report.scorecard()` are its two projection methods. The foundation; every surface below projects from it.
1. **CLI / exec** — `manage.py health` runs `run_health()` in-process (**actor-free** — the v0 probes resolve no actor, so the gate works even when auth/DB is broken), prints `report.full()` (human, or `--json` for the machine view), and exits 0 / non-zero. The CLI is a *trusted* surface, so it gets `full()`, not the scorecard. It sets **`requires_system_checks = []`** so a failing system check (e.g. the untagged `tap_cares.E001` from a required-for-boot malformed secret) cannot abort the command before it reports — health must *report* broken state, not be preempted by it; the probes themselves surface that state. This is the surface the spawn post-boot gate and any container **exec** readiness probe use — **no network exposure at all**. Migrating the spawn gate from the unauthenticated HTTP curl to `manage.py health --json` is what lets the HTTP endpoint be deleted (`req-tap-health-exposure-4`, coordinated removal pass below).
2. **Authorized rich API** *(future)* — an authenticated, authZ-gated affordance returning the full report (reasoning + context) for AI agents, operators, and plugins. The eventual "agents introspect system status" surface; deferred until there is a consumer.
3. **Unauthenticated coarse scorecard** — **parked (resolved).** The existing unauthenticated `/healthz` (`req-tap-health-endpoint`, `req-tap-health-unauth`) is **removed** once the spawn gate migrates to `manage.py health` (tier 1) — it was an over-eager build with no consumer we actually need, and standing an unauthenticated surface on the web service by default is more exposure than the current need warrants. The coarse-scorecard *shape* (per-probe `status` + overall verdict, no `detail`/`reasoning`/`context`) is retained as a `HealthReport.scorecard()` projection method so a future external surface can be stood up deliberately — but **no endpoint exposes it** in this version. Re-introducing any externally-reachable health surface is a future, explicit decision with its own threat model, not a default.

#### The projection boundary is load-bearing security

Because probes now collect rich `context` (timings, file names, observed values), the coarse projection is a **security boundary**, not a formatting choice: a probe's `reasoning` / `context` / free-form `detail` must never cross into the unauthenticated scorecard, which emits only the four-state `status` per named probe plus the overall verdict. This **supersedes** `req-tap-health-unauth-2`'s "short error detail" allowance — with context-collection in play, even `detail` strings are withheld from the unauthenticated tier unless proven leak-free.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-health-exposure-1 | Projections, Not Surfaces | Proposed | One rich report; each surface is an explicit projection keyed on caller trust. | Spring `show-details` pattern |
| req-tap-health-exposure-2 | CLI Is Network-Free | Proposed | `manage.py health` runs the service in-process and exits 0 / non-zero; the spawn / exec gate uses it, needing no network endpoint. | makes the HTTP endpoint optional |
| req-tap-health-exposure-3 | Coarse Scorecard, Leak-Tested | Proposed | `report.scorecard()` emits only per-probe `status` (+ overall verdict) — never `detail` / `reasoning` / `context` / `code`. A **load-bearing projection test** asserts this and is the gate for `req-tap-health-service-4`. | projection = security boundary; supersedes `req-tap-health-unauth-2` |
| req-tap-health-exposure-4 | Unauth Endpoint Parked | Proposed | The unauthenticated `/healthz` is removed once the spawn gate migrates to `manage.py health`; the coarse shape survives only as a `HealthReport.scorecard()` method with no endpoint. Any future external surface is a deliberate decision with its own threat model. | resolved: park entirely |
| req-tap-health-exposure-5 | Coordinated Removal Pass | Proposed | Parking `/healthz` is one atomic, ordered change across every surface that references it; the repo never claims it is both removed and the current gate. | the file list + order below |

#### Coordinated removal pass (`req-tap-health-exposure-5`)

`/healthz` removal is not a one-file edit — it ripples, and a half-done pass leaves the repo internally dishonest (claiming the endpoint is both removed and the live gate). It runs as one ordered change:

1. **Build** the internal service + `manage.py health --json` (the replacement must exist first).
2. **Migrate the gate** — `scripts/spawn-session.sh` Step 6.5: `curl …/healthz` → `scripts/dc exec -T web uv run python manage.py health --json`.
3. **Reconcile the references that *describe* `/healthz`:**
   - `specs/spec-dev-validation.md` — the Validation Map row points at the CLI health gate, not a live `/healthz`.
   - `tap_cares/specs/spec-tap-cares-secrets.md` `req-tap-cares-secrets-resilient-load-5` — the secrets surface is the **internal service / CLI projection**, not `/healthz` (this reference exists *because* the resilient-secrets work wired the secrets probe into the endpoint; it moves with the endpoint).
4. **Delete the surface** — `tap/health.py` view + the `/healthz` route in `tap/urls.py` + the `TAP_LOGIN_EXEMPT_PREFIXES` entry in `tap/settings.py`.
5. **Update tests** — retire `tap/tests/test_health.py`'s endpoint cases; the secrets degraded-vs-blocking assertions move onto `run_health()` / the CLI; keep the projection leak-test.

After the pass there is **no externally-reachable health surface** — internal service + `manage.py health` only (`req-tap-health-service`, `req-tap-health-exposure` tiers 0–1).

### Health Endpoint
----
RID: `req-tap-health-endpoint`
Status: `Deprecating`

> **Parked (`req-tap-health-exposure-4`).** The unauthenticated `/healthz` endpoint is being **removed**, not kept — it was an over-eager end-of-week build with no consumer we actually need, and the internal service + `manage.py health` cover the real cases. It stays live only until the spawn gate migrates off it (`req-tap-health-exposure-2`), then the route and view are deleted. The coarse-scorecard *shape* survives as `HealthReport.scorecard()` for a future, deliberately-stood-up external surface. The as-built behavior below is retained for reference until removal.

TAP exposes a health endpoint at the stable path `/healthz` that reports the instance's real backend health as JSON with an HTTP status code consumable by an orchestrator or a script.

#### Implementation

- The view is `tap/health.py:health_view`, mounted in `tap/urls.py` at `/healthz`, **before** the `tap_web` catch-all so the path is never shadowed.
- The response body is `{"status": "healthy"|"degraded"|"unhealthy", "checks": {<name>: {"status": ..., ["detail": ...]}}}`.
- HTTP status is **200** when no *critical* probe is `unhealthy` (a `degraded` non-blocking result is still 200), **503** otherwise (`req-tap-health-probes` defines the critical set and the four-state status model). `"degraded"` was added with the `secrets` probe (`req-tap-cares-secrets-resilient-load-5`): a non-blocking secret-load failure reports `degraded` at 200, a `required_for_boot` failure reports `unhealthy` at 503.
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
- **secrets** (`_check_secrets`) — reports the startup secret-load outcome (`secret_load_report`, owned by `tap_cares`). The loader is resilient (a bad secret file is recorded, not raised), so this probe is how a degraded/blocked secret surfaces on a *running* instance, where Django system checks do not run. It is **conditionally critical**: a `required_for_boot` load failure reports `unhealthy` (→503); any other load failure reports `degraded` (→200). Defined and owned by `tap_cares` (`req-tap-cares-secrets-resilient-load-5`); `tap/health.py` currently imports it directly — the dependency inversion is the subject of `req-tap-health-probe-registry`.
- **queue** (`_check_queue`) — a light, best-effort reachability check (the DB-backed Steady Queue's `steady_queue_job` table is present). It is **non-critical**: any indeterminate result reports `"unknown"` and never flips the overall status. It deliberately does not probe worker liveness.
- **Critical set** = `(db, cache)` always-critical, plus `secrets` when it reports `unhealthy`. The overall verdict follows the four-state model: `unhealthy`/503 if any critical probe is `unhealthy`; else `degraded`/200 if any probe is `degraded`; else `healthy`/200. `queue` (`unknown`) never flips the verdict. `req-tap-health-probe-registry` generalizes this to a `critical=` flag per registered probe.
- Every probe wraps its work in a `try/except` that logs at the appropriate level (`warning` for critical, `info` for the non-critical queue) and returns a status dict — the view can never 500 on a probe error.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-health-probes-1 | DB Probe | Implemented | The db probe issues a trivial query over the default connection. | |
| req-tap-health-probes-2 | Cache Round-Trip | Implemented | The cache probe is a real set→get round-trip whose value must match. | the demo-fault catcher; tests: all-healthy, cache-broken |
| req-tap-health-probes-3 | Queue Best-Effort | Implemented | The queue probe is non-critical and reports `unknown` rather than failing on an indeterminate result. | |
| req-tap-health-probes-4 | Critical Set | Implemented | db and cache are always critical, and `secrets` is critical when `unhealthy`; `queue` never flips the overall status. | four-state model |
| req-tap-health-probes-5 | Probes Report, Never Raise | Implemented | A probe error is caught and reported, never propagated as a 500. | test: cache-broken |
| req-tap-health-probes-6 | Secrets Probe | Implemented | The `secrets` probe reports the resilient secret-load outcome: `degraded` (200) for a non-blocking failure, `unhealthy` (503) for a `required_for_boot` failure. | owned by `tap_cares`; tests in `tap/tests/test_health.py`; see `req-tap-cares-secrets-resilient-load-5` |

### Pluggable Health-Probe Registry
----
RID: `req-tap-health-probe-registry`
Status: `Proposed`

The probe set in `health_view` is currently a hardcoded dict literal and the critical set a module-level tuple. Adding the `secrets` probe (`req-tap-cares-secrets-resilient-load-5`) required editing `tap/health.py` directly and forced TAP core to import *up* into `tap_cares` — a backwards dependency (core depending on an app). This requirement replaces the literal with a small in-process registry so any first-party app contributes a named probe from its own `AppConfig.ready()` — the same import-to-register pattern the Django system-check half (`req-tap-health-bootcheck`) already uses — and inverts that dependency. It is the build-once edge that graduates the long-noted "plugin-contributed probes" future item from a flat non-goal into a real substrate, while still deferring untrusted plugin probes (see Non-Goals).

#### Implementation

- The registry **reuses the existing `tap_grid.registry.Registry[T]`** (the flat, globally-unique variant — not `ScopedRegistry`; health probe names are a small global set with no need for scope-namespacing). It follows the established `search_runner_registry` / `register_search_runner` precedent exactly: a module-level `health_probe_registry = Registry("health_probe", ...)` plus a thin `register_health_probe(...)` wrapper. Reuse buys the duplicate-guard (`ImproperlyConfigured` on a repeated name, at startup), `_reset_for_testing()` for test isolation, and self-registration into `meta_registry` so the probe set is discoverable alongside every other registry — at the cost of a first-party `tap_grid` import from the health surface. That import does **not** violate the "Dependency-Free" goal, which forbids a *third-party* health dependency (`django-health-check`), not a foundational first-party one; there is no import cycle (`tap_grid.registry` pulls only Django + stdlib).
- The wrapper:
  `register_health_probe(name: str, probe: Callable[[], dict], *, group: str = "core", critical: bool = False, requires: Sequence[str] = ()) -> None`
  - `requires` — the capabilities this probe needs to execute (the cheap-now/enforce-later least-privilege slot; see `req-tap-health-probe-actor` capability scoping). v0 probes are below the service boundary and pass `requires=()`; the field is captured now so probes carry `(check, required_capabilities)` from day one.
  - `name` — probe key, **globally unique** across groups (a duplicate raises `ImproperlyConfigured` at startup via `Registry.register`). Global uniqueness is deliberate: the flat `{"checks": {name: ...}}` output is keyed by `name`, so two probes cannot share one.
  - `probe` — a zero-arg callable returning a `{"status": ..., ["detail": ...]}` dict: exactly the current per-probe contract, unchanged.
  - `group` — the namespace this probe reports under (see *Grouping and report order*). Defaults to `"core"`. Carried as a field on the stored value, **not** as a registry scope — see the note below.
  - `critical` — whether an `unhealthy` result from this probe flips the endpoint to 503.
  - The stored value `T` is the canonical `HealthProbe` record — `HealthProbe(name, probe, group="core", critical=False, requires=())` — and the wrapper signature, this record, and the acceptance criteria all agree on exactly these fields. `requires` is captured here even though v0 does not enforce it (`req-tap-health-probe-actor`).
  - **Why `group` is a value field, not a `ScopedRegistry` scope.** Carrying `group` as a value field on a flat `Registry` (rather than reusing `ScopedRegistry` with `scope=group`) keeps `name` globally unique — which the flat output *requires*. `ScopedRegistry` deliberately *permits* the same short key under two scopes, which the `{name: ...}` output cannot represent. So the grouping requirement does **not** flip the registry choice: flat `Registry` + a `group` field is the better fit precisely because we want global names *and* grouping. (`Registry` has no `validate_key` hook; name/group token validation, if ever wanted, lives in this wrapper — v0 needs none.)
- Probes self-register from their owning app's `ready()` by importing the registration module. Registration only appends a callable — it accesses no DB and does not breach the no-DB-in-`ready()` rule; the probe body runs later, at request time (identical to how system checks register).
- **Ownership inverts:**
  - The registry lives in the **`tap_health`** app (`tap_health/registry.py`, wrapping `tap_grid.registry.Registry`). The core `db`, `cache` (critical) and `queue` (non-critical) probes register from `tap_health.apps.TapHealthConfig.ready()`. This resolves the earlier open question — the core `tap` package is not a Django app and has no `ready()`; rather than borrow `tap_boot`'s, health gets its own app, which the internal-service framing (`req-tap-health-service`) warrants anyway.
  - `tap_cares` registers `secrets` (critical) from its own `ready()`; `tap/health.py` no longer imports `tap_cares`. This is the concrete fix for the layering smell named in `req-tap-cares-secrets-resilient-load-5`.
- `health_view` iterates the probes in deterministic **`(group, name)` order** (clustering each group's probes together; alphabetical within a group) to build the `checks` dict, and derives the critical set from the per-probe `critical=` flags rather than a separate literal tuple. The JSON shape and 200/503 contract (`req-tap-health-endpoint`) are unchanged — this is a pure refactor with no behavior change. (Probe *report order* shifts from the current literal order to grouped-alphabetical; no consumer depends on order, and tests assert presence, not order.)

#### Four-state status model

Each probe returns a status in `{healthy, degraded, unhealthy, unknown}`; the endpoint derives the overall verdict:

- **unhealthy / 503** — any *critical* probe returns `unhealthy`.
- **degraded / 200** — no critical `unhealthy`, but at least one probe returns `degraded` **or a non-critical probe returns `unhealthy`** (non-blocking, but never over-greened to healthy — Law 1).
- **healthy / 200** — otherwise.

A non-critical probe never flips the overall verdict; `unknown` never *flips* it either. But — per Law 1, **Preserve Truth** (`docs/misc/agent-affordance-laws.md`) — `unknown` is **never silently dropped**: every probe's status, `unknown` included, is always present in the report's per-check output. The overall verdict may stay `healthy` while a non-critical check is `unknown`, but the `unknown` is always *visible*, never collapsed into "healthy." A by-design `unknown` (the `queue` probe) is explicitly acceptable *and explicitly shown*; the rule the model forbids is over-greening — reporting overall `healthy` in a way that hides a check an operator should notice.

This also subsumes the `secrets` probe's *conditional* criticality without a conditional flag: it registers `critical=True` and itself chooses `unhealthy` for a `required_for_boot` failure (→503) or `degraded` for a non-blocking one (→200). The model is a strict generalization of the current `(db, cache)` literal — re-expressing today's behavior, not changing it.

#### Grouping and report order

Every probe registers under a `group` (default `"core"`). Groups serve two purposes, one cosmetic and one structural:

1. **Clustering (now).** `health_view` reports probes in `(group, name)` order, so a group's probes appear adjacently and deterministically — `core` (cache, db, queue) cluster; `tap_cares` (secrets) clusters. This is the "grouped together" floor.
2. **Subset selection (the real payoff, future) — a *separate* mechanism, not the `group` field.** The prior art (see Prior Art) is consistent: liveness/readiness selection is expressed as named **include/exclude sets over probe names** (Spring Boot health *groups*) or **multi-valued tags per check** (ASP.NET), *distinct* from a check's single owning namespace — because one probe (e.g. `db`) commonly belongs to *both* the readiness and liveness sets. So `group` here is strictly the **clustering / ownership** dimension (one per probe: which subsystem owns it, how it sorts). The future liveness/readiness split is a separate selection layer — a config-defined include/exclude over probe *names*, surfaced as role endpoints (`/livez`, `/readyz`, the dominant convention) and/or a k8s-style `?exclude=`/`?verbose` query — layered on without re-plumbing registration. Keeping the two concerns separate now (a single `group` field, **no** per-probe selection-set membership) deliberately avoids baking a single-membership assumption that the readiness/liveness split would later have to unwind.

**Ordering flag — recommended *deferred*.** Beyond `(group, name)` clustering, should a probe declare an explicit `order: int`? Recommendation: not in v0.

- Report order is cosmetic — the `checks` block is a map; no consumer should depend on order (clients look up by `name`). Determinism (sorted `group, name`) is the real requirement and is met.
- The one functional reason to order — short-circuiting an expensive probe behind a cheap critical one — does not apply: all v0 probes are trivially fast and the endpoint always runs the full set to report the complete picture.
- It stays cheaply additive: if a real need emerges (a probe gains cost, or a within-group priority matters), add `order: int` to `HealthProbe` and sort by `(group, order, name)`. Deferring costs nothing; `group` + sorted `name` already delivers the stated "grouped together" goal.

#### Robustness and isolation

- The registry wraps every probe call in `try/except`: a probe that raises is reported as `{"status": "unhealthy", "detail": <message>}` and isolated — one probe can neither 500 the endpoint nor prevent the others from running (preserves and centralizes `req-tap-health-probes-5`).
- Every registered probe remains bound by `req-tap-health-unauth-2`: `detail` is coarse operational signal only — never secrets, settings, stack traces, or record data.

#### Security considerations

Every registered probe executes real work, and a probe contributed by *untrusted* code (a plugin) runs inside `run_health()` with no sandbox. v0 of the registry is therefore scoped to **first-party apps only**; plugin-contributed probes stay deferred (Non-Goals) until these controls exist — named here rather than left implicit, per the security-posture doctrine of naming risks left open (and Laws 2/5/7 of `docs/misc/agent-affordance-laws.md`):

- a per-probe **time budget** so a slow or hung probe cannot stall or DoS the run (Law 7). v0 relies on probes being trivially fast and enforces no hard timeout — the primary named risk a plugin-probe future must close.
- an **effect class** declared per probe — read-only / idempotent / external-world-touching / privileged (Law 2) — so the runner and any consumer know what a probe may do before calling it. v0 first-party probes are all read-only/internal, so no field is added yet; it is the natural companion to `requires` when plugin probes arrive.
- enforced (not assumed) confirmation that a contributed probe's `detail` / `context` cannot leak secret/material (Law 5), since untrusted code would author it.
- declared **required capabilities** (`requires`, `req-tap-health-probe-actor`) so a plugin probe is confined to a tightly-scoped program actor and cannot `acting_as` an arbitrary powerful one.
- a bounded probe count so a caller cannot amplify cost across many contributed probes.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-health-probe-registry-1 | Registration API | Proposed | `register_health_probe(name, probe, *, critical=False)` wraps a flat `tap_grid.registry.Registry`; a duplicate name raises `ImproperlyConfigured` at startup. | reuses existing registry; precedent `register_search_runner` |
| req-tap-health-probe-registry-2 | Self-Registration From ready() | Proposed | Apps register probes by importing the module in `AppConfig.ready()`; registration accesses no DB. | mirrors system-check registration |
| req-tap-health-probe-registry-3 | Dependency Inversion | Proposed | `tap_cares` registers the `secrets` probe; `tap/health.py` no longer imports `tap_cares`. | fixes the layering smell from `req-tap-cares-secrets-resilient-load-5` |
| req-tap-health-probe-registry-4 | Derived Critical Set | Proposed | The 200/503 verdict is derived from per-probe `critical=` flags, not a hardcoded tuple. | |
| req-tap-health-probe-registry-5 | Four-State Status Model | Proposed | Overall = `unhealthy` if any critical probe `unhealthy`; else `degraded` if any probe `degraded` or a non-critical probe `unhealthy`; else `healthy`. | subsumes secrets conditional criticality; a non-critical unhealthy is degraded, never hidden (Law 1) |
| req-tap-health-probe-registry-6 | Probe Isolation | Proposed | A probe that raises is caught and reported; it cannot 500 the endpoint or block other probes. | centralizes `req-tap-health-probes-5` |
| req-tap-health-probe-registry-7 | First-Party Only | Proposed | The v0 registry accepts first-party app probes only; plugin probes remain deferred with the named risks above. | security scope |
| req-tap-health-probe-registry-8 | Probe Grouping | Proposed | Each probe registers under one `group` (default `core`), carried as a value field for clustering/ownership; probes report in `(group, name)` order. Names stay globally unique. | `group` is ownership, **not** a selection set; liveness/readiness selection is a separate deferred layer; no `order` flag in v0 |

### Probe Execution Identity
----
RID: `req-tap-health-probe-actor`
Status: `Proposed`

The instance enforces a no-anonymous-actor rule: the service boundary rejects `user=None` and system-initiated work runs as a **named program actor** — `tap_bootloader`, `tap_cares.collector`, `tap_cares.scheduler` (`tap_grid/caller_context.py`, `req-tap-auth-policy`). Health probes execute real work, so they must answer "as whom?" without re-introducing an anonymous actor.

The resolution rests on a distinction that is easy to miss:

- **Caller-anonymous ≠ actor-anonymous.** `/healthz` is deliberately unauthenticated (`req-tap-health-unauth`) so an orchestrator or a pre-auth boot gate can probe it. The no-anonymous-actor rule governs *actors performing actions in the system*, not *who may hit a liveness endpoint*. The anonymous caller **never becomes an actor** — it triggers system-executed probe work and is attributed nothing. There is no conflict to resolve away; these are two different subjects.

Given that, probe execution identity is defined as:

- **v0 probes run below the service boundary** (`SELECT 1`, a cache round-trip, an in-memory `secret_load_report` read). Below the boundary, `CallerContext.user` is legitimately `None` (the same allowance the docstring grants model-level saves and migrations), so v0 probes require no actor at all. This is the "below the level of the grid (so far)" case.
- **Any probe that crosses the service boundary** — now or later — executes as a single named program actor **`tap_health.health_probe`** (the "health probe actor"), consistent with the existing program actors and **never** as `user=None` and **never** as the anonymous caller. One shared actor for all probe execution ("the health subsystem ran its checks"); *which* probe ran is already carried by the probe `name`, so per-contributor actors are unnecessary.

#### Robustness invariant (the liveness path resolves no actor at all)

A liveness probe must run **when the grid, DB, or auth is broken** — that is its entire job. The correction the as-built investigation forces: program actors are **not** in-code constants — they are `AUTH_USER_MODEL` rows (`user_kind="program"`, `tap_builtin_key`, capabilities via group membership), resolved by a **DB query** (`get_builtin_actor`, uncached), and `policy.can` adds an `EXISTS` query (stateless — no ledger — but **not** DB-free). So binding *any* actor costs the database. The invariant is therefore preserved not by making the actor "in-code," but by keeping the liveness path **actor-free**:

- The below-boundary liveness probes (`db`, `cache`, `queue`) resolve **no actor and run no capability check** — they need none (`req-tap-health-probe-actor-2`). Wrapping the `db` probe in `get_builtin_actor(...)` would couple it to the very database it checks; that is exactly the coupling to avoid.
- `tap_health.health_probe` (a DB-backed program actor like its peers) is resolved and used **only** for probes that *already* cross the service boundary — and for the deferred activity recording — i.e. only where the DB is already a dependency, so the actor resolution adds no new failure mode. v0 has no such probe, so v0 resolves no health actor anywhere.

#### Activity tracking (deferred)

Recording health runs as on-grid activity (a health-run event/edge per probe execution, for audit/trend) is a **future layer** this identity enables but does not yet build. When it lands, those writes go through the service layer under `tap_health.health_probe` — which is the point at which the actor is created. Creating it is a small auth-sync task, not free: add a `tap_health.health_probe` builtin key + a like-named capability group in `tap_auth/sync.py` (mirroring `_ensure_program_actor` for the existing actors) and re-run sync — or simply reuse an existing scoped program actor (e.g. `tap_cares.collector`) if its capability set fits. v0 does neither. Naming the principal now (at near-zero cost) is the cheap foundational edge; building the activity machinery waits for demand.

#### Capability scoping (declare now, enforce later)

A natural refinement: rather than one health actor accumulating the *union* of every probe's permissions, let each probe declare the capabilities it needs and execute under a principal scoped to **only** those — least privilege, and the right shape for the untrusted plugin-probe tier (`req-tap-health-probe-registry` security considerations). The cost/value split falls cleanly along the design's current edge:

- **Declare now (cheap, do it).** The registration API is being designed now, so `register_health_probe(..., requires=())` carries the capability list a probe needs (TAP's existing capability model — `requires_capability` / `policy.can`). v0 probes are below the service boundary (`SELECT 1`, cache round-trip, in-memory read) and declare `requires=()` — there is nothing to scope yet — but capturing the slot now sets the contract so probes are never retrofitted later. Defining a probe as `(check, required_capabilities)` is the asymmetric cheap-now/expensive-later edge.
- **Enforce later (premature, defer).** When a probe first crosses the service boundary, it executes under a context granting *only* its declared capabilities — a capability-restricted derivative of the `tap_health.health_probe` actor. That scoping machinery is built then, against a real consumer; no v0 probe exercises it.

**Why not execute a probe as a user / sub-user.** Running a probe as a human-derived identity is **rejected** — resolving a *user* needs the DB/auth, and (like resolving any actor) costs queries. Down-scoping stays **program-actor-based, capability-narrowed**: a boundary-crossing probe executes under a named *program* actor restricted to its declared capabilities. Per-subsystem attribution, if ever wanted, reuses an existing scoped program actor (e.g. a collector-health probe under `tap_cares.collector`) — never a human user. None of this runs on the liveness path (the robustness invariant above): only probes that already touch the service layer resolve an actor.

**Scaffolding — already on rails (as-built).** The binding primitive exists and is battle-tested, so program-actor scoping is a *usage* task, not new machinery:

- A program actor is resolved by `get_builtin_actor(KEY)` (`tap_auth/actors.py`), and **`acting_as(actor)`** (`tap_auth/actors.py`) is a nesting, `ContextVar`-backed scoped swap — the no-request analogue of `CallerContextMiddleware` — already used by the collector task (`tap_cares/tasks.py`), boot (`tap_boot/orchestrator.py`), and the scheduler. `run_collection` already swaps the executor mid-flight (trigger user → `tap_cares.collector`, `tap_cares/services.py`). So scoping a boundary-crossing probe is literally `with acting_as(get_builtin_actor(ACTOR)): <probe>`.
- **Cost / constraint:** `get_builtin_actor` is one (uncached) DB query and each guarded op adds a `policy.can` `EXISTS` query — so this is for DB-touching probes only; the liveness probes stay actor-free (above). If health probes ever run hot under an actor, add caching to `get_builtin_actor`.
- **On "sudo to another actor."** The generic scoped swap *is* `acting_as` — a process bound to actor A can `with acting_as(B):` and revert, today, **unguarded**. So running an app's health check under that app's program actor needs **no new mechanism for first-party probes**. What does *not* exist is a **named, authorized, audited** assume — a policy check that "A may assume B" plus an audit trail (the reserved `req-tap-auth-ai-placeholder` delegation seam). First-party probes don't need that guard; it becomes necessary only for the **untrusted plugin-probe tier**, so a plugin cannot `acting_as` an arbitrary powerful actor — tying this directly to the plugin-probe security controls (`req-tap-health-probe-registry`). v0 needs neither.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-health-probe-actor-1 | Caller Never An Actor | Proposed | Any external/unauthenticated caller of a (future) health surface is attributed no actor identity; it triggers system-executed probes. | caller-anonymous ≠ actor-anonymous |
| req-tap-health-probe-actor-2 | Below-Boundary Probes Need No Actor | Proposed | v0 probes run below the service boundary and require no `CallerContext`. | matches the `user=None`-below-boundary allowance |
| req-tap-health-probe-actor-3 | Named Program Actor At The Boundary | Proposed | A probe crossing the service boundary executes as `tap_health.health_probe`, never `None`, never the caller. | peer of `tap_bootloader` / `tap_cares.*` |
| req-tap-health-probe-actor-4 | Liveness Path Resolves No Actor | Proposed | Below-boundary probes (db/cache/queue) resolve no actor and run no capability check. The DB-backed health actor is resolved only for boundary-crossing probes and deferred activity recording — paths that already touch the DB. | program actors are DB rows; binding one costs a query, so liveness stays actor-free |
| req-tap-health-probe-actor-5 | Activity Tracking Deferred | Proposed | On-grid recording of health runs is a future layer under `tap_health.health_probe`; v0 records nothing. | names the edge, defers the build |
| req-tap-health-probe-actor-6 | Declared Capabilities, Scoped Execution | Proposed | A probe declares `requires=()` capabilities at registration (captured now); a boundary-crossing probe later executes under the health actor down-scoped to exactly those (enforcement deferred). A probe never executes as a human user. | least-privilege; robustness invariant preserved |

### Unauthenticated, Coarse-Status Only
----
RID: `req-tap-health-unauth`
Status: `Deprecating`

> **Parked with the endpoint (`req-tap-health-exposure-4`).** This requirement existed to justify an *unauthenticated* surface; with the endpoint removed there is no unauthenticated surface to govern. It is retained for reference until the route is deleted, after which there is no externally-reachable health endpoint at all (the internal service + `manage.py health` are the surfaces). Note the projection boundary that this requirement guarded is now owned by `req-tap-health-exposure-3` and applies to *any* future external surface.

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
- the **build-out** of the authorized, detailed-diagnostics API (the rich reasoning/context surface for agents/operators) — its *shape* is now named as exposure tier 2 (`req-tap-health-exposure`), but the actual authenticated endpoint/affordance is deferred until a consumer exists
- worker / scheduler liveness probing beyond the light queue-table reachability check
- **untrusted plugin-contributed** health probes (a *plugin* registering its own `/healthz` check). The first-party probe registry (`req-tap-health-probe-registry`) is the substrate, but it is scoped to first-party apps; opening it to plugin code waits on the time-budget / leakage / amplification controls named there.
- a split between distinct liveness and readiness endpoints
- a durable health history / boot report

Those may become later layers, but they are intentionally outside this v0 surface.

#### Future

- **Plugin-contributed probes.** The first-party registry (`req-tap-health-probe-registry`) is the baked-in core analogue of NetBox's pluggable health checks. Extending it to *plugin* code (the baked-in analogue's untrusted tier) graduates when a plugin has a backend whose health is not visible to the core probes **and** the registry's named security controls (per-probe time budget, `detail` leakage enforcement, bounded probe count) are in place.
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
