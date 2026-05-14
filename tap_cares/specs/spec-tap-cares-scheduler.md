# tap-cares Scheduler Specification

## Philosophy

The tap-cares scheduler is TAP's on-grid recurring trigger system.

The scheduler decides when a collector should run. It does not own collector execution. Once a schedule determines that a collector should run, it calls `run_collection(...)` and lets the collector runtime create the `CollectionJob`, create the `HAS_JOB` edge, enqueue the task, and manage the job lifecycle.

Huey is the v0 clock and worker mechanism for evaluating schedules once per minute. TAP schedule nodes remain the source of truth. Huey should not be used as the durable schedule registry, the schedule history, or the audit record.

The v0 scheduler should be deliberately small: UTC cron expressions, collector targets only, no catch-up execution, durable fire records, and one simple overlap guard.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | On-Grid      | Represent schedules and schedule fires as TAP-managed graph objects |
| 2. | Collector-Only | Support recurring collector execution as the first scheduler target |
| 3. | Observable   | Record each evaluated scheduled slot, including skipped runs and detected gaps |
| 4. | Minimal      | Use cron semantics, UTC, minute resolution, and a small field set |
| 5. | Bounded      | Prevent a schedule from piling up overlapping collector runs |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-tap-cares-scheduler-scope | [Scheduler Scope](#scheduler-scope) | Proposed | Defines v0 as collector-only recurring execution |
| req-tap-cares-scheduler-huey | [Huey Minute Tick](#huey-minute-tick) | Proposed | Huey evaluates enabled schedules once per minute |
| req-tap-cares-scheduler-dependencies | [Implementation Dependencies](#implementation-dependencies) | Proposed | Huey must be added as an explicit uv-managed dependency |
| req-tap-cares-scheduler-model | [Schedule Model](#schedule-model) | Proposed | Minimal on-grid schedule node |
| req-tap-cares-scheduler-fire-model | [ScheduleFire Model](#schedulefire-model) | Proposed | Durable record for each evaluated due slot |
| req-tap-cares-scheduler-edges | [Scheduler Edges](#scheduler-edges) | Proposed | Graph relationships between schedules, fires, collectors, and jobs |
| req-tap-cares-scheduler-cron | [Cron Semantics](#cron-semantics) | Proposed | UTC, minute-resolution cron with no catch-up execution |
| req-tap-cares-scheduler-missed-count | [Missed Count](#missed-count) | Proposed | Detect schedule gaps without backfilling work |
| req-tap-cares-scheduler-dedupe | [Slot Dedupe](#slot-dedupe) | Proposed | Prevent duplicate fires for the same schedule minute |
| req-tap-cares-scheduler-concurrency | [Schedule Concurrency](#schedule-concurrency) | Proposed | Per-schedule max active runs |
| req-tap-cares-scheduler-trigger-provenance | [Trigger Provenance](#trigger-provenance) | Proposed | Scheduled collector jobs identify the scheduler trigger that caused them |
| req-tap-cares-scheduler-backlog | [Backlog](#backlog) | Backlog | Deferred scheduler capabilities |

## Scheduler Scope
----
RID: `req-tap-cares-scheduler-scope`
Status: `Proposed`

v0 schedules target collectors only.

A schedule represents a recurring policy that says "run this collector when this cron expression matches." Emitters, receivers, actions, ad hoc run-now requests, and generic capability targets are future work. The model should not paint TAP into a corner, but the v0 implementation and acceptance criteria are collector-specific.

The scheduler is a trigger system. It must not:

- import collector implementation modules directly
- enqueue `run_collector` directly
- create `CollectionJob` rows directly
- create `HAS_JOB` edges directly
- mutate collector output or GRIFT batches

When a schedule fires successfully, it invokes `tap_cares.services.run_collection(...)` for the target `Collector`.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-scheduler-scope-1 | Collector-Only v0 | Proposed | v0 schedules can target `Collector` nodes and no other CARES capability type. | |
| req-tap-cares-scheduler-scope-2 | Uses run_collection | Proposed | Successful scheduled execution invokes `run_collection(...)`; the scheduler does not reach behind that boundary. | See `spec-tap-cares-collector.md` `req-tap-cares-collector-run-collection`. |
| req-tap-cares-scheduler-scope-3 | No Direct Task Enqueue | Proposed | The scheduler never calls `run_collector.enqueue(...)` directly. | |

## Huey Minute Tick
----
RID: `req-tap-cares-scheduler-huey`
Status: `Proposed`

Huey provides the v0 recurring process that wakes once per minute and evaluates schedules.

The Huey task should:

1. Compute the current UTC minute slot by truncating wall-clock time to minute precision.
2. Find enabled `Schedule` nodes.
3. Evaluate each schedule's cron expression against the current slot.
4. For matching schedules, claim the slot, create a `ScheduleFire`, apply the overlap guard, and call `run_collection(...)` when allowed.

Huey is not the schedule database. Schedule state, schedule targets, fire history, missed counts, and links to collection jobs live on the TAP grid.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-scheduler-huey-1 | Minute Tick | Proposed | Huey runs the scheduler evaluation task once per minute. | No per-second evaluation in v0. |
| req-tap-cares-scheduler-huey-2 | UTC Slot | Proposed | The scheduler evaluates an exact UTC minute slot, not arbitrary sub-minute wall-clock time. | |
| req-tap-cares-scheduler-huey-3 | TAP Owns State | Proposed | Huey is only the clock/worker; durable scheduler state is stored in TAP graph objects. | |

## Implementation Dependencies
----
RID: `req-tap-cares-scheduler-dependencies`
Status: `Proposed`

The scheduler implementation requires adding Huey as an explicit uv-managed Python dependency.

Because `tap_cares` is a first-party TAP app, Huey may be added to the root project dependency set unless the uv workspace/plugin-dependency work lands first. If the workspace pattern lands before scheduler implementation, the scheduler should use that pattern as the first real proving ground for installing the dependency cleanly while preserving the eventual ability to separate plugin and app dependency ownership.

This requirement is about dependency management only. It does not change the runtime rule that Huey is the clock/worker and TAP graph objects are the durable schedule source of truth.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-scheduler-dependencies-1 | Huey Dependency | Proposed | Scheduler implementation adds Huey through uv rather than relying on an undeclared transitive import. | |
| req-tap-cares-scheduler-dependencies-2 | Workspace-Compatible | Proposed | If the uv workspace/plugin-dependency pattern lands first, scheduler dependency installation follows that pattern. | Cross-reference `tap_plugins/specs/spec-plugin-architecture.md` `req-plugin-arch-python-deps`. |
| req-tap-cares-scheduler-dependencies-3 | State Boundary Unchanged | Proposed | Adding Huey as a dependency does not make Huey the durable schedule store. | |

## Schedule Model
----
RID: `req-tap-cares-scheduler-model`
Status: `Proposed`

`Schedule` is the on-grid policy node for recurring collector execution.

`Schedule` must be implemented as a standard TAP-managed `BaseModel` node. It should be `INTERNAL_ONLY` unless and until TAP defines a public schedule creation API. Schedule writes should route through a dedicated tap-cares scheduler service, not direct ORM writes or generic public CRUD.

Every `Schedule` has a human-readable `name` and plain-text `description`.

Minimal v0 fields:

| Field | Type | Notes |
| --- | --- | --- |
| `name` | string | Required human-readable name |
| `description` | string | Plain-text explanation of what this schedule does |
| `enabled` | bool | Disabled schedules are ignored and do not accumulate missed runs |
| `cron_expression` | string | Five-field cron expression interpreted in UTC at minute resolution |
| `last_scheduled_for` | datetime/null | Last UTC cron slot the scheduler processed for this schedule |
| `max_active_runs` | positive integer | Maximum active runs allowed for this schedule; default `1` |

`last_scheduled_for` is a processed-slot cursor, not a prediction. It exists to make the per-minute scheduler idempotent and to detect gaps. The scheduler should set it to the current slot when it processes that slot, whether the resulting fire is triggered, skipped, or failed.

`max_active_runs` is per schedule in v0. It is not a collector-wide concurrency limit.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-scheduler-model-1 | Standard BaseModel | Proposed | `Schedule` is a TAP-managed `BaseModel` node with a backing `Entity`. | |
| req-tap-cares-scheduler-model-2 | Name And Description | Proposed | `Schedule` has required `name` and `description` fields. | |
| req-tap-cares-scheduler-model-3 | Minimal Fields | Proposed | v0 `Schedule` exposes only `name`, `description`, `enabled`, `cron_expression`, `last_scheduled_for`, and `max_active_runs`. | |
| req-tap-cares-scheduler-model-4 | Processed-Slot Cursor | Proposed | `last_scheduled_for` records the most recent processed cron slot, not the most recent task completion time. | |
| req-tap-cares-scheduler-model-5 | Default Overlap Guard | Proposed | `max_active_runs` defaults to `1` and must be greater than or equal to `1`. | |

## ScheduleFire Model
----
RID: `req-tap-cares-scheduler-fire-model`
Status: `Proposed`

`ScheduleFire` is the on-grid execution-decision record for one evaluated due slot of a schedule.

A `ScheduleFire` is not the collector run. The collector run is still represented by `CollectionJob`. `ScheduleFire` records the scheduler's decision for a due slot and links to a `CollectionJob` only when the schedule actually triggers collection.

Every `ScheduleFire` has a human-readable `name` and plain-text `description`.

Minimal v0 fields:

| Field | Type | Notes |
| --- | --- | --- |
| `name` | string | Human-readable fire name, usually derived from schedule name and slot |
| `description` | string | Plain-text explanation of the scheduled decision |
| `status` | enum | `triggered`, `skipped`, or `failed` |
| `scheduled_for` | datetime | UTC cron slot being evaluated |
| `fired_at` | datetime/null | Actual wall-clock time when the scheduler evaluated the slot |
| `missed_count` | integer | Number of matching cron slots skipped before this slot; default `0` |
| `skip_reason` | string | Machine-readable reason when `status = skipped` |
| `error_summary` | string | Bounded failure summary when the scheduler itself fails before triggering collection |

`ScheduleFire.status` describes scheduler behavior only:

- `triggered`: the scheduler called `run_collection(...)` and linked the resulting `CollectionJob`.
- `skipped`: the slot was due but no collector run was started, for example because `max_active_runs` was already reached.
- `failed`: the scheduler failed while processing the slot before it could produce a normal triggered or skipped result.

Collector success or failure is recorded on `CollectionJob.status`, not copied back into `ScheduleFire.status`.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-scheduler-fire-model-1 | Standard BaseModel | Proposed | `ScheduleFire` is a TAP-managed `BaseModel` node with a backing `Entity`. | |
| req-tap-cares-scheduler-fire-model-2 | Name And Description | Proposed | `ScheduleFire` has required `name` and `description` fields. | |
| req-tap-cares-scheduler-fire-model-3 | Decision Record | Proposed | Each `ScheduleFire` records the scheduler decision for one due cron slot. | |
| req-tap-cares-scheduler-fire-model-4 | Scheduler Status Only | Proposed | `ScheduleFire.status` records scheduler decision state, not the terminal collector job state. | |
| req-tap-cares-scheduler-fire-model-5 | Missed Count Field | Proposed | `ScheduleFire` has an integer `missed_count` defaulting to `0`. | |

## Scheduler Edges
----
RID: `req-tap-cares-scheduler-edges`
Status: `Proposed`

The v0 scheduler graph uses these edges:

```text
Schedule --TARGETS--> Collector
Schedule --HAS_FIRE--> ScheduleFire
ScheduleFire --TRIGGERED_JOB--> CollectionJob
```

`TARGETS` ties the schedule policy to the collector capability it can run.

`HAS_FIRE` ties a durable fire/decision record to the schedule that produced it.

`TRIGGERED_JOB` exists only for fires whose status is `triggered`. Skipped or failed fires do not have a `TRIGGERED_JOB` edge because no collection job was started.

The existing collector edge remains unchanged:

```text
Collector --HAS_JOB--> CollectionJob
```

This means a scheduled collection job is reachable in two useful ways:

```text
Schedule --HAS_FIRE--> ScheduleFire --TRIGGERED_JOB--> CollectionJob
Collector --HAS_JOB--> CollectionJob
```

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-scheduler-edges-1 | TARGETS Edge | Proposed | tap-cares declares `TARGETS` from `Schedule` to `Collector` for v0. | |
| req-tap-cares-scheduler-edges-2 | HAS_FIRE Edge | Proposed | tap-cares declares `HAS_FIRE` from `Schedule` to `ScheduleFire`. | |
| req-tap-cares-scheduler-edges-3 | TRIGGERED_JOB Edge | Proposed | tap-cares declares `TRIGGERED_JOB` from `ScheduleFire` to `CollectionJob`. | Only present for triggered fires. |
| req-tap-cares-scheduler-edges-4 | HAS_JOB Preserved | Proposed | Scheduled collection still creates the existing `Collector --HAS_JOB--> CollectionJob` edge through `run_collection(...)`. | |

## Cron Semantics
----
RID: `req-tap-cares-scheduler-cron`
Status: `Proposed`

v0 schedules use five-field cron expressions:

```text
minute hour day-of-month month day-of-week
```

Cron expressions are interpreted in UTC. The scheduler evaluates only minute-level slots. Sub-minute precision, named time zones, daylight-saving-time policy, seconds fields, calendars, and interval-specific fields are out of scope for v0.

There is no catch-up execution in v0. If Huey, the app, or the host is down when a schedule would have matched, TAP does not enqueue historical collector runs for those missed slots.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-scheduler-cron-1 | Five-Field Cron | Proposed | `cron_expression` stores a five-field cron expression. | |
| req-tap-cares-scheduler-cron-2 | UTC Only | Proposed | Cron matching is interpreted in UTC in v0. | |
| req-tap-cares-scheduler-cron-3 | Minute Resolution | Proposed | The scheduler evaluates minute slots only; seconds are ignored. | |
| req-tap-cares-scheduler-cron-4 | No Catch-Up Execution | Proposed | Missed slots are not backfilled or executed later in v0. | |

## Missed Count
----
RID: `req-tap-cares-scheduler-missed-count`
Status: `Proposed`

The scheduler detects gaps by comparing a schedule's `last_scheduled_for` cursor to the current matching slot.

When the current UTC minute matches a schedule's cron expression:

1. If `last_scheduled_for` is null, set `missed_count = 0`.
2. Otherwise, count matching cron slots after `last_scheduled_for` and before the current slot.
3. Store that count on the current slot's `ScheduleFire.missed_count`.
4. Continue processing only the current slot.

Example for an every-minute schedule:

```text
last_scheduled_for = 12:00
current slot       = 12:05
missed slots       = 12:01, 12:02, 12:03, 12:04
missed_count       = 4
```

The fire for `12:05` proceeds normally after this accounting. It may trigger a collection job, or it may be skipped because `max_active_runs` has been reached.

Disabled schedules do not accumulate missed runs. Missed counts are observed only when an enabled schedule next matches.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-scheduler-missed-count-1 | Cursor Comparison | Proposed | Missed slots are detected by comparing `last_scheduled_for` to the current matching cron slot. | |
| req-tap-cares-scheduler-missed-count-2 | Count Only | Proposed | Missed slots increment `missed_count`; they do not create backfilled collection jobs. | |
| req-tap-cares-scheduler-missed-count-3 | Current Fire Carries Count | Proposed | The current slot's `ScheduleFire` stores the missed count summary. | |
| req-tap-cares-scheduler-missed-count-4 | Disabled Ignored | Proposed | Disabled schedules do not accumulate or later report missed counts for disabled periods. | |

## Slot Dedupe
----
RID: `req-tap-cares-scheduler-dedupe`
Status: `Proposed`

The scheduler must process a schedule/slot pair at most once.

Before creating a `ScheduleFire`, the scheduler checks whether `Schedule.last_scheduled_for` already equals the current slot. If it does, the tick is a duplicate and does nothing.

If the current slot should be processed, the scheduler claims the slot by setting `last_scheduled_for = current_slot` in the same transactional unit as `ScheduleFire` creation. Duplicate Huey ticks, worker retries, process restarts, and overlapping scheduler workers must not create duplicate fire records for the same schedule/slot pair.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-scheduler-dedupe-1 | Duplicate Slot No-Op | Proposed | If `last_scheduled_for == current_slot`, the scheduler does not create a `ScheduleFire`. | |
| req-tap-cares-scheduler-dedupe-2 | Atomic Claim | Proposed | Claiming `last_scheduled_for` and creating the `ScheduleFire` happen atomically. | |
| req-tap-cares-scheduler-dedupe-3 | One Fire Per Slot | Proposed | A schedule cannot produce more than one `ScheduleFire` for the same `scheduled_for` slot. | Enforce with service logic and, if practical, a DB uniqueness constraint. |

## Schedule Concurrency
----
RID: `req-tap-cares-scheduler-concurrency`
Status: `Proposed`

Each schedule limits its own active scheduled runs with `max_active_runs`.

For v0, active runs are `CollectionJob` nodes linked from this schedule through:

```text
Schedule --HAS_FIRE--> ScheduleFire --TRIGGERED_JOB--> CollectionJob
```

where `CollectionJob.status` is `READY` or `RUNNING`.

If the active count is greater than or equal to `Schedule.max_active_runs`, the scheduler creates a `ScheduleFire` for the current slot with:

```text
status = skipped
skip_reason = max_active_runs
```

and does not call `run_collection(...)`.

This policy is intentionally similar to production systems that support "forbid overlap" behavior. v0 does not replace or cancel active runs.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-scheduler-concurrency-1 | Per-Schedule Limit | Proposed | `max_active_runs` applies to runs triggered by the same schedule, not all runs of the target collector. | |
| req-tap-cares-scheduler-concurrency-2 | Active Statuses | Proposed | `READY` and `RUNNING` collection jobs count as active for scheduler overlap checks. | |
| req-tap-cares-scheduler-concurrency-3 | Skipped Fire | Proposed | A due slot blocked by active-run limit creates a skipped `ScheduleFire` with `skip_reason = max_active_runs`. | |
| req-tap-cares-scheduler-concurrency-4 | No Replace In v0 | Proposed | v0 does not cancel, replace, or interrupt already-active collection jobs. | |

## Trigger Provenance
----
RID: `req-tap-cares-scheduler-trigger-provenance`
Status: `Proposed`

Scheduled collector execution must preserve why the collector ran.

`run_collection(...)` should accept trigger metadata so manual runs, scheduled runs, future API runs, and other explicit triggers use the same collector execution path while preserving their origin.

Proposed signature shape:

```python
def run_collection(
    collector: Collector,
    *,
    caller_context: CallerContext | None = None,
    trigger_source: str,
    trigger_description: str,
) -> CollectionJob:
    ...
```

For a scheduled run:

```text
trigger_source = "scheduler"
trigger_description = "Scheduled run: <schedule.name>"
```

The durable kickoff state should preserve this metadata on the created `CollectionJob` or on an immediately linked trigger/run context node. The exact storage location may be finalized during implementation, but the metadata must be queryable with the collection job and should not exist only as transient task arguments.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-scheduler-trigger-provenance-1 | Trigger Metadata Accepted | Proposed | `run_collection(...)` accepts `trigger_source` and `trigger_description` keyword arguments. | |
| req-tap-cares-scheduler-trigger-provenance-2 | Scheduler Values | Proposed | Scheduled runs use `trigger_source = "scheduler"` and a description naming the schedule. | |
| req-tap-cares-scheduler-trigger-provenance-3 | Durable Provenance | Proposed | Trigger metadata is durably queryable with the resulting collection job, not only passed to the task. | |
| req-tap-cares-scheduler-trigger-provenance-4 | Caller Context Separate | Proposed | `caller_context` remains the authority/user context; trigger metadata describes the mechanism and human-readable reason. | |

## Backlog
----
RID: `req-tap-cares-scheduler-backlog`
Status: `Backlog`

The following are intentionally deferred:

- schedule targets beyond collectors
- run-now trigger nodes that mediate manual execution
- catch-up or backfill execution for missed slots
- time zone support beyond UTC
- second-level cron support
- stale active run timeout, stuck-job sweep, or administrator resolution flow
- replace-running or cancel-running overlap policy
- collector-wide concurrency limits
- schedule parameter payloads and per-run input overrides
- schedule creation/update API design
- schedule-fire retention and pruning
- richer scheduler tick health metrics

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-scheduler-backlog-1 | Deferred Work Named | Backlog | Non-v0 scheduler capabilities are explicitly tracked as backlog rather than being partially specified. | |
