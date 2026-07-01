# TAP Security Rerunner Guide

This guide is for future Codex Security runs and other security tooling instances
that need to come online quickly against TAP, The Analogy Platform.

TAP is a Python/Django and PostgreSQL-backed graph system for modeling systems,
operations, compliance, and security. Treat the local instance as production for
security testing purposes, even when the runtime profile is a dev profile.

## Core Security Invariant

TAP's central authorization rule is:

> Passing request authentication never implies permission.

Every graph read requires `grid.read`. Every graph write requires `grid.write`
or a narrower capability. This includes direct service reads, Gryphon, Search,
API read endpoints, page rendering, panel rendering, and helper paths that
resolve graph-backed objects for display.

Denied authorization decisions should log through:

- `tap_auth.policy` with site token `[e5d9]`
- `tap_auth.middleware` with site token `[a6b7]` for web denials

If a no-cap user receives graph data and no denial log appears, assume the route
skipped the authorization policy entirely.

## Read First

Start with these files before broad scanning:

1. `AGENTS.md`
2. `architecture.md`
3. `plan/road-rampart.md`
4. `tap_auth/specs/spec-tap-auth-v0.md`
5. `tap_web/specs/spec-web-page.md`
6. `tap_web/specs/spec-web-panel.md`
7. `tap_web/specs/spec-web-rendering.md`
8. `tap_web/specs/spec-web-panel-security.md`
9. `specs/spec-security-posture.md`
10. The relevant `tap_api/routers/` code and tests

Specs are canonical. If current route behavior disagrees with a spec, treat the
spec as the intended security contract and the behavior as suspect.

## Runtime Rules

Use the Python inside the container for Django/runtime validation:

```bash
scripts/dc exec web uv run python ...
```

The local web process is commonly published as:

```text
0.0.0.0:8030 -> container port 8000
```

For authorization validation, prefer real HTTP from inside the container to the
host-published port:

```python
BASE = "http://host.docker.internal:8030"
HEADERS = {"Host": "localhost:8030"}
```

Do not rely only on Django's test client or `force_login()` when proving route
authz. Create real users, log in through `/auth/login/`, keep the session
cookies, and hit the app over HTTP.

## Capability Matrix

Create and test at least these actors:

- anonymous client
- authenticated human user with no TAP capability groups
- `tap_viewer` user with `grid.read`
- `tap_admin` user
- optional program user for non-human actor constraints

Expected pattern:

- anonymous web pages usually redirect to `/auth/login/`
- anonymous APIs usually return `401`
- capless graph reads should return `403` and emit authz-denial logs
- `tap_viewer` can read graph-backed surfaces
- `tap_viewer` cannot write
- `tap_admin` can read and write where the request is otherwise valid

## High-Value Surfaces

Prioritize these before spending time on lower-signal files:

- `tap_web/views.py`
- `tap_web/page.py`
- `tap_web/panels/*`
- `tap_web/templates/*`
- `tap_api/routers/*`
- `tap_auth/policy.py`
- `tap_auth/middleware.py`
- `tap_grid/search`
- Gryphon executor and API router
- service-layer graph read/write chokepoints
- plugin panel context builders and templates
- `tap_cares` collector/action execution paths

Search for direct graph ORM reads in web/API paths:

```bash
rg -n "Page\\.objects|Panel\\.objects|Entity\\.objects|EntityType\\.objects|Edge\\.objects|model_cls\\.objects" tap_* plugins
```

Any route that touches graph state before an explicit `grid.read` authorization
decision deserves review.

## Known Finding Classes To Retest

Recent validated classes included:

1. Generic panel fragments: `/panel/<slug>--<uuid>/` resolved and rendered
   `Panel` data without `grid.read`.
2. ViewerPanel object selection: a ViewerPanel could use `entity_id` and
   `entity_type` query parameters to render another object behind the unguarded
   panel endpoint.
3. Page/nav enumeration: dynamic page routes and `/__nav-index.json` exposed
   page metadata, layout slots, and panel URL identifiers without `grid.read`.
4. Entity type catalog: `/api/v1/entity-types/` returned graph metadata to
   authenticated no-cap users.

Retest these first after fixes, then expand to nearby route families.

## Logging Checks

For every denied request, check both status and logs.

Good guarded denial evidence looks like:

```text
tap_auth.policy ... [e5d9] authz denied: reason=capability_denied capability=grid.read ...
tap_auth.middleware ... [a6b7] web authz denied ...
```

If a no-cap request returns `200`, no authz denial log may appear because the
policy was never called. Record that as part of the finding.

## POST, CSRF, XSS, CORS, And Headers

Always run a small live HTTP sanity pass:

- POST without CSRF token returns `403`
- POST with bogus CSRF token returns `403`
- cross-origin POST returns `403`
- valid same-origin CSRF token is the only write that lands
- stored `<script>` and `<img onerror>` payloads render escaped
- template `|safe` uses are fed by `safe_json()` or clearly escaped HTML
- responses do not unexpectedly emit `Access-Control-Allow-Origin`
- `X-Frame-Options` is `DENY`
- `X-Content-Type-Options` is `nosniff`
- `Referrer-Policy` is `same-origin`
- `Cross-Origin-Opener-Policy` is `same-origin`

The dev profile may fail `manage.py check --deploy`. Before reporting that as an
exploitable deployment issue, verify whether the deploy boot path fails closed.
`tap_auth.boot._check_deploy_posture` is the relevant source.

## Useful Commands

Targeted auth/web/API tests:

```bash
scripts/dc exec web uv run python -m pytest \
  tap_auth/tests/test_policy.py \
  tap_auth/tests/test_enforcement.py \
  tap_auth/tests/test_login_wall.py \
  tap_api/tests/test_gryphon.py \
  tap_api/tests/test_searches.py \
  tap_api/tests/test_entity_types.py \
  tap_web/tests/test_views.py \
  tap_web/tests/test_reserved_prefixes.py \
  tap/tests/test_authz_coverage.py -q
```

Deploy posture:

```bash
scripts/dc exec web uv run python manage.py check --deploy
```

Logs:

```bash
scripts/dc logs --since 2m web
```

Broad source search:

```bash
rg -n "objects\\.|authorize\\(|requires_capability|csrf_exempt|mark_safe|\\|safe|innerHTML|insertAdjacentHTML" tap_* plugins
```

## Efficient Scan Order

1. Read the architecture, active roadmap step, and auth/web/API specs.
2. Build the threat model around anonymous, capless, viewer, and admin actors.
3. Enumerate routes and graph-read sinks.
4. Live-test high-value routes over real HTTP.
5. Compare no-cap behavior against guarded graph APIs.
6. Check denial logs.
7. Check POST, CSRF, XSS, CORS, and browser-security headers.
8. Broaden into plugin-specific surfaces once core boundaries are understood.

TAP's highest-signal bug class is usually a presentation/helper route that reads
graph state outside the capability policy. Prove or disprove those first.

## Reporting Expectations

For each finding, include:

- exact route or callable
- required capability
- actual no-cap status
- expected guarded status
- source root-control line
- sink line
- live HTTP proof
- access-control logging behavior
- remediation
- no-cap regression test

For coverage, be explicit about deferred work. A partial scan with precise
receipts is better than an exhaustive-looking report that silently skipped
surfaces.
