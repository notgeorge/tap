# tap-cares Administration Specification

## Philosophy

tap-cares administration gives humans a clear control surface for observing and operating CARES capabilities. The first target is collectors: users should be able to see which collectors exist, whether their runner code is available, what happened during recent runs, and manually execute the FedRAMP 20x KSI collector from a TAP-native page.

The canonical CARES runtime concepts remain owned by `tap_cares`: `Collector`, `CollectionJob`, `HAS_JOB`, collector registry resolution, Django Tasks execution, and GRIFT batch correlation. The initial web implementation lives in the Administrivia plugin under `plugins/administrivia/tap_cares/` because Administrivia is TAP's first-party administrative UI host.

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
| req-tap-cares-admin-ownership | [Administrative Ownership](#administrative-ownership) | Proposed | CARES owns semantics; Administrivia hosts the UI implementation |
| req-tap-cares-admin-homepage | [CARES Homepage](#cares-homepage) | Proposed | Overview page for CARES subsystem status, starting with collectors |
| req-tap-cares-admin-collector-table | [Collector Table](#collector-table) | Proposed | Table listing available collectors and their latest run state |
| req-tap-cares-admin-manual-run | [Manual Collector Execution](#manual-collector-execution) | Proposed | Human-triggered run action calls `run_collection()` |
| req-tap-cares-admin-htmx-trigger | [HTMX Trigger Surface](#htmx-trigger-surface) | Proposed | v0 browser POST path for manual collector execution |
| req-tap-cares-admin-collector-detail | [Collector Detail Page](#collector-detail-page) | Proposed | Collector-specific page with metadata and run history |
| req-tap-cares-admin-run-observability | [Run Observability](#run-observability) | Proposed | Display timestamps, status, errors, task IDs, and GRIFT batch correlation |
| req-tap-cares-admin-ksi-path | [FedRAMP KSI Collector Path](#fedramp-ksi-collector-path) | Proposed | Initial happy path for executing the KSI collector from the homepage |
| req-tap-cares-admin-api-trigger | [API Trigger Surface](#api-trigger-surface) | Backlog | Future API chokepoint for collector execution requests |

### Administrative Ownership
----
RID: `req-tap-cares-admin-ownership`
Status: `Proposed`

The CARES administration requirements live in `tap_cares/specs/` because the behavior being administered belongs to `tap_cares`.

The initial page, panel, template, static asset, and optional view code lives in:

```text
plugins/administrivia/tap_cares/
```

Administrivia should reference this spec from its hosted surface index rather than duplicating these CARES requirements.

The admin UI must use existing CARES services and models:

- `Collector` for on-grid collector capability rows
- `CollectionJob` for run history
- `HAS_JOB` for collector-to-run provenance
- `tap_cares.registry.get_collector()` or equivalent registry inspection for runner availability
- `tap_cares.services.run_collection()` for manual execution
- `CollectionJob.grift_batches` for imported/skipped GRIFT batch correlation

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-admin-ownership-1 | Spec Lives With CARES | Proposed | CARES administrative behavior is specified under `tap_cares/specs/`. | |
| req-tap-cares-admin-ownership-2 | UI Code In Administrivia | Proposed | Initial implementation code lives under `plugins/administrivia/tap_cares/`. | |
| req-tap-cares-admin-ownership-3 | Service Layer Execution | Proposed | Manual execution routes through `tap_cares.services.run_collection()`. | |
| req-tap-cares-admin-ownership-4 | No New Execution Path | Proposed | The admin UI does not bypass collector registry, Django Tasks, CollectionJob, or GRIFT import contracts. | |

### CARES Homepage
----
RID: `req-tap-cares-admin-homepage`
Status: `Proposed`

The CARES homepage is the top-level administrative page for CARES subsystem status.

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
| req-tap-cares-admin-homepage-1 | Route Exists | Proposed | CARES homepage is reachable at `/administrivia/cares`. | |
| req-tap-cares-admin-homepage-2 | Collector Focus | Proposed | v0 homepage shows collector status before other CARES subsystems exist. | |
| req-tap-cares-admin-homepage-3 | Summary Strip | Proposed | Homepage includes aggregate collector health and run-state summary values. | |
| req-tap-cares-admin-homepage-4 | Future Subsystems Reserved | Proposed | Layout leaves room for future receivers, emitters, actions, and schedules. | |

### Collector Table
----
RID: `req-tap-cares-admin-collector-table`
Status: `Proposed`

The collectors table lists all on-grid `Collector` nodes and summarizes their execution readiness and recent run outcome.

Initial columns:

| Column | Source | Notes |
| --- | --- | --- |
| Name | `Collector.name` | Row opens collector detail page |
| Source Plugin | inferred from `collector_registry` scope | For `plugins.fedramp_20x_ksi.collectors:ksi-catalog`, show FedRAMP 20x KSI where possible |
| Description | `Collector.description` | Plain text |
| Registry Key | `Collector.collector_registry` | Full `scope:key`, useful for debugging |
| Availability | registry lookup | `available` or `missing runner` |
| Run State | latest `CollectionJob.status` | `idle`, `running`, or current status |
| Last Run | latest finished `CollectionJob.status` | `successful`, `failed`, or `never run` |
| Last Run At | latest finished `CollectionJob.finished_at` | Empty for never run |
| Last Error | latest failed `CollectionJob.error_summary` | Short bounded error |
| Action | admin POST | Manual Run button |

The table should avoid implying that registry availability and last run outcome are the same thing. A collector can be available even if its last run failed, and a collector can have a historical successful run while its current runner code is missing.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-admin-collector-table-1 | All Collectors Listed | Proposed | Table includes every on-grid `Collector` node. | |
| req-tap-cares-admin-collector-table-2 | Availability Distinct | Proposed | Registry resolution is displayed separately from run outcome. | |
| req-tap-cares-admin-collector-table-3 | Latest Job Summarized | Proposed | Table displays latest run state, last finished run, timestamp, and bounded error summary. | |
| req-tap-cares-admin-collector-table-4 | Row Drilldown | Proposed | Clicking a collector row opens the collector-specific admin page. | |

### Manual Collector Execution
----
RID: `req-tap-cares-admin-manual-run`
Status: `Proposed`

The CARES admin UI provides a manual Run action for a collector.

The Run action is a human-triggered POST. It must:

1. Resolve the target `Collector` by entity ID.
2. Verify that the collector's registry key resolves to a registered runner.
3. Call `tap_cares.services.run_collection(collector)`.
4. Return or display the created `CollectionJob`.
5. Refresh the homepage row or navigate to the collector detail page.

The Run button may guard against obvious duplicate manual runs, such as a collector already showing a `RUNNING` job, but the general collector concurrency policy is Backlog until the enqueue path and scheduler behavior are specified together. The future service-layer concurrency policy is tracked in `tap_cares/specs/spec-tap-cares-collector.md` (`req-tap-cares-collector-concurrency`).

The UI handler must not create `CollectionJob` nodes or `HAS_JOB` edges directly. It is an adapter from a browser POST into the CARES execution service. `run_collection()` owns job creation, edge creation, task enqueueing, and concurrency enforcement, and that service must route TAP-managed node and edge creation through the grid service layer.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-admin-manual-run-1 | POST Only | Proposed | Manual execution uses a POST action, not a GET link. | |
| req-tap-cares-admin-manual-run-2 | Registry Checked | Proposed | UI checks runner availability before enqueuing and surfaces missing runner errors. | |
| req-tap-cares-admin-manual-run-3 | Uses run_collection | Proposed | Manual execution calls `tap_cares.services.run_collection()`. | |
| req-tap-cares-admin-manual-run-4 | Job Visible | Proposed | The resulting `CollectionJob` is visible after the action completes. | |
| req-tap-cares-admin-manual-run-5 | Duplicate Running Guard | Proposed | UI may prevent or warn against starting a second manual run when the collector already has a `RUNNING` job. | Full concurrency policy is Backlog; cross-ref `req-tap-cares-collector-concurrency`. |
| req-tap-cares-admin-manual-run-6 | No Direct Node Creation In UI | Proposed | The UI handler does not directly create `CollectionJob` nodes or `HAS_JOB` edges. | Creation belongs to CARES services and the grid service layer. |

### HTMX Trigger Surface
----
RID: `req-tap-cares-admin-htmx-trigger`
Status: `Proposed`

The initial browser trigger surface for manual collector execution is an HTMX POST handled by an Administrivia CARES panel type.

The preferred v0 flow:

1. The CARES homepage hosts a collector administration panel.
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

This is intentionally a v0 administrative UI adapter, not a general external API. The HTMX handler must not contain collector execution semantics beyond request validation, message shaping, and invoking the CARES service. It must not bypass the service layer for node creation, edge creation, task enqueueing, or concurrency checks.

Because bespoke HTMX POST handlers can become scattered management chokepoints, this path should be revisited once TAP invests more heavily in `tap_api` as the canonical external request surface. See [API Trigger Surface](#api-trigger-surface).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-admin-htmx-trigger-1 | Panel POST Surface | Proposed | v0 manual collector execution is triggered by HTMX POST to a TAP Web panel endpoint. | |
| req-tap-cares-admin-htmx-trigger-2 | handle_post Dispatch | Proposed | The CARES admin panel type handles POSTs through `handle_post(panel, request)`. | |
| req-tap-cares-admin-htmx-trigger-3 | Action Validated | Proposed | The handler validates the requested action and collector entity ID before calling services. | |
| req-tap-cares-admin-htmx-trigger-4 | Service Layer Only | Proposed | The handler calls `run_collection()` and does not create nodes, edges, jobs, or tasks directly. | |
| req-tap-cares-admin-htmx-trigger-5 | Fragment Refresh | Proposed | Successful or failed POSTs return a refreshed panel or row fragment with visible state. | |

### Collector Detail Page
----
RID: `req-tap-cares-admin-collector-detail`
Status: `Proposed`

The collector detail page shows one collector's metadata, registry health, manual run action, and run history.

Preferred URL shape:

```text
/administrivia/cares/collector/<collector_entity_id>
```

If current TAP Web routing cannot represent this route without new route support, v0 may use query parameters:

```text
/administrivia/cares/collector?entity_id=<collector_entity_id>
```

The chosen route must be documented in Administrivia's hosted surface index when implemented.

Required sections:

- collector identity: name, description, entity ID
- registry details: full registry key, source scope, local key, resolution status
- latest run summary
- manual Run button
- run history table

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-admin-collector-detail-1 | Single Collector Input | Proposed | Page resolves the collector from a URL-provided `collector_entity_id` or `entity_id`. | |
| req-tap-cares-admin-collector-detail-2 | Registry Health Displayed | Proposed | Detail page displays registry key and whether it resolves. | |
| req-tap-cares-admin-collector-detail-3 | Manual Run Available | Proposed | Detail page exposes the same human-triggered run action as the homepage. | |
| req-tap-cares-admin-collector-detail-4 | Run History Table | Proposed | Detail page lists previous `CollectionJob` nodes for the collector. | |

### Run Observability
----
RID: `req-tap-cares-admin-run-observability`
Status: `Proposed`

The collector detail page should make previous collection runs inspectable enough to diagnose first-order failures without leaving the CARES admin surface.

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
| Error Summary | `CollectionJob.error_summary` | Only populated on failure |

v0 does not require a rich log/event stream because that remains backlog work in `spec-tap-cares-collector.md`. The UI should not pretend detailed logs exist until the run-record/log spec exists.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-admin-run-observability-1 | Lifecycle Fields Visible | Proposed | Run history displays status and lifecycle timestamps. | |
| req-tap-cares-admin-run-observability-2 | Error Summary Visible | Proposed | Failed runs show bounded `error_summary` text. | |
| req-tap-cares-admin-run-observability-3 | GRIFT Correlation Visible | Proposed | Imported and skipped GRIFT batch IDs/counts are visible from run history. | |
| req-tap-cares-admin-run-observability-4 | Logs Not Invented | Proposed | UI does not invent rich logs before CARES specifies log/event records. | |

### FedRAMP KSI Collector Path
----
RID: `req-tap-cares-admin-ksi-path`
Status: `Proposed`

The first concrete workflow is the ability to open the CARES homepage and manually execute the FedRAMP 20x KSI collector.

This requires:

- a registered collector runner for the KSI catalog collector
- an on-grid `Collector` node for that runner
- the collector table row showing the runner as available
- a Run button for that row
- the run creating a `CollectionJob`
- the job recording success or failure visibly
- any produced GRIFT batches appearing through `CollectionJob.grift_batches`

The KSI collector's source parsing, safety checks, diff, and GRIFT generation remain governed by `spec-tap-cares-v0.md` and the FedRAMP KSI plugin specs. This requirement only defines the admin path for invoking and observing the collector.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-admin-ksi-path-1 | KSI Row Visible | Proposed | CARES homepage includes a FedRAMP 20x KSI collector row when the collector node is seeded. | |
| req-tap-cares-admin-ksi-path-2 | KSI Runner Available | Proposed | The row reports available when the KSI collector runner is registered. | |
| req-tap-cares-admin-ksi-path-3 | KSI Manual Run | Proposed | Pressing Run enqueues the KSI collector through `run_collection()`. | |
| req-tap-cares-admin-ksi-path-4 | KSI Job Observable | Proposed | The resulting job status, error summary, and GRIFT batch correlation are visible in CARES admin. | |

### API Trigger Surface
----
RID: `req-tap-cares-admin-api-trigger`
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
| req-tap-cares-admin-api-trigger-1 | Backlog Requirement Exists | Backlog | A future API trigger surface is tracked explicitly. | |
| req-tap-cares-admin-api-trigger-2 | API Chokepoint | Backlog | Future externally-triggered collector runs route through `tap_api` or an approved plugin API router. | |
| req-tap-cares-admin-api-trigger-3 | Shared Service | Backlog | The API endpoint calls the same CARES execution service used by the admin UI. | |
| req-tap-cares-admin-api-trigger-4 | No Duplicate Semantics | Backlog | API and HTMX/browser behavior do not grow separate collector execution logic. | |
| req-tap-cares-admin-api-trigger-5 | Management Controls | Backlog | API design accounts for authorization, validation, auditing, error shaping, and rate limiting. | |

## Out Of Scope

- Autonomous collector execution.
- Scheduler administration.
- Receiver, emitter, and action administration.
- Rich collector log/event records beyond existing `CollectionJob` fields.
- A credential/authenticator management UI.
- General capability enable/disable or feature-flag behavior.

## Future

- Add scheduler status and schedule-triggered run history once CARES scheduler specs land.
- Add receiver, emitter, and action sections to the CARES homepage.
- Define a richer run detail page once status/log/event records are specified.
- Add admin affordances for reviewing GRIFT batches before merge if the collector workflow separates collection and merge in a later phase.
