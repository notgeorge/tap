# AAR — The `tap_cache` Latent Provisioning Fault

| | |
| --- | --- |
| **Date** | 2026-06-26 |
| **Severity** | High (near-miss) — login crashed minutes before a partner demo; caught and patched in the room, no data loss. |
| **Status** | Immediate fix shipped; the durable **pair** (startup system check + real-backend health endpoint) + spawn-gate flip implemented in this bundle. Convergence-to-one-canonical-sequence carried forward into the plugin-config work. |
| **Author** | Claude `session/plugins` |
| **Class** | Latent provisioning fault — "standup succeeds, a never-exercised-at-boot path is broken." |

This is a process AAR: the running-system behavior is owned by the specs and by
the code that landed alongside this note. The subject here is *how a "successful"
standup shipped a broken instance*, why every guard we had was blind to it by
construction, and the layering frame that tells us where each future fix belongs.

> **Standing principle (state it, then live by it):**
> **A comment asserting an operational guarantee is a latent lie until a step or
> test fails when it's false.**

## 1. Goal vs. Outcome (read this first)

**Goal:** stand up a TAP instance and demo login to a partner.

**Outcome:** the standup reported success — `migrate` ran, the container came up,
runserver bound the port, the spawn script printed "Done — session is ready." Then
the first real login crashed:

```
ProgrammingError: relation "tap_cache" does not exist
```

The instance was never actually healthy. Every signal we trusted said "green"
because not one of them exercised the path that was broken. We patched it live and
made the demo, but the lesson is the gap, not the recovery.

## 2. Timeline

1. Instance stood up for the demo via the normal path (`migrate` → container up →
   runserver listening). All green.
2. First login attempt → 500. allauth's login flow touches the cache for
   rate-limiting; that was the **first cache access in the instance's life**, and
   it hit a table that did not exist.
3. Root-caused in the room: `settings.CACHES` default is `DatabaseCache` with
   `LOCATION="tap_cache"`. That table is created by `manage.py createcachetable` —
   **not** by a migration — and `createcachetable` was wired into **neither** the
   container entrypoint **nor** `spawn-session.sh`.
4. Immediate fix: added `createcachetable` to `docker/entrypoint.sh`, right after
   `migrate` (it is idempotent — no-ops when the table exists, safe on every start).
5. Demo proceeded. This bundle then built the durable guards so the *class* can't
   recur silently.

## 3. Root cause

`DatabaseCache` is provisioned **outside the migration system**. `migrate` — the
one provisioning step everything runs — does not create `tap_cache`; a separate
`createcachetable` command does. That command was documented (a settings comment
even *claimed* it ran "in boot/migrate") but never actually invoked by any boot
path. So:

- **Schema looked complete** (migrate succeeded) while a schema object the app
  hard-depends on was absent.
- **The broken path is never touched at boot.** Nothing at standup does a cache
  write. The first cache access is a *user action* (login rate-limiting), so the
  fault is invisible until a human exercises it — by construction, after "ready."

The settings comment asserting `createcachetable` "runs in boot/migrate" was the
latent lie made concrete: an operational guarantee with no step or test that would
fail when it was false.

## 4. Why every existing guard was blind — by construction

This is the heart of the AAR. Each guard missed not by accident but because its
construction structurally excludes this fault:

- **The test suite swaps the backend out.** `tap/test_settings.py` overrides
  `CACHES` to `LocMemCache`. Tests literally cannot see a missing `tap_cache` —
  the production backend is never instantiated under pytest. A substitution
  backend is a substitution blind spot.
