# Security Review: notgeorge/tap

## Scope

Repository-wide Codex Security scan, completed as a parent-agent high-impact scan after worker fan-out failed.

- Scan mode: repository
- Target kind: git_worktree
- Target ID: git:sha256:75c79590b0db6b31e3168a25927139e3897cf4911ee0fa6fc77b785e5621184c
- Revision: 1c6b57c3132a5340df4510340c8be6831c379cec
- Snapshot digest: codex-security-snapshot/v1:sha256:297e22723e4d415eedd69cbb4766487b9fec88b53f45b62ca22f8af13ccddac0
- Inventory strategy: repository
- Included paths: .
- Excluded paths: .git/, .venv/, node_modules/
- Runtime or test status: Docker web container available on host port 8030; live HTTP validation used requests from inside the web container to host.docker.internal:8030 with Host localhost:8030.
- Artifacts reviewed: architecture.md, plan/road-rampart.md, tap_auth/specs/spec-tap-auth-v0.md, tap_web/specs/spec-web-page.md, tap_web/specs/spec-web-panel.md, tap_web/specs/spec-web-rendering.md, tap_web/specs/spec-web-panel-security.md, tap_api routers, tap_web views/page/panel helpers/templates
- Scan context: TAP auth spec requires every graph read, including API read endpoints and page/panel render paths, to require grid.read.

Limitations and exclusions:
- Multi-agent exhaustive discovery failed due usage limit.
- Current runtime is a dev profile; deploy-posture hardening was checked by source and manage.py check --deploy output rather than a real TLS deploy profile.
- Excluded .git/: repository metadata, not application runtime source
- Excluded .venv/: third-party environment artifacts
- Excluded node_modules/: third-party dependency tree, if present

### Scan Summary

| Field | Value |
| --- | --- |
| Reportable findings | 3 |
| Severity mix | high: 1, medium: 1, low: 1 |
| Confidence mix | high: 3 |
| Coverage | partial |
| Validation mode | source review plus live network HTTP plus targeted pytest suite |

Canonical artifacts: `scan-manifest.json`, `findings.json`, and `coverage.json`. This report is a deterministic projection of those files.

## Threat Model

Single-tenant TAP instance with authenticated human/program actors, capability-gated graph data, web page/panel rendering, and API routes. Main attacker is an authenticated but capless user attempting to read or mutate graph data or bypass capability checks.

### Assets

- TAP graph entities and edges
- page/panel configuration and compliance/security dashboard data
- auth capabilities and roles
- collector/job metadata
- session cookies and CSRF tokens

### Trust Boundaries

- external HTTP client to Django web process
- authenticated session to capability policy
- page/panel presentation layer to graph service layer
- plugin code to core TAP graph APIs

### Attacker Capabilities

- anonymous web client
- authenticated user with no TAP capabilities
- tap_viewer with grid.read but no grid.write
- tap_admin with full capabilities

### Security Objectives

- All graph reads require grid.read
- All graph writes require grid.write or narrower capability
- Denied authz decisions are logged
- CSRF protects state-changing requests
- Templates do not execute stored user-controlled HTML

### Assumptions

- No multi-tenancy is intended
- Local Docker dev profile is not the deploy TLS profile
- Test client force_login is not sufficient proof for route authz; live HTTP proofs were required

## Findings

