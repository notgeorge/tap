# tap-cares Administrivia Surface Specification

## Philosophy

tap-cares's administrivia surface gives humans a clear control surface for observing and operating CARES capabilities. The first target is collectors: users should be able to see which collectors exist, whether their runner code is available, what happened during recent runs, and manually execute the FedRAMP 20x KSI collector from a TAP-native page.

The canonical CARES runtime concepts remain owned by `tap_cares`: `Collector`, `CollectionJob`, `HAS_JOB`, collector registry resolution, Django Tasks execution, and GRIFT batch correlation. The pages and panels that surface these concepts live in the Administrivia plugin under `plugins/administrivia/tap_cares/` because Administrivia is TAP's first-party host for internal operator pages — every spec describing one of those pages is filenamed `spec-...-administrivia.md` so the operator-page surface is trivially grep-able as a class.

This surface is intentionally human-triggered. Pressing a Run button is explicit user intent to execute an existing on-grid collector capability. This spec does not introduce autonomous actions, scheduler policy, or a new write path around the CARES service layer.

## Goals

|    |                     |                                                                 |
| :---: | ---              | ---                                                             |
| 1. | Observable          | Show collector availability, run state, last outcome, and failures |
| 2. | Executable          | Let a user manually execute an on-grid collector capability |
| 3. | Drillable           | Let users inspect a collector's run history and GRIFT batch outcomes |
| 4. | Implementation-Clear | Keep CARES semantics in `tap_cares` while hosting UI code in Administrivia |
| 5. | KSI-Ready           | Support the initial "run FedRAMP 20x KSI collector" workflow |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-tap-cares-administrivia-ownership | [Administrivia Ownership](#administrivia-ownership) | Implemented | CARES owns semantics; Administrivia hosts the operator pages |
| req-tap-cares-administrivia-homepage | [CARES Homepage](#cares-homepage) | Implemented | Overview page for CARES subsystem status, starting with collectors |
| req-tap-cares-administrivia-collector-table | [Collector Table](#collector-table) | Implemented | Table listing available collectors and their latest run state |
| req-tap-cares-administrivia-manual-run | [Manual Collector Execution](#manual-collector-execution) | Implemented | Human-triggered run action calls `run_collection()` |
| req-tap-cares-administrivia-htmx-trigger | [HTMX Trigger Surface](#htmx-trigger-surface) | Implemented | v0 browser POST path for manual collector execution |
| req-tap-cares-administrivia-collector-detail | [Collector Detail Page](#collector-detail-page) | Implemented | Collector-specific page with metadata and run history |
| req-tap-cares-administrivia-run-observability | [Run Observability](#run-observability) | Implemented | Display timestamps, status, errors, task IDs, and GRIFT batch correlation |
| req-tap-cares-administrivia-ksi-path | [FedRAMP KSI Collector Path](#fedramp-ksi-collector-path) | Implemented | Initial happy path for executing the KSI collector from the homepage |
| req-tap-cares-administrivia-api-trigger | [API Trigger Surface](#api-trigger-surface) | Backlog | Future API chokepoint for collector execution requests |

### Administrivia Ownership
----
RID: `req-tap-cares-administrivia-ownership`
Status: `Implemented`

The CARES administrivia-surface requirements live in `tap_cares/specs/` because the behavior being surfaced belongs to `tap_cares`. The naming convention is deliberate: any spec whose pages or panels render through the Administrivia plugin is filenamed `spec-...-administrivia.md` (e.g. this file, `spec-tap-cares-administrivia.md`), and any cross-spec reference uses the same form. That makes the operator-surface family trivially grep-able as a class — `grep -rln "spec-.*-administrivia"` returns the full set.

The initial page, panel, template, static asset, and optional view code lives in:

```text
plugins/administrivia/tap_cares/
```

Administrivia should reference this spec from its hosted-surface index rather than duplicating these CARES requirements.

The administrivia surface must use existing CARES services and models:

- `Collector` for on-grid collector capability rows
- `CollectionJob` for run history
- `HAS_JOB` for collector-to-run provenance
- `tap_cares.registry.get_collector()` or equivalent registry inspection for runner availability
- `tap_cares.services.run_collection()` for manual execution
- `CollectionJob.grift_batches` for imported/skipped GRIFT batch correlation

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-administrivia-ownership-1 | Spec Lives With CARES | Implemented | CARES administrivia-surface behavior is specified under `tap_cares/specs/`. | |
| req-tap-cares-administrivia-ownership-2 | Pages Live In Administrivia | Implemented | The pages, panels, templates, and static assets that render this surface live under `plugins/administrivia/tap_cares/`. | |
| req-tap-cares-administrivia-ownership-3 | Service Layer Execution | Implemented | Manual execution routes through `tap_cares.services.run_collection()`. | |
| req-tap-cares-administrivia-ownership-4 | No New Execution Path | Implemented | The administrivia surface does not bypass collector registry, Django Tasks, CollectionJob, or GRIFT import contracts. | |
| req-tap-cares-administrivia-ownership-5 | Filename Convention | Implemented | Specs whose pages or panels are hosted by the Administrivia plugin are filenamed `spec-...-administrivia.md`, so the operator-surface family is grep-able as a class. | |

### CARES Homepage
----
RID: `req-tap-cares-administrivia-homepage`
Status: `Implemented`

The CARES homepage is the top-level Administrivia page for CARES subsystem status.

v0 focuses on collectors. The page should be structured so future sections can add receivers, emitters, actions, and schedules without redesigning the route.

Initial route:

```text
/administrivia/cares
```

Initial page content:

- summary strip with collector counts and run health
- collectors table

Recommended summary values:

- total collector nodes
- collectors with resolvable runner code
- collectors with missing runner code
- currently running collection jobs
- last successful collection time
- collectors whose latest run failed

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-administrivia-homepage-1 | Route Exists | Implemented | CARES homepage is reachable at `/administrivia/cares`. | |
| req-tap-cares-administrivia-homepage-2 | Collector Focus | Implemented | v0 homepage shows collector status before other CARES subsystems exist. | |
| req-tap-cares-administrivia-homepage-3 | Summary Strip | Implemented | Homepage includes aggregate collector health and run-state summary values. | |
| req-tap-cares-administrivia-homepage-4 | Future Subsystems Reserved | Implemented | Layout leaves room for future receivers, emitters, actions, and schedules. | |

### Collector Table
----
RID: `req-tap-cares-administrivia-collector-table`
Status: `Implemented`

The collectors table lists all on-grid `Collector` nodes and summarizes their execution readiness and recent run outcome.

Initial columns:

| Column | Source | Notes |
| --- | --- | --- |
| Name | `Collector.name` | Row opens collector detail page |
| Source Plugin | `collector_registry` scope (raw dotted path) | Shown as a small code badge. Human-readable plugin names are a future enhancement (deferred — see Future). |
| Description | `Collector.description` | Plain text; gets the dominant horizontal column space |
| Run State | latest `CollectionJob.status` | `idle`, `running`, or current status |
| Last Run | latest finished `CollectionJob.status` | `successful`, `failed`, or `never run` |
| Last Run At | latest finished `CollectionJob.finished_at` | Empty for never run |
| Summary | latest finished `CollectionJob.summary` | At-a-glance one-liner describing the last run (success or failure); collector-authored on success, count-derived fallback on failure. Empty for collectors that don't set one. |
| Action | Administrivia panel POST | Manual Run button |

Availability is no longer a column. The Run button stays disabled when the registry has no runner for the collector's `collector_registry` value, and that row is tinted to indicate the unavailable state. The previous explicit `available` / `missing runner` pill column was redundant once the Run button conveyed the same state through its disabled affordance.

The Registry Key column was removed because the full `scope:key` is already visible on the collector detail page; the homepage table doesn't need to repeat it.

The table auto-refreshes via a quiet HTMX GET poll every 5 seconds so manual-Run state and in-flight job lifecycle transitions appear without an operator reload. The poll is rooted on the panel container and re-issued each swap.

The table should avoid implying that registry availability and last run outcome are the same thing. A collector with no registered runner can still have a historical successful run; the row tint and disabled Run button surface the current availability without conflating it with the last-run outcome.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-administrivia-collector-table-1 | All Collectors Listed | Implemented | Table includes every on-grid `Collector` node. | |
| req-tap-cares-administrivia-collector-table-2 | Availability Distinct | Implemented | Registry resolution is shown by row tint + disabled Run button, separate from last-run outcome columns. | |
| req-tap-cares-administrivia-collector-table-3 | Latest Job Summarized | Implemented | Table displays latest run state, last finished run, timestamp, and bounded error summary. | |
| req-tap-cares-administrivia-collector-table-4 | Row Drilldown | Implemented | Clicking a collector row opens the collector-specific Administrivia page. | |
| req-tap-cares-administrivia-collector-table-5 | Quiet Auto-Refresh | Implemented | The table polls itself via HTMX GET every 5 seconds and replaces its outer HTML in place, so manual-Run state and in-flight job transitions appear without a page reload. | |

### Manual Collector Execution
----
RID: `req-tap-cares-administrivia-manual-run`
Status: `Implemented`

The CARES administrivia surface provides a manual Run action for a collector.

The Run action is a human-triggered POST. It must:

1. Resolve the target `Collector` by entity ID.
2. Verify that the collector's registry key resolves to a registered runner.
3. Call `tap_cares.services.run_collection(collector)`.
4. Return or display the created `CollectionJob`.
5. Refresh the homepage row or navigate to the collector detail page.

The Run button may guard against obvious duplicate manual runs, such as a collector already showing a `RUNNING` job, but the general collector concurrency policy is Backlog until the enqueue path and scheduler behavior are specified together. The future service-layer concurrency policy is tracked in `tap_cares/specs/spec-tap-cares-collector.md` (`req-tap-cares-collector-concurrency`).

The UI handler must not create `CollectionJob` nodes or `HAS_JOB` edges directly. It is an adapter from a browser POST into the CARES execution service. `run_collection()` owns job creation, edge creation, task enqueueing, and concurrency enforcement, and that service must route TAP-managed node and edge creation through the grid service layer.

**Current Deviation (v0).** The eventual flow inserts the scheduler subsystem between the Administrivia POST and `run_collection`: the Administrivia panel handler creates a `ScheduledCollection` (or run-now trigger) and the scheduler picks it up and calls `run_collection`. The scheduler subsystem is not yet specced or built. Until it lands, the Administrivia panel handler calls `run_collection` directly. This is documented in the collector spec at `req-tap-cares-collector-run-collection` and is the same temporary state described there.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-administrivia-manual-run-1 | POST Only | Implemented | Manual execution uses a POST action, not a GET link. | |
| req-tap-cares-administrivia-manual-run-2 | Registry Checked | Implemented | UI checks runner availability before enqueuing and surfaces missing runner errors. | |
| req-tap-cares-administrivia-manual-run-3 | Uses run_collection | Implemented | Manual execution calls `tap_cares.services.run_collection()`. | |
| req-tap-cares-administrivia-manual-run-4 | Job Visible | Implemented | The resulting `CollectionJob` is visible after the action completes. | |
| req-tap-cares-administrivia-manual-run-5 | Duplicate Running Guard | Implemented | UI may prevent or warn against starting a second manual run when the collector already has a `RUNNING` job. | Full concurrency policy is Backlog; cross-ref `req-tap-cares-collector-concurrency`. |
| req-tap-cares-administrivia-manual-run-6 | No Direct Node Creation In UI | Implemented | The UI handler does not directly create `CollectionJob` nodes or `HAS_JOB` edges. | Creation belongs to CARES services and the grid service layer. |

### HTMX Trigger Surface
----
RID: `req-tap-cares-administrivia-htmx-trigger`
Status: `Implemented`

The initial browser trigger surface for manual collector execution is an HTMX POST handled by an Administrivia CARES panel type.

The preferred v0 flow:

1. The CARES homepage hosts a collector-administrivia panel.
2. Each collector row renders a Run button inside a small form.
3. The form posts to the panel endpoint with HTMX.
4. The panel type implements `handle_post(panel, request)`.
5. `handle_post()` validates the action and target collector entity ID.
6. `handle_post()` calls `tap_cares.services.run_collection()`.
7. The panel re-renders itself or the affected row with updated job state.

The POST target is the existing TAP Web panel endpoint:

```text
/panel/<panel-slug>--<panel-entity-id>/
```

Example form shape:

```html
<form hx-post="/panel/<panel-slug>--<panel-entity-id>/"
      hx-target="#cares-collectors-panel"
      hx-swap="outerHTML">
  <input type="hidden" name="action" value="run_collector">
  <input type="hidden" name="collector_entity_id" value="<collector-entity-id>">
  <button type="submit">Run</button>
</form>
```

This is intentionally a v0 Administrivia-surface adapter, not a general external API. The HTMX handler must not contain collector execution semantics beyond request validation, message shaping, and invoking the CARES service. It must not bypass the service layer for node creation, edge creation, task enqueueing, or concurrency checks.

Because bespoke HTMX POST handlers can become scattered management chokepoints, this path should be revisited once TAP invests more heavily in `tap_api` as the canonical external request surface. See [API Trigger Surface](#api-trigger-surface).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-administrivia-htmx-trigger-1 | Panel POST Surface | Implemented | v0 manual collector execution is triggered by HTMX POST to a TAP Web panel endpoint. | |
| req-tap-cares-administrivia-htmx-trigger-2 | handle_post Dispatch | Implemented | The CARES Administrivia panel type handles POSTs through `handle_post(panel, request)`. | |
| req-tap-cares-administrivia-htmx-trigger-3 | Action Validated | Implemented | The handler validates the requested action and collector entity ID before calling services. | |
| req-tap-cares-administrivia-htmx-trigger-4 | Service Layer Only | Implemented | The handler calls `run_collection()` and does not create nodes, edges, jobs, or tasks directly. | |
| req-tap-cares-administrivia-htmx-trigger-5 | Fragment Refresh | Implemented | Successful or failed POSTs return a refreshed panel or row fragment with visible state. | |

### Collector Detail Page
----
RID: `req-tap-cares-administrivia-collector-detail`
Status: `Implemented`

The collector detail page shows one collector's metadata, registry health, manual run action, and run history.

URL shape (chosen for v0):

```text
/administrivia/cares/collector?entity_id=<collector_entity_id>
```

TAP Web pages route from `Page.slug` directly; path parameters under a static page slug are not supported by current Page routing. v0 follows the same precedent the KSI Indicator Profile page uses (entity_id via query param). The Administrivia hosted-surface index records the actual route shape.

Required sections:

- collector identity: name, description, entity ID
- registry details: full registry key, source scope, local key, resolution status
- latest run summary
- manual Run button
- run history table

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-administrivia-collector-detail-1 | Single Collector Input | Implemented | Page resolves the collector from a URL-provided `collector_entity_id` or `entity_id`. | |
| req-tap-cares-administrivia-collector-detail-2 | Registry Health Displayed | Implemented | Detail page displays registry key and whether it resolves. | |
| req-tap-cares-administrivia-collector-detail-3 | Manual Run Available | Implemented | Detail page exposes the same human-triggered run action as the homepage. | |
| req-tap-cares-administrivia-collector-detail-4 | Run History Table | Implemented | Detail page lists previous `CollectionJob` nodes for the collector. | |

### Run Observability
----
RID: `req-tap-cares-administrivia-run-observability`
Status: `Implemented`

The collector detail page should make previous collection runs inspectable enough to diagnose first-order failures without leaving the CARES administrivia surface.

Run history columns:

| Column | Source | Notes |
| --- | --- | --- |
| Name | `CollectionJob.name` | Link to object viewer or expanded detail |
| Status | `CollectionJob.status_display` | Display label with raw status available |
| Enqueued | `CollectionJob.enqueued_at` | |
| Started | `CollectionJob.started_at` | |
| Finished | `CollectionJob.finished_at` | |
| Duration | derived from timestamps | Blank while running |
| Task Result ID | `CollectionJob.task_result_id` | Backend-defined string |
| GRIFT Batches | `CollectionJob.grift_batches` | imported/skipped counts and IDs |
| Summary | `CollectionJob.summary` | At-a-glance one-liner for the run (success or failure); collector-authored when set, count-derived fallback on failure. |

v0 does not require a rich log/event stream because that remains backlog work in `spec-tap-cares-collector.md`. The UI should not pretend detailed logs exist until the run-record/log spec exists.

#### Per-run deep dive

The Run column links to a dedicated CARES Run Detail page at slug `/administrivia/cares/run` with query parameter `?entity_id=<CollectionJob entity_id>`. The page renders the full structured event record stored on `CollectionJob.results`:

- Run header — collector name + link to its detail page, status pill, lifecycle timestamps, derived duration, `summary`, task result ID.
- Counts strip — `info` / `warn` / `error` entry counts plus GRIFT imported / skipped batch counts.
- Three structured event sections (Errors, Warnings, Info), each listing every entry with its `code`, `message`, `site` UUIDv7, and an expandable `context` payload (pretty-printed JSON).
- GRIFT batches section listing imported and skipped batch entity IDs.

The deep dive is read-only; running a collector remains the responsibility of the collector_table and collector_detail panels. The page exists so an operator can answer "what specifically went wrong in this run" without leaving the Administrivia surface — particularly useful for collectors like KSI that accumulate every detected error in a single run.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-administrivia-run-observability-1 | Lifecycle Fields Visible | Implemented | Run history displays status and lifecycle timestamps. | |
| req-tap-cares-administrivia-run-observability-2 | Summary Visible | Implemented | Every finished run shows its bounded `summary` text — collector-authored on success ("Imported 46 indicators (rev_pin v0.1.4)"), count-derived or exception-derived on failure. Empty for collectors that don't set one on a successful run. | |
| req-tap-cares-administrivia-run-observability-3 | GRIFT Correlation Visible | Implemented | Imported and skipped GRIFT batch IDs/counts are visible from run history. | |
| req-tap-cares-administrivia-run-observability-4 | Logs Not Invented | Implemented | UI does not invent rich logs before CARES specifies log/event records. | |
| req-tap-cares-administrivia-run-observability-5 | Per-Run Deep-Dive Page | Implemented | Each run history row links to `/administrivia/cares/run?entity_id=<job_uuid>` which renders the full `results["info"]`, `results["warn"]`, `results["error"]` structured events plus per-entry context payloads. Read-only. | Implemented by the `cares_run_detail` panel in `plugins/administrivia/tap_cares/panels/run_detail/`. |

### FedRAMP KSI Collector Path
----
RID: `req-tap-cares-administrivia-ksi-path`
Status: `Implemented`

The first concrete workflow is the ability to open the CARES homepage and manually execute the FedRAMP 20x KSI collector.

This requires:

- a registered collector runner for the KSI catalog collector
- an on-grid `Collector` node for that runner
- the collector table row showing the runner as available
- a Run button for that row
- the run creating a `CollectionJob`
- the job recording success or failure visibly
- any produced GRIFT batches appearing through `CollectionJob.grift_batches`

The KSI collector's source parsing, safety checks, diff, and GRIFT generation remain governed by `spec-tap-cares-v0.md` and the FedRAMP KSI plugin specs. This requirement only defines the Administrivia path for invoking and observing the collector.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-administrivia-ksi-path-1 | KSI Row Visible | Implemented | CARES homepage includes a FedRAMP 20x KSI collector row when the collector node is seeded. | |
| req-tap-cares-administrivia-ksi-path-2 | KSI Runner Available | Implemented | The row reports available when the KSI collector runner is registered. | |
| req-tap-cares-administrivia-ksi-path-3 | KSI Manual Run | Implemented | Pressing Run enqueues the KSI collector through `run_collection()`. | |
| req-tap-cares-administrivia-ksi-path-4 | KSI Job Observable | Implemented | The resulting job status, summary, and GRIFT batch correlation are visible in the CARES administrivia surface. | |

### API Trigger Surface
----
RID: `req-tap-cares-administrivia-api-trigger`
Status: `Backlog`

Manual collector execution should eventually be reachable through a TAP API endpoint rather than only through a bespoke HTMX panel POST.

The reason is architectural, not cosmetic: external requests that trigger operational behavior should converge on `tap_api` so TAP has one chokepoint for authorization, validation, auditing, rate limiting, error shaping, and future machine clients. HTMX may still be used in the browser, but it should call or be backed by the same API contract rather than growing parallel behavior inside individual panel handlers.

Future API shape should be specified before implementation. A possible route family:

```text
POST /api/v1/cares/collectors/{collector_entity_id}/runs
```

The future API endpoint must call the same CARES execution service as the v0 HTMX handler. It must not duplicate collection semantics or bypass service-layer node and edge creation.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-administrivia-api-trigger-1 | Backlog Requirement Exists | Backlog | A future API trigger surface is tracked explicitly. | |
| req-tap-cares-administrivia-api-trigger-2 | API Chokepoint | Backlog | Future externally-triggered collector runs route through `tap_api` or an approved plugin API router. | |
| req-tap-cares-administrivia-api-trigger-3 | Shared Service | Backlog | The API endpoint calls the same CARES execution service used by the Administrivia surface. | |
| req-tap-cares-administrivia-api-trigger-4 | No Duplicate Semantics | Backlog | API and HTMX/browser behavior do not grow separate collector execution logic. | |
| req-tap-cares-administrivia-api-trigger-5 | Management Controls | Backlog | API design accounts for authorization, validation, auditing, error shaping, and rate limiting. | |

## Out Of Scope

- Autonomous collector execution.
- Scheduler administrivia.
- Receiver, emitter, and action administrivia.
- Rich collector log/event records beyond existing `CollectionJob` fields.
- A credential/authenticator management UI.
- General capability enable/disable or feature-flag behavior.

## Future

- Add scheduler status and schedule-triggered run history once CARES scheduler specs land.
- Add receiver, emitter, and action sections to the CARES homepage.
- Define a richer run detail page once status/log/event records are specified.
- Add Administrivia affordances for reviewing GRIFT batches before merge if the collector workflow separates collection and merge in a later phase.
- Replace the raw `collector_registry` scope in the Source Plugin column with the owning plugin's human-readable display name. A first attempt added per-scope display metadata to `ScopedRegistry`; it was backed out in favor of focusing on functional fixes. The durable path is a dedicated TAP-level plugin registry that lets any Administrivia page look up plugin display metadata by slug; that registry doesn't exist yet and should be specified before the column copy changes.