- **The spawn liveness check tests "listening," not "works."** `spawn-session.sh`
  Step 5 polls `/admin/` and treats *any* HTTP response — **5xx included** — as
  success (its own comment says "500s are fine here; we just need to know
  runserver bound the port"). A perfectly broken instance returns 500s all day and
  passes. It proves the socket is open, nothing about the backends behind it.
- **There is no assembled-instance test.** The "Playwright" in
  `spec-dev-playwright-refresh` is a process-recovery script, not a test suite;
  nothing drives a real request through the real backends of a stood-up instance.

The common thread: **every guard validated a proxy** (migrate exit code, socket
open, locmem round-trip) **instead of the real thing** (a real cache write on the
real backend of the assembled instance). That is the latent-provisioning-fault
class in one sentence.

## 5. The layering frame — where does a provisioning step belong?

The fix forced an explicit model of *which layer owns which provisioning*, because
"just add it to spawn" would have left customer standups broken:

| Layer | Owns | Cadence | The `tap_cache` call belongs here because… |
| --- | --- | --- | --- |
| **entrypoint** (`docker/entrypoint.sh`) | DB **schema** — "fresh DB → schema current" | Every container start | `createcachetable` is schema provisioning, same category as `migrate`; idempotent, must run wherever migrate runs. **Chosen home.** |
| **boot** (`manage.py boot`) | **Instance state** above the schema (auth, plugin seed, collectors) | At standup | Cache table is below instance state, a schema precondition — not boot's job. |
| **spawn** (`spawn-session.sh`) | **Dev-env orchestration only** (worktrees, ports, creds) | Dev only | A customer instance never runs spawn; provisioning here would leave prod broken. |

**The boundary test:** *"would a customer standup also need this?"* If yes, it
cannot live in `spawn-session.sh`. `createcachetable` is yes → entrypoint. This is
the test to apply to every future provisioning step, and it is the same instinct
that should drive the convergence recommendation in §7.

## 6. NetBox prior art

NetBox solved this exact class and its design informed this bundle:

- **One canonical provisioning sequence as single source of truth.**
  [`upgrade.sh`](https://github.com/netbox-community/netbox/blob/main/upgrade.sh)
  runs an explicit ordered list — `migrate` → `trace_paths` → `collectstatic` →
  `remove_stale_contenttypes` → `reindex` → `clearsessions`/`clearcache`. Every
  out-of-migration provisioning step lives in *one* file nobody can forget to run.
  TAP's `tap_cache` gap is precisely the failure mode that one-canonical-sequence
  prevents: a provisioning step with no single owning list.
- **Django's system check framework: fail loud at startup.**
  [Django checks](https://docs.djangoproject.com/en/6.0/topics/checks/) run at
  startup; DB-needing checks use the `databases=` argument so they do **not** run
  on every management command. This is exactly the shape of the check this bundle
  added — loud at `migrate`/`check --database`, silent elsewhere.
- **A real-backend health endpoint does an actual round-trip.**
  [`netbox-healthcheck-plugin`](https://github.com/netbox-community/netbox-healthcheck-plugin)
  (built on django-health-check) does a **real cache set/get** plus DB and queue
  probes and returns JSON — exactly what catches a missing `tap_cache`. Notably,
  NetBox **core ships no health endpoint** (feature requests
  [#3291](https://github.com/netbox-community/netbox/issues/3291),
  [#8831](https://github.com/netbox-community/netbox/issues/8831)); it is a
  community plugin. We chose to hand-roll a minimal core one rather than take the
  `django-health-check` dependency — the probe surface is small and we want it core.

## 7. Corrective actions

### The pair (headline — different moments, both needed)

These two are the durable answer and they are deliberately a **pair**: they cover
different moments in an instance's life. Neither replaces the other.

1. **Startup system check = fail-at-boot.** `tap_boot/checks.py`
   `check_database_cache_table`, registered via `TapBootConfig.ready()` (import
   only registers — no DB access in `ready()`), tagged `Tags.database` so it runs
   during `migrate` and `check --database <alias>` but **not** on ordinary
   commands. When the default cache backend is `DatabaseCache`, it asserts the
   `LOCATION` table exists and emits a loud `checks.Error` with a
   `manage.py createcachetable` hint when missing. **This catches the fault before
   the instance is even handed over** — the moment provisioning is wrong.
2. **Real-backend health endpoint = verify / monitor / demo-gate.** `tap/health.py`
   at `/healthz` (conventional k8s-style spelling; login-exempt, exposes only
   coarse status strings). Independent probes, each reported separately: **db**
   (`SELECT 1`), **cache** (a **real `cache.set`→`cache.get` round-trip** — the
   probe that catches *this* bug), **queue** (best-effort DB-backed Steady-Queue
   table reachability; reports `"unknown"`, never fails, when indeterminate).
   Returns JSON `{"status", "checks"}`, HTTP 200 when critical probes (db, cache)
   pass, 503 otherwise. **This catches the fault at any later moment** — a
   monitor, a human, or the spawn gate hitting a live instance.

The system check is *static, pre-handover*; the health endpoint is *live,
post-handover*. Together they bracket the instance's whole lifecycle. That framing
— **fail-at-boot + verify/monitor** — is the headline recommendation, not either
piece alone.

### Convergence to one canonical sequence (carried forward — critical path)

NetBox's deepest lesson is the single ordered provisioning list. TAP today
scatters provisioning across `entrypoint.sh` (migrate, createcachetable),
`manage.py boot` (instance state), and implicit assumptions. The cure for the
*class* is one canonical, named, ordered sequence that is the single source of
truth for "what a fresh instance needs," with every out-of-migration step in it.
**This is explicitly carried into the plugin-config work, which is on the roadmap
critical path** (plugins grow provisioning needs — migrations, seed, static,
per-plugin tables — and that is exactly when scattered provisioning compounds).
Recommendation, not built here: design that convergence as part of plugin-config,
using §5's boundary test to place each step.

### The spawn-check flip (done here)

`spawn-session.sh` gained **Step 6.5**: after boot, it consumes `/healthz` in-container
(pure Python urllib, no curl), parses the JSON, and **requires HTTP 200 + `status:
healthy`**, failing the spawn loudly with a `scripts/dc logs web` pointer otherwise.
The Step 5 "is it listening" wait is kept (we still need the socket up before boot),
but the *functional* gate is now real: a 5xx instance no longer passes spawn. Live
verification: `/healthz` returns `200 {"status":"healthy","checks":{db,cache,queue
all healthy}}` on the running stack.

### Validation map (now partially guarded)

The assembled-instance health/standup-smoke surface was **unguarded** (no row, no
guard). This bundle adds a Validation Map row in `specs/spec-dev-validation.md`
recording it as **now partially guarded**: health endpoint + spawn gate + the
cache-table system check — honest about what is and isn't covered.

### Tiering the rest (honestly)

- **Built now:** the pair, the spawn flip, the Map row. Available *today*.
- **Recommended, carried into plugin-config:** the one-canonical-sequence
  convergence (critical path).
- **Decouple the check from the runner.** The cold-boot assembled-instance test is
  a *check* we can author today; the *CI pipeline that runs it on every push* is
  **roadmap item 5 (post-July)**. **Do not build a CI pipeline now.** The honest
  posture: the guard exists (system check + health endpoint + spawn gate run at
  spawn/boot today); wiring it into an automated runner waits for the CI/CD step.
  `spec-dev-validation.md`'s cold-boot gate stays *Proposed (target)*.

## 8. Provisioning-completeness audit (appendix)

What does a fresh instance need that nothing enforces?

- **`tap_cache` (the incident)** — created by `createcachetable`, outside
  migrations. **FIXED** (entrypoint) + now triple-guarded (system check, health
  cache probe, spawn gate).
- **`collectstatic`?** — **Not needed in dev; recommend for prod.** Dev runs
  `DEBUG=True` with `django.contrib.staticfiles`, so `runserver` serves app static
  directly (verified live: `/static/tap_web/favicon.ico` → HTTP 200). `STATIC_ROOT`
  is set but `collectstatic` is never run by any boot path. This is fine *only*
  because of the dev server; a production (`DEBUG=False`, real WSGI) deployment
  would serve nothing. **Did not add it** — unlike `createcachetable` it is *not*
  trivially-correct-everywhere (it is unnecessary and slightly wasteful in dev, and
  the right home is the future prod-provisioning sequence, not the dev entrypoint).
  Recommendation: fold `collectstatic` into the canonical sequence (§7) when the
  prod path is designed. This is exactly NetBox's `collectstatic`-in-`upgrade.sh`.
- **Other out-of-migration provisioning?** Audited the standup path. The other
  schema objects a fresh instance needs are migration-owned and covered by
  `migrate`: `django_session` (sessions migration), the `steady_queue_*` tables
  (steady_queue migrations). The `tap_secrets/` bind-mount target is provisioned by
  `spawn-session.sh` Step 3.5 (dev-env-owned, correct layer). **`tap_cache` was the
  unique gap** — the only app-depended-upon schema object created outside both
  migrations and a boot path. No other instance of the same fault was found.

## 9. Lessons → durable rules

- **Validate the real thing, not a proxy.** Migrate-exit-code, socket-open, and
  locmem-round-trip are proxies; a real cache write on the real backend of the
  assembled instance is the thing. Guards that test proxies are blind to whole
  fault classes by construction.
- **Substitution backends are substitution blind spots.** When tests swap a
  backend (locmem for DatabaseCache, ImmediateBackend for the real queue), name the
  resulting blind spot and cover it elsewhere (here: the health endpoint + spawn
  gate run the *real* backend).
- **Provisioning needs one canonical owner.** A step with no single owning list is
  a step someone will forget. Apply §5's boundary test ("would a customer standup
  need this?") to place it; converge toward one ordered sequence.
- **The pair, not the piece.** Fail-at-boot (system checks) and
  verify/monitor/demo-gate (health endpoint) cover different moments; ship both.
- **Decouple the check from the runner.** A guard can exist and run at spawn/boot
  today even though its CI automation is a later roadmap item. Don't block the
  guard on the pipeline.
- **A comment asserting an operational guarantee is a latent lie until a step or
  test fails when it's false.** The `createcachetable`-runs-in-boot comment was
  exactly that. Back every such claim with a failing step or test, or delete it.

## 10. What this bundle implemented vs. what remains

**Implemented (in the working tree, uncommitted for review):**
- `docker/entrypoint.sh` — `createcachetable` after `migrate` (immediate fix; was
  applied pre-bundle).
- `tap_boot/checks.py` + `tap_boot/apps.py` `ready()` — the database-tagged startup
  system check, with tests (`tap_boot/tests/test_checks.py`).
- `tap/health.py` + `tap/urls.py` route + `/healthz` login exemption in
  `tap/settings.py` — the real-backend health endpoint, with tests
  (`tap/tests/test_health.py`).
- `scripts/spawn-session.sh` — Step 6.5 functional health gate (replaces the
  5xx-passes blindness with a real 200+healthy requirement).
- `specs/spec-dev-validation.md` — the assembled-instance Validation Map row.

**Remains (recommendations, not built here):**
- One canonical provisioning sequence — carried into the plugin-config work
  (roadmap critical path).
- `collectstatic` in the prod-provisioning path (when prod is designed).
- CI automation of the cold-boot assembled-instance gate — **roadmap item 5,
  post-July**; the guard is authorable today, the runner is not this work.