| Finding | Severity | Confidence |
| --- | --- | --- |
| [Generic panel endpoint lets no-cap users read panel content and request-selected entity fields](#finding-1) | high | high |
| [Dynamic page and nav-index routes enumerate page metadata and panel URLs without grid.read](#finding-2) | medium | high |
| [Entity type catalog API ignores grid.read for authenticated no-cap users](#finding-3) | low | high |

### Confidence Scale

| Label | Meaning |
| --- | --- |
| high | Direct evidence supports the finding with no material unresolved blocker. |
| medium | Evidence supports a plausible issue, but material runtime or reachability proof remains. |
| low | Evidence is incomplete and the item is retained only for explicit follow-up. |

<a id="finding-1"></a>

### [1] Generic panel endpoint lets no-cap users read panel content and request-selected entity fields

| Field | Value |
| --- | --- |
| Severity | high |
| Confidence | high |
| Confidence rationale | Direct source trace and live network validation agree: capless panel GET returned 200 while guarded object/API routes returned 403 and logged denials. |
| Category | authorization-bypass |
| CWE | CWE-862 |
| Affected lines | tap_web/views.py:75-110, tap_web/panels/viewer_panel/__init__.py:108-121, tap_web/templates/tap_web/panels/text_panel.html:1-4 |

#### Summary

The generic /panel/\<slug\>--\<uuid\>/ route resolves a Panel and renders its template without a grid.read authorization decision. A capless authenticated user received 200 over the Docker-published HTTP port, and a ViewerPanel instance could be pointed at another entity by query string to reveal fields that /object/... correctly denied.

#### Root Cause

Panel fragments were treated as UI implementation details instead of graph-read entrypoints, so the route relies on downstream helpers that are not guaranteed to enforce grid.read.

**Panel view resolves and renders without authorization** — `tap_web/views.py:75-110`

The route reaches graph-backed Panel state and renders the panel template without calling authorize(..., "grid.read", ...).

```python
def panel_view(request: HttpRequest, panel_url_id: str) -> HttpResponse:
    ...
    panel = Panel.objects.select_related("entity").get(entity__pk=entity_uuid)
    ...
    extra_ctx = panel_type.get_view_context(panel, request) or {}
    return render(request, panel.view, {"panel": panel, ...})
```

**ViewerPanel resolves request-selected object** — `tap_web/panels/viewer_panel/__init__.py:108-121`

When used behind the unguarded panel endpoint, query parameters select an arbitrary registered entity type and entity id for direct ORM lookup.

```python
model_cls = get_model_class(entity_type)
obj = model_cls.objects.select_related("entity").get(entity__pk=entity_id)
```

#### Validation

Direct source trace and live network validation agree: capless panel GET returned 200 while guarded object/API routes returned 403 and logged denials. Validation details were not recorded separately.

Validation method: live_http

**Panel view resolves and renders without authorization** — `tap_web/views.py:75-110`

The route reaches graph-backed Panel state and renders the panel template without calling authorize(..., "grid.read", ...).

```python
def panel_view(request: HttpRequest, panel_url_id: str) -> HttpResponse:
    ...
    panel = Panel.objects.select_related("entity").get(entity__pk=entity_uuid)
    ...
    extra_ctx = panel_type.get_view_context(panel, request) or {}
    return render(request, panel.view, {"panel": panel, ...})
```

**ViewerPanel resolves request-selected object** — `tap_web/panels/viewer_panel/__init__.py:108-121`

When used behind the unguarded panel endpoint, query parameters select an arbitrary registered entity type and entity id for direct ORM lookup.

```python
model_cls = get_model_class(entity_type)
obj = model_cls.objects.select_related("entity").get(entity__pk=entity_id)
```

#### Dataflow

The canonical finding records the affected path at tap_web/views.py:75-110, tap_web/panels/viewer_panel/__init__.py:108-121, tap_web/templates/tap_web/panels/text_panel.html:1-4, but no expanded source-to-sink narrative was recorded.

#### Reachability

Reachability was not recorded beyond the canonical finding summary and affected locations.

#### Severity

**High** — Remote authenticated low-privilege users can bypass the central graph-read permission and read TAP-managed object data. The route is designed for HTMX fragments but is directly reachable and accepts request-selected ViewerPanel targets.

Additional runtime or deployment evidence could raise or lower this severity.

#### Remediation

Call tap_auth.policy.authorize(get_caller_context(), "grid.read", operation="panel_view") before any Panel lookup or panel-type context building. Add defense-in-depth grid.read authorization before ViewerPanel request-selected object resolution, and add no-cap HTTP tests proving panel fragments return 403 and emit authz-denial logs.

Tests:
- No-cap live HTTP GET /panel/\<panel-url-id\>/ returns 403 and emits \[e5d9\]/\[a6b7\].
- No-cap live HTTP GET to a ViewerPanel with target entity query parameters returns 403.
- tap_viewer can read panel fragments; tap_admin can read and edit where grid.write is required.

Preventive controls:
- Static route/ORM lint for graph model access in tap_web views and panel helpers unless preceded by an explicit authorize call.
- Central helper for graph-read guarded panel/page resolution.

<a id="finding-2"></a>

### [2] Dynamic page and nav-index routes enumerate page metadata and panel URLs without grid.read

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | Source trace shows direct ORM reads, and live HTTP validation showed capless page/nav requests returning 200 while protected graph-read routes returned 403. |
| Category | authorization-bypass |
| CWE | CWE-862 |
| Affected lines | tap_web/views.py:43-67, tap_web/views.py:520-562, tap_web/views.py:716-757, tap_web/page.py:14-61 |

#### Summary

The page, parameterized page, landing redirect, and nav-index routes read Page, Edge, and Panel rows directly without a grid.read authorization decision. A capless authenticated user received page content and the nav catalog, including page metadata and panel URL identifiers that chain into the panel-fragment bypass.

#### Root Cause

Page/navigation rendering predates the authz backstop and uses graph ORM reads as a presentation convenience without treating the routes as graph-read entrypoints.

**Page routes render without grid.read** — `tap_web/views.py:43-67`

The route resolves and renders the page before any graph-read authorization decision.

```python
page = get_page_by_slug(slug)
if page is None:
    raise Http404(...)
return _render_page(request, page)
```

**Nav index enumerates pages directly** — `tap_web/views.py:716-757`

The nav endpoint exposes page metadata from direct ORM rows without grid.read.

```python
pages_qs = Page.objects.filter(discoverable=True).order_by("-nav_weight", "slug")
...
"url": page.slug, "name": page.name, "description": page.description or ""
```

**Page rendering exposes panel URL identifiers** — `tap_web/views.py:526-545`

The page render prepares panel URL identifiers later used by HTMX, which are also sufficient to call the unguarded panel endpoint directly.

```python
panel_slots = get_page_panels(page)
for panel_id, panel in panel_slots:
    panels_by_id[panel_id] = f"{panel.slug}--{panel.entity_id}"
```

#### Validation

Source trace shows direct ORM reads, and live HTTP validation showed capless page/nav requests returning 200 while protected graph-read routes returned 403. Validation details were not recorded separately.

Validation method: live_http

**Page routes render without grid.read** — `tap_web/views.py:43-67`

The route resolves and renders the page before any graph-read authorization decision.

```python
page = get_page_by_slug(slug)
if page is None:
    raise Http404(...)
return _render_page(request, page)
```

**Nav index enumerates pages directly** — `tap_web/views.py:716-757`

The nav endpoint exposes page metadata from direct ORM rows without grid.read.

```python
pages_qs = Page.objects.filter(discoverable=True).order_by("-nav_weight", "slug")
...
"url": page.slug, "name": page.name, "description": page.description or ""
```

**Page rendering exposes panel URL identifiers** — `tap_web/views.py:526-545`

The page render prepares panel URL identifiers later used by HTMX, which are also sufficient to call the unguarded panel endpoint directly.

```python
panel_slots = get_page_panels(page)
for panel_id, panel in panel_slots:
    panels_by_id[panel_id] = f"{panel.slug}--{panel.entity_id}"
```

#### Dataflow

The canonical finding records the affected path at tap_web/views.py:43-67, tap_web/views.py:520-562, tap_web/views.py:716-757, tap_web/page.py:14-61, but no expanded source-to-sink narrative was recorded.

#### Reachability

Reachability was not recorded beyond the canonical finding summary and affected locations.

#### Severity

**Medium** — The issue exposes graph-backed page names, descriptions, layouts, slot ids, and panel URL ids to authenticated users that lack grid.read. It is also an exploit enabler for direct panel reads.

Additional runtime or deployment evidence could raise or lower this severity.

#### Remediation

Require grid.read at the start of landing_view, page_view, parameterized_page_view, _render_grid_placeholder fallback, and nav_index_view before Page/Edge/Panel rows are loaded. Preserve anonymous login redirects, but authenticated no-cap users should receive 403 and log an authz denial.

Tests:
- No-cap live HTTP GET for page, parameterized page, landing page, and /__nav-index.json returns 403 and emits \[e5d9\]/\[a6b7\].
- tap_viewer still receives 200 for page/nav read routes.

Preventive controls:
- Static authz coverage rule for Page/Panel/Edge ORM reads in web views.
- Central page-resolution service that requires CallerContext.

<a id="finding-3"></a>

### [3] Entity type catalog API ignores grid.read for authenticated no-cap users

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | high |
| Confidence rationale | The router body is a direct EntityType.objects.all() call and live network validation returned 200 for capless users. |
| Category | authorization-bypass |
| CWE | CWE-862 |
| Affected lines | tap_api/routers/entity_types.py:12-14 |

#### Summary

The /api/v1/entity-types/ endpoint is session-authenticated but returns EntityType rows directly without checking grid.read. Live HTTP validation showed capless users receive 200 from this catalog while /api/v1/entities/ correctly returns 403.

#### Root Cause

Read-only type metadata was treated as harmless API catalog data and missed the auth spec requirement that every graph read, including API read endpoints, requires grid.read.

**Entity type API returns catalog without authorization** — `tap_api/routers/entity_types.py:12-14`

The route is mounted with session authentication, but it does not authorize grid.read before returning graph type metadata.

```python
@router.get("/", response=list[EntityTypeOut])
def list_entity_types(request: HttpRequest) -> list[EntityType]:
    return list(EntityType.objects.all())
```

#### Validation

The router body is a direct EntityType.objects.all() call and live network validation returned 200 for capless users. Validation details were not recorded separately.

Validation method: live_http

**Entity type API returns catalog without authorization** — `tap_api/routers/entity_types.py:12-14`

The route is mounted with session authentication, but it does not authorize grid.read before returning graph type metadata.

```python
@router.get("/", response=list[EntityTypeOut])
def list_entity_types(request: HttpRequest) -> list[EntityType]:
    return list(EntityType.objects.all())
```

#### Dataflow

The canonical finding records the affected path at tap_api/routers/entity_types.py:12-14, but no expanded source-to-sink narrative was recorded.

#### Reachability

Reachability was not recorded beyond the canonical finding summary and affected locations.

#### Severity

**Low** — The endpoint exposes model/plugin catalog metadata rather than object contents, but the auth spec states all graph reads require grid.read and this metadata helps enumerate the instance shape.

Additional runtime or deployment evidence could raise or lower this severity.

#### Remediation

Authorize grid.read in list_entity_types before querying EntityType, or route the catalog through a gated read service. Add no-cap tests for /api/v1/entity-types/ mirroring the existing /api/v1/entities/ denial tests.

Tests:
- No-cap live HTTP GET /api/v1/entity-types/ returns 403 and emits \[e5d9\].
- tap_viewer GET /api/v1/entity-types/ returns 200.

Preventive controls:
- Require every core API read router to declare the capability it enforces.
- Extend authz coverage tests to include metadata/catalog endpoints.

## Reviewed Surfaces

| Surface | Risk Area | Outcome | Notes |
| --- | --- | --- | --- |
| tap_web panel fragment routes | authorization | Reported | Validated capless read bypass and ViewerPanel object read bypass. Evidence: artifacts/05_findings/cs-tap-web-panel-001/validation_report.md, artifacts/05_findings/cs-tap-web-panel-001/attack_path_analysis_report.md, artifacts/06_runtime/live_http_authz_matrix.json, artifacts/06_runtime/log_access_control_sample.txt |
| tap_web page, landing, and nav-index routes | authorization | Reported | Validated capless page/nav enumeration and panel URL disclosure. Evidence: artifacts/05_findings/cs-tap-web-page-002/validation_report.md, artifacts/05_findings/cs-tap-web-page-002/attack_path_analysis_report.md, artifacts/06_runtime/live_http_authz_matrix.json |
| tap_api entity-type catalog | authorization | Reported | Validated capless metadata read. Evidence: artifacts/05_findings/cs-tap-api-typecat-003/validation_report.md, artifacts/05_findings/cs-tap-api-typecat-003/attack_path_analysis_report.md, artifacts/06_runtime/live_http_authz_matrix.json |
| tap_api entities, edges, searches, and Gryphon | authorization | No issue found | Source and tests show grid.read enforcement. Live no-cap entities returned 403 and logged \[e5d9\]. Evidence: artifacts/06_runtime/live_http_authz_matrix.json, artifacts/06_runtime/log_access_control_sample.txt, artifacts/06_runtime/pytest_summary.txt |
| tap_web object view and edit guards | authorization | No issue found | Object view denies no-cap before object resolution; panel edit denied no-cap write and viewer write. Evidence: artifacts/06_runtime/live_http_authz_matrix.json, artifacts/06_runtime/log_access_control_sample.txt |
| access-control violation logging | logging | Reported | Guarded denials log \[e5d9\]/\[a6b7\]; bypassed panel/page/nav/entity-types reads do not log because authorization is not invoked. Evidence: artifacts/06_runtime/log_access_control_sample.txt |
| CSRF protection for POST routes | csrf | No issue found | Missing, bogus, and evil-origin tokens were rejected; valid same-origin token was the only write that landed. Evidence: artifacts/06_runtime/live_http_csrf_xss_headers.json |
| XSS rendering and explicit safe sinks | xss | No issue found | TextPanel hostile script/img rendered escaped; inspected explicit safe JSON and preview sinks are escaped. Evidence: artifacts/06_runtime/live_http_csrf_xss_headers.json, artifacts/02_discovery/finding_discovery_report.md |
| HTTP headers, CORS, same-origin, and deploy posture | http-hardening | Needs follow-up | Live responses set DENY/nosniff/same-origin headers and no ACAO. Dev runtime fails deploy checks, but deploy boot has a fail-closed posture gate; verify real deploy profile before release. Evidence: artifacts/06_runtime/live_http_csrf_xss_headers.json, artifacts/06_runtime/deploy_check_summary.txt |
| tap_auth policy, login wall, boot gate, OIDC source docs alignment | authentication | No issue found | Targeted auth tests and source review showed no bypass in policy decorators, login wall, deploy gate, or Google hd/email verification assumptions. Evidence: artifacts/06_runtime/pytest_summary.txt, artifacts/06_runtime/deploy_check_summary.txt |
| plugin API routers | authorization | Not applicable | Search found no mounted plugin API routers in this worktree beyond tests/service helpers. Evidence: artifacts/02_discovery/finding_discovery_report.md |
| ranked discovery worklist closure | coverage | Needs follow-up | 917 rank-input rows were given explicit parent-reviewed/deferred closure after worker fan-out failed. Evidence: artifacts/02_discovery/work_ledger.jsonl, artifacts/02_discovery/rank_input.jsonl |

## Open Questions And Follow Up

- Should page/nav read authorization happen at every route entrypoint, or should tap_web page service helpers require CallerContext and enforce grid.read centrally?
  - Follow-up prompt: Design the tap_web page/panel read authorization fix and tests.
- Should the authz coverage ratchet baseline be regenerated after line drift, or are the tap_grid service entries real remaining hardening work?
  - Follow-up prompt: Triage tap/tests/test_authz_coverage.py baseline drift.
- The requested multi-agent exhaustive pass could not run because all discovery workers failed with usage-limit errors. Parent-agent reviewed high-impact auth/web/API/spec surfaces and marked remaining rank-input rows deferred.
  - Follow-up prompt: Review deferred unit deferred.worker-fanout and close its stated proof gap. Paths: \*. Surfaces: surface.discovery_worklist.
- Plugin templates/panels received targeted XSS and authz-source spot checks, but not every plugin collector/action/domain route received live capability permutations.
  - Follow-up prompt: Review deferred unit deferred.full-plugin-domain-review and close its stated proof gap. Paths: plugins/. Surfaces: surface.discovery_worklist.
- Vendored/minified JavaScript was not audited line-by-line; first-party dangerous DOM sinks and runtime render behavior were checked.
  - Follow-up prompt: Review deferred unit deferred.vendor-js-line-audit and close its stated proof gap. Paths: tap_web/static/tap_web/js/lib/. Surfaces: surface.xss_rendering.
