# tap-cares Collector Specification

## Philosophy

Collectors are tap-cares capabilities that gather data from a source and prepare it for TAP-owned processing. The collector system starts with two deliberately small foundations:

- an on-grid `Collector` node that represents the capability TAP can inspect, schedule, and manage
- a `collector_registry` that maps the collector node's stable registry key to trusted Python code registered at startup

Status messages are intentionally deferred to later requirements. This spec slice defines the collector model-to-module mapping, the minimal task execution boundary needed to host collector modules, the approved GRIFT import path for collection results, and the on-grid `CollectionJob` execution record.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | On-Grid      | Represent collector capabilities as TAP-managed grid nodes       |
| 2. | Registered   | Resolve executable collector code through a scoped registry      |
| 3. | Deterministic | Require fully qualified registry keys for persisted collectors  |
| 4. | Safe Shape   | Prevent grid data from becoming an arbitrary code loading path   |
| 5. | Conventional | Follow standard TAP `BaseModel` conventions and model-building skill guidance |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-tap-cares-collector-model | [Collector Model](#collector-model) | Implemented | On-grid TAP-managed collector node |
| req-tap-cares-collector-registry | [Collector Registry](#collector-registry) | Implemented | Scoped registry mapping collector keys to registered runner code |
| req-tap-cares-collector-module-class | [Collector Module Class](#collector-module-class) | Implemented | Registered collector classes instantiated by tap-cares |
| req-tap-cares-collector-config | [CollectorConfig](#collectorconfig) | Implemented | JSON-safe collector configuration object |
| req-tap-cares-collector-task-execution | [Collector Task Execution](#collector-task-execution) | Implemented | Django Tasks worker-process execution boundary |
| req-tap-cares-collector-read-boundary | [Collector Read Boundary](#collector-read-boundary) | Implemented | Collector modules read through approved search/read surfaces and only submit result mutations through GRIFT import |
| req-tap-cares-collector-grift-import | [Collector GRIFT Import Surface](#collector-grift-import-surface) | Implemented | Collector result grid mutations route through the GRIFT importer |
| req-tap-cares-collector-job-model | [CollectionJob Model](#collectionjob-model) | Implemented | On-grid execution record for one collector run |
| req-tap-cares-collector-job-edge | [Collector HAS_JOB Edge](#collector-has_job-edge) | Implemented | Graph relationship from Collector root node to its CollectionJob nodes |
| req-tap-cares-collector-job-lifecycle | [CollectionJob Lifecycle Status](#collectionjob-lifecycle-status) | Implemented | Job status reflects Django Tasks lifecycle states |
| req-tap-cares-collector-job-logs | [Collection Job Status Messages And Logs](#collection-job-status-messages-and-logs) | Backlog | Deferred richer in-process status/log/event stream |
| req-tap-cares-collector-strict-isolation | [Strict Collector Isolation](#strict-collector-isolation) | Backlog | Future stronger isolation for untrusted or high-risk collector execution |

## Collector Model
----
RID: `req-tap-cares-collector-model`
Status: `Implemented`

`Collector` is the grid-side representation of a tap-cares collector capability.

`Collector` must be implemented as a standard TAP-managed `BaseModel` node using the model-building skill at `tap_grid/skills/add-model/SKILL.md`. The model should follow ordinary TAP model conventions rather than re-specifying boilerplate in this requirement. Those conventions include entity-spine backing, `ENTITY_TYPE`, display metadata, `FIELD_CRUD_SCHEMA`, `FIELD_VALIDATION_SCHEMA`, `CREATE_REQUIRED`, `get_name()`, service-layer write compatibility, history behavior, and tests for creation, validation, display projection, and dimensions.

The collector node must not store arbitrary filesystem paths, dynamic import paths, or executable code. It stores a fully qualified registry key. The registry is the controlled intermediary between grid data and executable code.

Collector-specific model requirements:

- `Collector` has a human-readable `name`.
- `Collector` has a plain-text `description`.
- `Collector` has a top-level `collector_registry` field.
- `collector_registry` stores the fully qualified registry key used to resolve the collector's registered runner.
- Persisted `collector_registry` values must use `scope:key` format.
- Persisted collector nodes must not use short keys.
- Persisted `collector_registry` values are unique per grid in v0; two Collector nodes may not share the same registry key while per-instance configuration is deferred.
- v0 ships only `name`, `description`, and `collector_registry`. Per-instance configuration is deferred (see [CollectorConfig](#collectorconfig)); the first concrete collector (FedRAMP 20x KSI) hardcodes its behavior in the registered class.
- The v0 default dimension is `{"tap_cares": "collector"}`.
- Instance-derived collector dimensions are deferred until TAP's dimension conventions are revisited.

The scheduler will use `Collector` nodes to determine which collector capability to execute. The scheduler relationship and execution behavior are out of scope for this requirement.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-collector-model-1 | Standard BaseModel | Implemented | `Collector` is specified as a normal TAP-managed `BaseModel` node implemented through the model-building skill conventions. | |
| req-tap-cares-collector-model-2 | Registry Field | Implemented | `Collector` has a top-level `collector_registry` field that stores the registered collector runner key. | |
| req-tap-cares-collector-model-3 | Fully Qualified Key | Implemented | `collector_registry` values persisted on Collector nodes must use `scope:key` format. | |
| req-tap-cares-collector-model-4 | No Short Keys | Implemented | Persisted Collector nodes reject short, unscoped registry keys. | |
| req-tap-cares-collector-model-5 | Default Dimension | Implemented | New Collector nodes use the v0 default dimension `{"tap_cares": "collector"}`. | |
| req-tap-cares-collector-model-6 | Dynamic Dimensions Deferred | Implemented | Instance-derived collector dimension values are explicitly deferred. | |
| req-tap-cares-collector-model-7 | Unique Registry Key | Implemented | v0 `collector_registry` values are unique within a grid. Attempts to persist a second Collector with an existing `collector_registry` value fail validation. | Enforced via DB-level `unique=True`; revisit when per-instance configuration exists. |
| req-tap-cares-collector-model-8 | v0 Field Set | Implemented | v0 `Collector` exposes only `name`, `description`, and `collector_registry`. Per-instance configuration fields are deferred. | |

## Collector Registry
----
RID: `req-tap-cares-collector-registry`
Status: `Implemented`

The collector registry is the controlled mapping from on-grid collector definitions to executable collector code.

The registry should be named `collector_registry` and modeled on the search system's module-runner registry. It should use TAP's standard `ScopedRegistry` pattern so independently authored apps and plugins can register collector runners under local names without colliding.

Registry key format:

```text
scope:key
```

Example:

```text
plugins.fedramp_20x_ksi.collectors:ksi-catalog
```

The scope identifies where the runner was registered from, typically the module path of the registering callable. The key identifies the runner within that scope.

Collector runners are registered by trusted app or plugin code at startup. A `Collector` node never causes TAP to import a module, read a filesystem path, evaluate code, or otherwise load code dynamically from grid data. At execution time, TAP resolves the persisted `collector_registry` value by looking it up in `collector_registry`.

The collector registry is separate from `search_runner_registry`. Search runners and collector runners have different contracts and should not share a registry, even if both use the same underlying `ScopedRegistry` abstraction.

The registry instance and its public helpers live in `tap_cares/registry.py`, mirroring the search precedent in `tap_grid/registry.py`:

```python
collector_registry: ScopedRegistry[type[CollectorBase]] = ScopedRegistry(
    "collector",
    validate_key=_validate_collector_key,
    validate_scope=_validate_collector_key,
)

def register_collector(key: str, cls: type[CollectorBase], scope: str | None = None) -> None: ...
def get_collector(collector_key: str) -> type[CollectorBase]: ...
```

`register_collector` and `get_collector` are the public surface; plugin code should call the helpers rather than the registry instance directly so the type narrowing and `CollectorBase` subclass check ([req-tap-cares-collector-module-class](#collector-module-class)) stay enforced.

The collector registry uses the `validate_key` / `validate_scope` callbacks introduced by `req-grid-registry-scope-validators` (see `tap_grid/specs/spec-grid-registry.md`). That registry requirement is an implementation dependency for the collector registry. Both halves of the `scope:key` pair must match the format:

```text
^[A-Za-z0-9][A-Za-z0-9_.\-]*$
```

Validation runs on both `register()` and `get()`, so malformed runner registrations fail loud at startup and malformed persisted `Collector.collector_registry` values fail loud at execution-time lookup. The same validation helper is reused by `Collector.validate()` so the model and the registry cannot drift.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-collector-registry-1 | Scoped Registry | Implemented | Collector runners are registered in a dedicated `collector_registry` backed by TAP's `ScopedRegistry` pattern. | |
| req-tap-cares-collector-registry-2 | Separate From Search | Implemented | Collector runners do not share `search_runner_registry`. | |
| req-tap-cares-collector-registry-3 | Startup Registration | Implemented | Apps and plugins register collector runners at startup before collector execution. | |
| req-tap-cares-collector-registry-4 | Fully Qualified Lookup | Implemented | Runtime lookup uses the persisted fully qualified `scope:key` value from the Collector node. | |
| req-tap-cares-collector-registry-5 | Duplicate Guard | Implemented | Duplicate registration of the same `(scope, key)` pair is a configuration error. | |
| req-tap-cares-collector-registry-6 | No Dynamic Code Loading | Implemented | Collector execution never imports modules, reads filesystem paths, or evaluates code based on Collector node data. | |
| req-tap-cares-collector-registry-7 | Provenance By Scope | Implemented | Fully qualified keys preserve the runner's registration provenance through the scope portion of `scope:key`. | |
| req-tap-cares-collector-registry-8 | Public Helpers | Implemented | `tap_cares/registry.py` exposes `register_collector(key, cls, scope=None)` and `get_collector(collector_key)` as the public registration and lookup surface, mirroring `tap_grid.registry.register_search_runner` / `get_search_runner`. | |
| req-tap-cares-collector-registry-9 | Format Validators | Implemented | `collector_registry` is constructed with `validate_key` and `validate_scope` callbacks (per `req-grid-registry-scope-validators`) that enforce `^[A-Za-z0-9][A-Za-z0-9_.\-]*$` on each half of `scope:key`. | |
| req-tap-cares-collector-registry-10 | Shared Validator Helper | Implemented | The same validator function used by the registry is reused by `Collector.validate()` so format rules cannot drift between model-side and registry-side enforcement. | Validator helper now defined; Collector.validate() call site lands with the model in Phase 3. |

## Collector Module Class
----
RID: `req-tap-cares-collector-module-class`
Status: `Implemented`

The `collector_registry` registers collector classes that inherit from `CollectorBase`.

A collector class is the Python implementation of a collector capability. tap-cares resolves the `Collector.collector_registry` key, retrieves the registered class, builds a `CollectorConfig`, instantiates the class with that config, and invokes its `run()` method.

`CollectorBase` is an abstract base class defined in `tap_cares` that fixes the constructor signature and declares `run()` as an abstract method:

```python
from abc import ABC, abstractmethod

class CollectorBase(ABC):
    def __init__(self, config: CollectorConfig) -> None:
        self.config = config

    @abstractmethod
    def run(self) -> None: ...
```

v0 collector class shape:

```python
class ExampleCollector(CollectorBase):
    def run(self) -> None:
        ...
```

`register_collector` checks `issubclass(cls, CollectorBase)` and rejects anything else — factory functions, lambdas, plain classes that happen to define `run()`, or already-instantiated objects all fail at registration time.

The class constructor receives the `CollectorConfig`. The `run()` method receives no direct arguments in v0. Per-run information should be carried in `CollectorConfig` so the collector instance is self-contained for the duration of a run.

The module class contract intentionally avoids factory functions in v0. Registered classes are simpler to inspect, simpler to document, and easier for future skills to scaffold consistently. Reusable behavior belongs in tap-cares collector runtime helpers and shared base classes, not in plugin-specific factory setup.

Collector classes should be written as thread/process-compatible units of work:

- no reliance on request-local state
- no reliance on shared mutable module globals
- no assumption that execution occurs in the web process
- no arbitrary grid mutation below the approved GRIFT import surface
- no dependency on receiving live Django model instances in the public collector API

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-collector-module-class-1 | Registry Stores Classes | Implemented | `collector_registry` entries resolve to collector classes rather than filesystem paths, import strings, or factory functions. | |
| req-tap-cares-collector-module-class-2 | Constructor Receives Config | Implemented | tap-cares instantiates collector classes with a `CollectorConfig` object. | |
| req-tap-cares-collector-module-class-3 | Run Method | Implemented | Collector classes expose `run(self)` as the v0 execution method. | |
| req-tap-cares-collector-module-class-4 | No Run Arguments | Implemented | v0 `run()` receives no direct arguments; per-run data flows through `CollectorConfig`. | |
| req-tap-cares-collector-module-class-5 | Process-Compatible Shape | Implemented | Collector classes are specified so they can later execute outside the web process without changing the public class contract. | |
| req-tap-cares-collector-module-class-6 | CollectorBase Subclass | Implemented | Registered collector classes must inherit from `tap_cares`'s `CollectorBase` abstract base. `register_collector` rejects non-subclasses at registration time. | |
| req-tap-cares-collector-module-class-7 | Abstract Run | Implemented | `CollectorBase.run` is declared `@abstractmethod`, so concrete subclasses must override it before instantiation succeeds. | |

## CollectorConfig
----
RID: `req-tap-cares-collector-config`
Status: `Implemented`

`CollectorConfig` is the configuration object tap-cares passes to a collector class at construction time.

`CollectorConfig` is built by tap-cares, not by plugin code. In v0, it is derived only from the `Collector` node and the collection job being executed. Future versions may add JSON-safe execution data supplied by a scheduler or manual run surface.

The detailed contents of `CollectorConfig` will be refined as the first concrete collector is implemented. v0 should keep the shape deliberately small for the FedRAMP 20x KSI collector, where most behavior can be hard-coded in the registered collector class.

v0 shape — a frozen dataclass carrying exactly two identifiers:

```python
from dataclasses import dataclass
from uuid import UUID

@dataclass(frozen=True, slots=True)
class CollectorConfig:
    collector_entity_id: UUID
    collection_job_entity_id: UUID
```

These two IDs match the JSON-safe task arguments listed in [Collector Task Execution](#collector-task-execution); the task worker reconstructs the `CollectorConfig` from them after dequeuing. No `params` dict, no scheduler-supplied overrides, no per-instance Collector configuration in v0. Additional fields are introduced when the second concrete collector arrives and demonstrates a real shape requirement.

Design constraints (forward-looking):

- `CollectorConfig` must be JSON-serializable or reducible to a JSON-serializable payload.
- `CollectorConfig` should carry identifiers and configuration data, not live Django model instances.
- `CollectorConfig` should be suitable for transmission to a worker process.
- future collector-specific configuration should be modeled as JSON data, not Python objects.

This shape keeps collector modules compatible with future stricter process isolation.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-collector-config-1 | Built By tap-cares | Implemented | tap-cares builds `CollectorConfig` before instantiating a collector class. | Construction site lands with the task runtime in Phase 5; the type is callable from anywhere now. |
| req-tap-cares-collector-config-2 | Constructor Input | Implemented | `CollectorConfig` is passed to the collector class constructor. | |
| req-tap-cares-collector-config-3 | JSON-Safe Shape | Implemented | `CollectorConfig` is JSON-serializable or reducible to JSON-safe data. | |
| req-tap-cares-collector-config-4 | No Live Model Requirement | Implemented | The public collector module contract does not require live Django model instances inside `CollectorConfig`. | |
| req-tap-cares-collector-config-5 | Future Isolation Ready | Implemented | The config shape can be passed across a process boundary without changing the collector class contract. | |
| req-tap-cares-collector-config-6 | v0 Shape Is Two IDs | Implemented | The v0 `CollectorConfig` is a frozen dataclass containing exactly `collector_entity_id: UUID` and `collection_job_entity_id: UUID`. No params dict, no scheduler overrides. | |

## Collector Task Execution
----
RID: `req-tap-cares-collector-task-execution`
Status: `Implemented`

Collector execution uses Django's Tasks API as the v0 execution contract.

The web process should enqueue collector work as a Django Task. A task worker process executes the task outside the request-response lifecycle. The task resolves the on-grid `Collector`, resolves the registered collector class from `collector_registry`, builds `CollectorConfig`, instantiates the class, and calls `run()`.

The Django Task receives only JSON-safe identifiers and execution data. v0 expected task inputs include:

- `collector_entity_id`
- `collection_job_entity_id`

The exact task payload may evolve when future collector-specific configuration is introduced, but task arguments must remain JSON-safe. Task execution should not receive live model instances or arbitrary Python objects from the web process.

This requirement follows the standard Django Tasks shape: Django provides task definition, queuing, validation, and task-result plumbing; a worker process provides actual background execution. v0 does not introduce a second collector subprocess underneath the Django task worker.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-collector-task-execution-1 | Django Tasks API | Implemented | Collector execution is enqueued through Django's Tasks API. | `tap_cares.tasks.run_collector` is decorated with `@django.tasks.task(takes_context=True)`. |
| req-tap-cares-collector-task-execution-2 | Worker Process Boundary | Implemented | Collector `run()` executes in a task worker process rather than the web request process. | v0 uses `django.tasks.backends.immediate.ImmediateBackend` (synchronous for dev/test); switching to a worker backend changes only `TASKS["default"]["BACKEND"]`. |
| req-tap-cares-collector-task-execution-3 | JSON-Safe Task Args | Implemented | Collector task arguments are JSON-serializable and initially limited to identifiers such as collector and job entity IDs. | `run_collector(context, collector_entity_id: str, collection_job_entity_id: str)`. |
| req-tap-cares-collector-task-execution-4 | Resolve In Worker | Implemented | The worker resolves Collector state and collector class registration after task execution begins. | Inside `run_collector`: looks up Collector + CollectionJob via Django ORM, then calls `get_collector(registry_key)`. |
| req-tap-cares-collector-task-execution-5 | No Nested Subprocess In v0 | Implemented | v0 does not require the task worker to spawn a second collector subprocess. | |

## Collector Read Boundary
----
RID: `req-tap-cares-collector-read-boundary`
Status: `Implemented`

Collector modules must not mutate TAP graph state through arbitrary write paths.

Collectors gather data and perform collector-specific interpretation. tap-cares execution services own grid writes for job state and status. Collector modules may read TAP state only through approved search/read surfaces.

The initial read path should favor TAP search APIs and service-layer read operations. This keeps collector reads aligned with future authorization, dimensions, and security policy work.

For collection results, the approved mutation path is the GRIFT import surface defined in [Collector GRIFT Import Surface](#collector-grift-import-surface). This is an explicit carve-out: collector modules may cause grid mutation by submitting a GRIFT batch through the approved import path. Collector modules should not import TAP models, call generic write services, call `write_batch()` directly, or otherwise bypass GRIFT import semantics.

Because v0 collector code still runs as Python inside a Django task worker process, this requirement is initially a contract and design constraint rather than a full sandbox. Stronger enforcement is tracked in [Strict Collector Isolation](#strict-collector-isolation).

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-collector-read-boundary-1 | No Mutation Outside GRIFT | Implemented | Collector modules are prohibited by contract from directly creating, updating, or deleting TAP-managed nodes or edges outside the approved GRIFT import surface. | GRIFT import is the explicit exception (`tap_cares.grift.submit_collector_grift`). |
| req-tap-cares-collector-read-boundary-2 | Approved Read Surfaces | Implemented | Collector modules read TAP state through approved search/read surfaces rather than ad hoc ORM access. | Contract; not enforced at runtime in v0 (see -5). |
| req-tap-cares-collector-read-boundary-3 | Runtime Owns Job Writes | Implemented | tap-cares execution services own grid writes for collector job state and status; collector result writes are permitted only through the approved GRIFT import path. | run_collector uses `update_fields` so the collector's `grift_batches` update is not clobbered by the lifecycle save. |
| req-tap-cares-collector-read-boundary-4 | Future Auth Alignment | Implemented | Collector read design must remain compatible with future authorization and dimension-scoped security. | |
| req-tap-cares-collector-read-boundary-5 | Enforcement Gap Named | Implemented | The spec explicitly recognizes that v0 in-process Python cannot fully sandbox collector code. | |

## Collector GRIFT Import Surface
----
RID: `req-tap-cares-collector-grift-import`
Status: `Implemented`

Collector result mutations must route through TAP's GRIFT import surface.

GRIFT import is the top-most exposed grid ingestion affordance for batch-shaped interchange. It sits above the lower-level service batch plumbing: the importer validates the GRIFT document, applies GRIFT batch identity and ordering rules, decides create-versus-replace behavior, handles importer diagnostics, and then executes the resulting service-layer write batch.

In v0, collector modules may submit collected results through the in-process GRIFT import service, `grift_import()`, or through a tap-cares helper that wraps it. The collector contract should treat GRIFT import as the approved result submission boundary. Collector modules must not call lower-level mutation primitives such as `write_batch()`, node/edge write helpers, direct ORM saves, or direct `Entity` updates.

tap-cares remains responsible for `CollectionJob` lifecycle state. When a collector imports a GRIFT document, the import result should be made available through a tap-cares-owned result path so the `CollectionJob` can be correlated with imported or skipped GRIFT batch entities. The exact return mechanics are deferred until the collector runtime and first concrete collector are implemented.

Future strict isolation may replace the in-process call with a TAP API result-submission endpoint. That endpoint should preserve the same contract: collector code submits GRIFT; TAP validates, authorizes, imports, records provenance, and returns structured import results.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-collector-grift-import-1 | GRIFT Is Result Boundary | Implemented | Collector result mutations route through GRIFT import rather than ad hoc grid writes. | `tap_cares.grift.submit_collector_grift` wraps `grift_import()`. |
| req-tap-cares-collector-grift-import-2 | v0 In-Process Import Allowed | Implemented | v0 collector execution may use in-process `grift_import()` or a tap-cares wrapper around it. | |
| req-tap-cares-collector-grift-import-3 | No Raw write_batch | Implemented | Collector modules do not call `write_batch()` or lower-level node/edge mutation helpers directly. | Contract; not enforced at runtime in v0. |
| req-tap-cares-collector-grift-import-4 | Job Correlation | Implemented | tap-cares can correlate a `CollectionJob` with the GRIFT batch entities imported or skipped by that job. | `CollectionJob.grift_batches` is a JSON field with `{"imported": [...], "skipped": [...]}` populated by `submit_collector_grift`. Imports across multiple `submit_collector_grift` calls in a single run accumulate. |
| req-tap-cares-collector-grift-import-5 | Future API Compatible | Implemented | The v0 contract remains compatible with replacing in-process import with an API-based GRIFT submission surface under strict isolation. | `submit_collector_grift` takes a document and returns a `GriftImportResult`; replacing the in-process call with an API round trip changes only the helper internals. |

## CollectionJob Model
----
RID: `req-tap-cares-collector-job-model`
Status: `Implemented`

`CollectionJob` is the on-grid execution record for one collector run.

A `Collector` is the root/capability node. A `CollectionJob` is a subordinate run instance that records the current lifecycle state of one attempted execution of that collector. The job exists so humans, management surfaces, schedulers, and future agents can see that collector execution is happening on the grid rather than inside an invisible background subsystem.

`CollectionJob` must be implemented as a standard TAP-managed `BaseModel` node using the model-building skill at `tap_grid/skills/add-model/SKILL.md`. The model should follow ordinary TAP model conventions rather than re-specifying boilerplate in this requirement.

CollectionJob-specific model requirements:

- `CollectionJob` has a human-readable `name`.
- `CollectionJob` has a plain-text `description`.
- `CollectionJob` has a `status` `CharField` driven by a `models.TextChoices` enum (see [CollectionJob Lifecycle Status](#collectionjob-lifecycle-status)).
- `CollectionJob` has a `task_result_id` `CharField(max_length=128, blank=True, default="")`. This stores the `TaskResult.id` returned by Django's Tasks API — a backend-defined string, **not** a UUID. The built-in `immediate` and `dummy` backends use 32-char random strings (`get_random_string(32)`); other backends may differ. `max_length=128` is comfortably above the current built-in but small enough to remain index-friendly. Empty string represents "not yet enqueued / enqueue raised."
- `CollectionJob` has `enqueued_at`, `started_at`, and `finished_at` `DateTimeField(null=True, blank=True)` timestamps; each is populated as the corresponding lifecycle transition occurs.
- `CollectionJob` has an `error_summary` `CharField(max_length=2048, blank=True, default="")` field for safe, short failure details. Long stack traces or raw payloads belong in the future status/log stream ([Collection Job Status Messages And Logs](#collection-job-status-messages-and-logs)), not here.
- The `CollectionJob` display projection emits both the raw `status` value and a `status_display` field carrying the human-readable label (via Django's auto-generated `get_status_display()`).
- The v0 default dimension is `{"tap_cares": "collection_job"}`.

The job does not snapshot `Collector.collector_registry` in v0. The job's collector provenance comes from the `Collector --HAS_JOB--> CollectionJob` edge. If immutable runner snapshots become necessary, that should be added as a separate requirement.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-collector-job-model-1 | Standard BaseModel | Implemented | `CollectionJob` is specified as a normal TAP-managed `BaseModel` node implemented through the model-building skill conventions. | |
| req-tap-cares-collector-job-model-2 | Execution Record | Implemented | Each `CollectionJob` represents one attempted collector execution. | |
| req-tap-cares-collector-job-model-3 | Lifecycle Fields | Implemented | `CollectionJob` carries status, task result identity, lifecycle timestamps, and safe error summary fields. | |
| req-tap-cares-collector-job-model-4 | Default Dimension | Implemented | New CollectionJob nodes use the v0 default dimension `{"tap_cares": "collection_job"}`. | |
| req-tap-cares-collector-job-model-5 | No Registry Snapshot | Implemented | `CollectionJob` does not copy `Collector.collector_registry` in v0; the relationship to Collector carries that provenance. | |
| req-tap-cares-collector-job-model-6 | task_result_id Is String | Implemented | `task_result_id` is `CharField(max_length=128, blank=True, default="")` matching Django's `TaskResult.id: str` contract, not a UUID. Empty string indicates the task was not enqueued or enqueue raised. | |
| req-tap-cares-collector-job-model-7 | Bounded error_summary | Implemented | `error_summary` is bounded (CharField `max_length=2048`). Long traces and raw payloads are out of scope for this field and belong in the future status/log stream. | |
| req-tap-cares-collector-job-model-8 | Status Display Projection | Implemented | The CollectionJob display projection emits both the raw `status` value and a `status_display` field carrying the title-case human label from `get_status_display()`. | |

## Collector HAS_JOB Edge
----
RID: `req-tap-cares-collector-job-edge`
Status: `Implemented`

The relationship between a collector capability and a collection job is represented as:

```text
Collector --HAS_JOB--> CollectionJob
```

This edge preserves the philosophical shape of the collector subsystem: `Collector` is the root capability node, and collection jobs are run instances owned by that collector.

tap-cares collector execution creates the `CollectionJob` node and the `HAS_JOB` edge when it starts a collector run. Collector modules do not create this edge directly.

The `HAS_JOB` edge should be a normal TAP edge type declared by tap-cares, with appropriate constraints so its source is `collector` and its target is `collection_job`.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-collector-job-edge-1 | HAS_JOB Edge Type | Implemented | tap-cares declares a `HAS_JOB` edge type for Collector to CollectionJob relationships. | Registered programmatically in `TapCaresConfig.ready()` via `register_edge_type_constraints` (first-party apps don't use the plugin manifest). |
| req-tap-cares-collector-job-edge-2 | Direction | Implemented | The edge direction is `Collector --HAS_JOB--> CollectionJob`. | |
| req-tap-cares-collector-job-edge-3 | Runtime Owned | Implemented | tap-cares collector execution creates the edge; collector modules do not create it directly. | Edge creation site lands with the orchestration service in Phase 5. |
| req-tap-cares-collector-job-edge-4 | Constrained Endpoints | Implemented | The edge type constrains source to `collector` and target to `collection_job`. | Strict rejection of disallowed endpoints depends on `tap_grid`'s Permission Union model: target node types must opt into `INBOUND_EDGES` constraints to actively block. The edge-type registration documents intended endpoints. |

## CollectionJob Lifecycle Status
----
RID: `req-tap-cares-collector-job-lifecycle`
Status: `Implemented`

`CollectionJob.status` reflects the coarse Django Tasks lifecycle for the collector task.

v0 intentionally maps `CollectionJob.status` directly to the Django task runner lifecycle because Django Tasks is the only supported collector runner process. If tap-cares later supports multiple runner backends, this requirement should be revisited so TAP-facing collection job status can be distinguished from backend-specific task status.

v0 status values mirror Django's `TaskResultStatus` exactly so no case translation is needed when copying status from a `TaskResult` to a `CollectionJob`. Values are stored uppercase; display labels are title-case:

```python
class Status(models.TextChoices):
    READY = "READY", "Ready"
    RUNNING = "RUNNING", "Running"
    FAILED = "FAILED", "Failed"
    SUCCESSFUL = "SUCCESSFUL", "Successful"
```

Stored values: `READY`, `RUNNING`, `FAILED`, `SUCCESSFUL`. Display labels: `Ready`, `Running`, `Failed`, `Successful`. The CollectionJob display projection exposes both (see `req-tap-cares-collector-job-model-8`).

The enum is tap-cares-owned — declared on `CollectionJob`, not imported from `django.tasks`. The v0 set deliberately mirrors Django's four values, but future TAP-specific states (`CANCEL_REQUESTED`, `CANCELLED`, `BLOCKED`, `PARTIAL`, etc.) are added by extending the local `TextChoices`, not by depending on Django's enum evolving.

tap-cares collector execution owns status updates. It should create the job with the appropriate initial lifecycle state, update the job when the task starts, and update the job when the task finishes. The collector module class does not update job status directly.

TAP-specific states such as `CANCEL_REQUESTED`, `CANCELLED`, `BLOCKED`, or `PARTIAL` are deferred until concrete needs appear.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-collector-job-lifecycle-1 | Django Status Values | Implemented | `CollectionJob.status` uses only `READY`, `RUNNING`, `FAILED`, and `SUCCESSFUL` (uppercase) in v0, matching `django.tasks.base.TaskResultStatus`. | |
| req-tap-cares-collector-job-lifecycle-2 | Runtime Updates Status | Implemented | tap-cares collector execution updates `CollectionJob.status` from task lifecycle changes. | Update site lands with the Django Tasks runtime in Phase 5. |
| req-tap-cares-collector-job-lifecycle-3 | Module Does Not Update Status | Implemented | Collector module classes do not directly mutate `CollectionJob.status`. | Enforced by contract: `CollectorBase.run` returns `None` and has no access to the `CollectionJob` instance. |
| req-tap-cares-collector-job-lifecycle-4 | Lifecycle Timestamps | Implemented | tap-cares records enqueued, started, and finished timestamps on the CollectionJob when available. | Timestamp-writing call sites land with the Django Tasks runtime in Phase 5. |
| req-tap-cares-collector-job-lifecycle-5 | TAP-Specific States Deferred | Implemented | TAP-specific job states are not part of v0 and require future requirements once tap-cares supports runner backends beyond the hardcoded Django task runner. | |
| req-tap-cares-collector-job-lifecycle-6 | TextChoices Enum | Implemented | `CollectionJob.status` is backed by a `models.TextChoices` enum with uppercase stored values and title-case display labels (`READY`/`"Ready"`, `RUNNING`/`"Running"`, `FAILED`/`"Failed"`, `SUCCESSFUL`/`"Successful"`). | |
| req-tap-cares-collector-job-lifecycle-7 | Enum Owned By tap-cares | Implemented | The Status enum is declared on `CollectionJob`, not imported from `django.tasks`. v0 mirrors Django's four values; future TAP-specific states extend the local enum rather than rely on Django's set evolving. | |

## Collection Job Status Messages And Logs
----
RID: `req-tap-cares-collector-job-logs`
Status: `Backlog`

Richer in-process job status messages, logs, warnings, and incremental progress events are deferred.

Django Tasks exposes coarse lifecycle information, but it does not provide a native progress/event stream for arbitrary task status messages. v0 therefore records coarse lifecycle state on `CollectionJob` and leaves detailed status/log emission for a later design.

Future work should define whether status messages and logs are modeled as separate grid nodes, edge-linked events, backend log records projected onto the grid, or a stricter isolated process message channel.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-collector-job-logs-1 | Backlog Requirement Exists | Backlog | Rich collection job status/log/event emission is tracked as a named backlog requirement. | |
| req-tap-cares-collector-job-logs-2 | Not Required For v0 | Backlog | v0 collector execution is not required to emit incremental status messages or logs. | |
| req-tap-cares-collector-job-logs-3 | Future Grid Shape Required | Backlog | Future status/log work must define how messages become visible on the grid. | |

## Strict Collector Isolation
----
RID: `req-tap-cares-collector-strict-isolation`
Status: `Backlog`

Strict collector isolation is a future execution mode that enforces collector boundaries with operating-system or process-level controls.

The goal is to run collectors in an isolated environment that cannot mutate TAP graph state directly. A strictly isolated collector should receive serialized configuration, read TAP only through approved narrow APIs, and return through a validated result channel.

Possible implementation directions include:

- separate OS process per collector run
- distinct host user for collector execution
- restricted environment variables and credentials
- no Django database write credentials
- search-only TAP API token or equivalent read-only capability
- host-supported filesystem and network restrictions
- process-level kill controls

Strict isolation is not required for v0 collector execution. The v0 module and config contracts should, however, remain compatible with this future mode.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-collector-strict-isolation-1 | Backlog Requirement Exists | Backlog | Strict collector isolation is tracked as a named backlog requirement. | |
| req-tap-cares-collector-strict-isolation-2 | No Write Credentials | Backlog | Isolated collectors do not receive Django database write credentials. | |
| req-tap-cares-collector-strict-isolation-3 | Approved Read Only | Backlog | Isolated collectors read TAP state only through approved search/read surfaces. | |
| req-tap-cares-collector-strict-isolation-4 | Serialized Config | Backlog | Isolated collectors receive JSON-safe serialized configuration. | |
| req-tap-cares-collector-strict-isolation-5 | Validated Return Channel | Backlog | Isolated collector output returns through a validated channel owned by tap-cares. | |
| req-tap-cares-collector-strict-isolation-6 | Kill Controls Considered | Backlog | Strict isolation design includes process-level termination controls or explicitly rejects them with rationale. | |

## Future

- Define collection job status/log/error nodes and edges beyond coarse lifecycle status.
- Define richer collection result records and job-to-batch graph relationships.
- Define management surfaces for collectors and collection jobs.
