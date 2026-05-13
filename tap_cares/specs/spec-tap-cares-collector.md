# tap-cares Collector Specification

## Philosophy

Collectors are tap-cares capabilities that gather data from a source and prepare it for TAP-owned processing. The collector system rests on three foundations:

- an on-grid `Collector` node that represents the capability TAP can inspect, schedule, and manage — declared as a dual-existence capability per `tap_grid/specs/spec-grid-dual-existence.md`
- a `collector_registry` that maps the collector node's stable registry key to trusted Python code registered at startup
- a public entry point `run_collection(collector)` that owns the entire execution path: CollectionJob creation, HAS_JOB linking, task enqueueing, and lifecycle bookkeeping

`run_collection` is the only legal way to start a collection. The future scheduler subsystem is the intended steady-state caller — it decides *when* a collection runs and invokes `run_collection`. The scheduler does not reach behind `run_collection` to create CollectionJobs, manipulate Django Tasks, or coordinate Collector identity. This is the **scheduler boundary**: scheduling is trigger; collection is everything from trigger onward. The scheduler spec is out of scope for this document and tracked separately.

For v0, before the scheduler exists, the Administrivia HTMX handler is a permitted direct caller of `run_collection`. That direct call gets mediated by the scheduler when it lands; `run_collection`'s contract does not change.

Status messages and richer event records remain backlog (`req-tap-cares-collector-job-logs`). This spec slice defines the collector model-to-module mapping, the dual-existence registration mechanism, the public `run_collection` entry point, the Django Task execution boundary, the approved GRIFT import path for collection results, and the on-grid `CollectionJob` execution record.

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
| req-tap-cares-collector-model | [Collector Model](#collector-model) | Refactoring | On-grid dual-existence capability node; INTERNAL_ONLY |
| req-tap-cares-collector-registry | [Collector Registry](#collector-registry) | Implemented | Scoped registry mapping collector keys to registered runner code |
| req-tap-cares-collector-registration | [Collector Registration](#collector-registration) | Proposed | `register_collector(key, cls, *, name, description)` creates both the runner registry entry and the on-grid Collector node |
| req-tap-cares-collector-concurrency | [Collector Concurrency Policy](#collector-concurrency-policy) | Backlog | Future per-collector maximum simultaneous run count |
| req-tap-cares-collector-module-class | [Collector Module Class](#collector-module-class) | Implemented | Registered collector classes instantiated by tap-cares |
| req-tap-cares-collector-config | [CollectorConfig](#collectorconfig) | Implemented | JSON-safe collector configuration object |
| req-tap-cares-collector-run-collection | [Run Collection Entry Point](#run-collection-entry-point) | Proposed | Public callable `run_collection(collector)` owns CollectionJob creation, HAS_JOB linking, and task enqueueing |
| req-tap-cares-collector-task-execution | [Collector Task Execution](#collector-task-execution) | Refactoring | Django Tasks worker-process execution boundary; tasks fire only via `run_collection` |
| req-tap-cares-collector-read-boundary | [Collector Read Boundary](#collector-read-boundary) | Refactoring | Collector modules read through approved search/read surfaces and only submit result mutations through GRIFT import |
| req-tap-cares-collector-grift-import | [Collector GRIFT Import Surface](#collector-grift-import-surface) | Refactoring | Collector result grid mutations route through the GRIFT importer; batch tracking accumulates on the collector instance |
| req-tap-cares-collector-job-model | [CollectionJob Model](#collectionjob-model) | Refactoring | INTERNAL_ONLY execution record; accumulator pattern for results/grift_batches |
| req-tap-cares-collector-job-sole-writer | [CollectionJob Sole-Writer Invariant](#collectionjob-sole-writer-invariant) | Proposed | Only `run_collection` and the task body write to CollectionJob; helpers accumulate in-memory |
| req-tap-cares-collector-job-edge | [Collector HAS_JOB Edge](#collector-has_job-edge) | Implemented | Graph relationship from Collector root node to its CollectionJob nodes |
| req-tap-cares-collector-job-lifecycle | [CollectionJob Lifecycle Status](#collectionjob-lifecycle-status) | Implemented | Job status reflects Django Tasks lifecycle states |
| req-tap-cares-collector-failure-mode | [Collector Failure Mode](#collector-failure-mode) | Proposed | Framework convention for how a collector signals failure; KSI and other collectors follow this protocol rather than re-specifying it |
| req-tap-cares-collector-job-logs | [Collection Job Status Messages And Logs](#collection-job-status-messages-and-logs) | Backlog | Deferred richer in-process status/log/event stream |
| req-tap-cares-collector-strict-isolation | [Strict Collector Isolation](#strict-collector-isolation) | Backlog | Future stronger isolation for untrusted or high-risk collector execution |
| req-tap-cares-collector-runtime-helpers | [Shared Collector Runtime Helpers](#shared-collector-runtime-helpers) | Backlog | Standard helper modules (git, http, archive, …) collectors can compose from |

## Collector Model
----
RID: `req-tap-cares-collector-model`
Status: `Refactoring`

`Collector` is the grid-side representation of a tap-cares collector capability and is the canonical first consumer of the dual-existence pattern (see `tap_grid/specs/spec-grid-dual-existence.md`).

`Collector` must be implemented as a standard TAP-managed `BaseModel` node using the model-building skill at `tap_grid/skills/add-model/SKILL.md`. The model should follow ordinary TAP model conventions rather than re-specifying boilerplate in this requirement. Those conventions include entity-spine backing, `ENTITY_TYPE`, display metadata, `FIELD_CRUD_SCHEMA`, `FIELD_VALIDATION_SCHEMA`, `CREATE_REQUIRED`, `get_name()`, history behavior, and tests for creation, validation, display projection, and dimensions.

`Collector` declares `INTERNAL_ONLY: ClassVar[bool] = True` per `req-grid-entity-internal`. The generic service-layer CRUD verbs and the GRIFT importer cannot create, patch, replace, or delete `Collector` rows. The sole legal creation path is `register_collector(...)` (see [Collector Registration](#collector-registration)), which uses `_create_node_internal` from `tap_grid.services` (see `req-grid-service-write-internal-create` in `spec-grid-service-write.md`) to construct the node while preserving the full write pipeline.

The collector node must not store arbitrary filesystem paths, dynamic import paths, or executable code. It stores a fully qualified registry key. The registry is the controlled intermediary between grid data and executable code.

Collector-specific model requirements:

- `Collector` has a human-readable `name`.
- `Collector` has a plain-text `description`.
- `Collector` has a top-level `collector_registry` field.
- `collector_registry` stores the fully qualified registry key used to resolve the collector's registered runner.
- Persisted `collector_registry` values must use `scope:key` format.
- Persisted collector nodes must not use short keys.
- Persisted `collector_registry` values are unique per grid in v0; two Collector nodes may not share the same registry key while per-instance configuration is deferred.
- The on-grid `entity_id` for a Collector is deterministically derived from its `collector_registry` value: `entity_id = uuid5(NAMESPACE_COLLECTOR, collector_registry)`. The `NAMESPACE_COLLECTOR` UUID is a module-level constant in `tap_cares/registry.py`.
- v0 ships only `name`, `description`, and `collector_registry`. Per-instance configuration is deferred (see [CollectorConfig](#collectorconfig)); the first concrete collector (FedRAMP 20x KSI) hardcodes its behavior in the registered class.
- The v0 default dimension is `{"tap_cares": "collector"}`.
- Instance-derived collector dimensions are deferred until TAP's dimension conventions are revisited.

The scheduler will use `Collector` nodes to determine which collector capability to execute. The scheduler relationship and execution behavior are out of scope for this requirement; see [Run Collection Entry Point](#run-collection-entry-point) for the public callable the scheduler invokes.

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
| req-tap-cares-collector-model-9 | INTERNAL_ONLY | Proposed | `Collector.INTERNAL_ONLY = True`. Generic `create_node` / `patch_node` / `replace_node` / `delete_node` and GRIFT import all reject the `collector` entity type. | |
| req-tap-cares-collector-model-10 | Deterministic Entity ID | Proposed | A Collector's `entity_id` is `uuid5(NAMESPACE_COLLECTOR, collector_registry)`. The same `scope:key` always yields the same `entity_id` across reloads and across grids. | `NAMESPACE_COLLECTOR` is a module-level UUID constant in `tap_cares/registry.py`. |
| req-tap-cares-collector-model-11 | Registration Is Sole Creator | Proposed | The only legal path that creates a `Collector` row is `register_collector(...)` (see [Collector Registration](#collector-registration)), which uses `_create_node_internal` from `tap_grid.services`. | |

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

## Collector Registration
----
RID: `req-tap-cares-collector-registration`
Status: `Proposed`

`register_collector(...)` is the dual-existence registration entry point for collectors. It performs two coupled actions in one call: it registers the runner class in `collector_registry`, and it upserts the on-grid `Collector` node.

This is the **sole legal path** for creating a `Collector` row. Generic `create_node`, GRIFT seeds, and direct ORM are all closed by `Collector.INTERNAL_ONLY = True`.

#### Signature

```python
def register_collector(
    key: str,
    cls: type[CollectorBase],
    *,
    name: str,
    description: str,
    scope: str | None = None,
) -> None:
    """Register a collector capability.

    Performs two coupled actions:
    1. Registers `cls` in `collector_registry` under `scope:key`.
       If `scope` is omitted, it is inferred from `cls.__module__`.
    2. Upserts the on-grid `Collector` node with:
       - entity_id = uuid5(NAMESPACE_COLLECTOR, f"{scope}:{key}")
       - collector_registry = f"{scope}:{key}"
       - name = name
       - description = description

    The Collector node upsert uses `_create_node_internal` from
    `tap_grid.services` for new rows, or `_patch_node_internal` (or the
    equivalent service-layer call) for existing rows. Both paths preserve
    the write pipeline.
    """
```

`name` and `description` are required keyword arguments. Plugin authors must provide human-readable identity for the on-grid node; collectors that ship to a TAP installation become visible in admin UIs and must carry display metadata appropriate for that visibility. There is no v0 default value or implicit fallback.

#### Plugin-side usage

```python
# plugins/<slug>/apps.py
class <Plugin>Config(TapPluginConfig):
    def ready(self) -> None:
        from tap_cares.registry import register_collector
        from plugins.<slug>.collectors.<module> import <Class>

        register_collector(
            key="<short-key>",
            cls=<Class>,
            name="Human-Readable Name",
            description="One-line description of what this collector does.",
        )
```

The first call on a fresh install creates the on-grid `Collector` node. Subsequent calls (every app restart, every plugin reload) upsert: identity stays stable because `entity_id` is deterministic; `name` and `description` refresh with whatever the plugin currently declares.

#### Identity derivation

Per `req-grid-dual-existence-identity`, the on-grid `entity_id` is:

```python
entity_id = uuid.uuid5(NAMESPACE_COLLECTOR, f"{scope}:{key}")
```

`NAMESPACE_COLLECTOR` is a module-level UUID constant in `tap_cares/registry.py`. Once set, it is immutable — changing it would re-identify every Collector node on every grid.

#### Helper colocation

In v0 the trusted-internal helper `_ensure_collector_node(...)` lives alongside `register_collector` in `tap_cares/registry.py`. The helper is private (leading underscore) and is not re-exported from any tap_cares public surface. It calls `_create_node_internal` (or the patch variant) to do the actual write.

When the dual-existence pattern lands a second concrete consumer (Emitter, Action, or Receiver), the helper is a candidate for consolidation into a shared registration mechanism per `req-grid-dual-existence-consolidation` in `spec-grid-dual-existence.md`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-collector-registration-1 | Single Entry Point | Proposed | `register_collector(key, cls, *, name, description, scope=None)` is the sole legal path for creating an on-grid `Collector` row. | |
| req-tap-cares-collector-registration-2 | Two Coupled Actions | Proposed | One call registers the runner class in `collector_registry` AND upserts the on-grid `Collector` node. | |
| req-tap-cares-collector-registration-3 | Required Display Metadata | Proposed | `name` and `description` are required keyword arguments. No default values or implicit fallbacks. | |
| req-tap-cares-collector-registration-4 | Deterministic Identity | Proposed | The on-grid `entity_id` is `uuid5(NAMESPACE_COLLECTOR, f"{scope}:{key}")`. | |
| req-tap-cares-collector-registration-5 | Idempotent Reload | Proposed | Repeated calls with the same `scope:key` upsert the node; identity stays stable; `name` and `description` refresh to the latest values. | |
| req-tap-cares-collector-registration-6 | Trusted-Internal Create | Proposed | New Collector rows are created via `_create_node_internal` from `tap_grid.services` so the full write pipeline runs. | See `req-grid-service-write-internal-create`. |
| req-tap-cares-collector-registration-7 | Private Helper Colocation | Proposed | `_ensure_collector_node` lives in `tap_cares/registry.py` alongside `register_collector` and is not re-exported. | Migration candidate for the shared mechanism in `req-grid-dual-existence-consolidation`. |
| req-tap-cares-collector-registration-8 | Namespace UUID Stable | Proposed | `NAMESPACE_COLLECTOR` in `tap_cares/registry.py` is a module-level constant; changing it is a grid-wide identity break and not permitted. | |

## Collector Concurrency Policy
----
RID: `req-tap-cares-collector-concurrency`
Status: `Backlog`

Each `Collector` should eventually declare how many simultaneous runs of that collector may be active.

Possible future model field:

```python
max_concurrent_runs = models.PositiveIntegerField(default=1)
```

This requirement is intentionally Backlog until the collector enqueue path, scheduler behavior, and future API trigger surface are untangled together. Concurrency touches all three: manual runs, scheduled runs, and any future externally-triggered collection request need one authoritative policy.

The likely shape is a field stored on the on-grid `Collector` node. Concurrency would be evaluated per `Collector` entity: before enqueuing a new collection job, tap-cares would count active `CollectionJob` records linked from that collector through `HAS_JOB` whose status is `RUNNING`. If the active count is greater than or equal to `Collector.max_concurrent_runs`, the service layer would refuse to enqueue another job.

The expected default is `1` because most collectors are safer as singleton execution paths until a concrete need for parallel collection exists. The FedRAMP 20x KSI catalog collector should remain singleton; there is no useful reason to refresh the same catalog source multiple times at once.

`max_concurrent_runs` must be a positive integer. `0` is not a disablement mechanism; capability enable/disable is separately tracked as backlog work in `spec-tap-cares-v0.md`.

When implemented, the service layer must be authoritative. Administrative pages may disable or guard Run buttons based on this field, but UI behavior is advisory. Manual runs, future scheduler-triggered runs, and any API-triggered runs must all route through the same concurrency guard.

This requirement intentionally scopes v0 concurrency to one `Collector` node. Today `collector_registry` is unique, so a collector node and a registered runner are effectively one-to-one. If future per-instance configuration allows multiple Collector nodes to share one runner, a later requirement should decide whether concurrency remains per node or moves to a shared `concurrency_key` / runner-level policy.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-collector-concurrency-1 | Field Declared | Backlog | `Collector` declares a positive integer `max_concurrent_runs` field with default `1`. | |
| req-tap-cares-collector-concurrency-2 | Positive Value Required | Backlog | `max_concurrent_runs` must be greater than or equal to `1`; `0` is invalid. | Disablement remains a separate backlog concern. |
| req-tap-cares-collector-concurrency-3 | Service-Layer Guard | Backlog | `run_collection()` refuses to create/enqueue a new job when linked `RUNNING` jobs meet or exceed the collector limit. | |
| req-tap-cares-collector-concurrency-4 | UI Reflects Policy | Backlog | Admin surfaces disable, guard, or explain manual Run actions when the concurrency limit is already reached. | Service layer remains authoritative. |
| req-tap-cares-collector-concurrency-5 | KSI Singleton | Backlog | The FedRAMP 20x KSI collector is configured for one simultaneous run. | |
| req-tap-cares-collector-concurrency-6 | Future Shared Runner Scope Deferred | Backlog | Any runner-level or shared-key concurrency across multiple Collector nodes is deferred until per-instance collector configuration exists. | |

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

## Run Collection Entry Point
----
RID: `req-tap-cares-collector-run-collection`
Status: `Proposed`

`run_collection(collector)` is the public callable that the collection system exposes for starting a collection. It is the **scheduler boundary**: callers (today: Administrivia HTMX handler; future steady-state: the scheduler) invoke `run_collection` and the collection system owns everything from that point — CollectionJob creation, HAS_JOB linking, Django Task enqueueing, CollectorConfig assembly, and lifecycle bookkeeping.

#### Signature

```python
def run_collection(
    collector: Collector,
    *,
    caller_context: CallerContext | None = None,
) -> CollectionJob:
    """Start a collection run for the given Collector.

    Performs, in order:
    1. Enforce concurrency policy (req-tap-cares-collector-concurrency, Backlog).
    2. Create a CollectionJob node via _create_node_internal
       (since CollectionJob is INTERNAL_ONLY).
    3. Create a HAS_JOB edge from collector.entity to the new job
       via the service-layer create_edge.
    4. Build a CollectorConfig from the collector and job entity IDs.
    5. Enqueue the run_collector Django Task with the JSON-safe IDs.
    6. Return the CollectionJob in its post-enqueue state.

    With ImmediateBackend (v0 default), the returned job will already
    reflect the terminal task outcome. With a worker backend, the job
    will be READY or RUNNING depending on worker pickup latency.
    """
```

#### Responsibilities and boundaries

`run_collection` owns:

- CollectionJob node creation (via `_create_node_internal` since `CollectionJob.INTERNAL_ONLY = True`).
- HAS_JOB edge creation (via `tap_grid.services.create_edge`).
- Django Task enqueueing.
- Returning the job in its post-enqueue state.

`run_collection` does **not** own:

- Deciding *when* to run — that's the scheduler's job (or the human pressing a Run button).
- Picking which collector — the caller passes a `Collector` instance.
- Anything that happens during `cls(config).run()` execution — that's the task body's job.

#### v0 callers

The intended steady-state caller is the future scheduler subsystem. Until that subsystem exists, the only permitted v0 caller is the Administrivia HTMX panel handler (per `spec-tap-cares-admin.md` → `req-tap-cares-admin-manual-run`). Direct calls from arbitrary plugin code are not permitted; the path is "create a scheduler trigger" (future) or "use the Administrivia handler" (v0).

#### Concurrency

`run_collection` is the authoritative point for collector concurrency enforcement. When `req-tap-cares-collector-concurrency` lands, the guard fires here — before CollectionJob creation, so a rejected request never produces a grid mutation. Manual UI triggers, scheduler triggers, and future API triggers all converge on `run_collection` and therefore share one concurrency contract.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-collector-run-collection-1 | Public Entry Point | Proposed | `run_collection(collector, *, caller_context=None) -> CollectionJob` is the sole public callable for starting a collection. | Replaces the v0 internal `enqueue_collection` name. |
| req-tap-cares-collector-run-collection-2 | Service-Layer Routing | Proposed | All grid mutations performed by `run_collection` (CollectionJob create, HAS_JOB create) route through the service layer or the trusted-internal create helper. No direct ORM writes for grid-managed types. | |
| req-tap-cares-collector-run-collection-3 | CollectionJob Internal Create | Proposed | `run_collection` is the sole legal creator of CollectionJob rows, using `_create_node_internal` (since CollectionJob is INTERNAL_ONLY). | |
| req-tap-cares-collector-run-collection-4 | Edge Through Service Layer | Proposed | The HAS_JOB edge is created via `tap_grid.services.create_edge`. | |
| req-tap-cares-collector-run-collection-5 | Concurrency Chokepoint | Proposed | `run_collection` is where the future concurrency guard (`req-tap-cares-collector-concurrency`) fires; manual, scheduled, and future API triggers all share it. | |
| req-tap-cares-collector-run-collection-6 | Scheduler Is Caller, Not Owner | Proposed | The future scheduler subsystem invokes `run_collection`; it does not reach behind it to create CollectionJobs or enqueue tasks directly. | |
| req-tap-cares-collector-run-collection-7 | Admin Caller Permitted In v0 | Proposed | The Administrivia HTMX panel handler is the permitted v0 caller. The path migrates to scheduler-mediated triggering when the scheduler spec lands; `run_collection`'s contract does not change. | See `spec-tap-cares-admin.md` `req-tap-cares-admin-manual-run`. |
| req-tap-cares-collector-run-collection-8 | Post-Enqueue Return | Proposed | The function returns the CollectionJob in its post-enqueue state. Under ImmediateBackend the job reflects terminal status; under worker backends it reflects READY or RUNNING. | |

## Collector Task Execution
----
RID: `req-tap-cares-collector-task-execution`
Status: `Refactoring`

Collector execution uses Django's Tasks API as the v0 execution contract.

The `run_collector` Django Task is enqueued **only** by `run_collection` (see [Run Collection Entry Point](#run-collection-entry-point)). No other code path in `tap_cares` or in plugins is permitted to call `run_collector.enqueue(...)` directly. The `run_collection` entry point is the chokepoint that owns CollectionJob creation and HAS_JOB linking before the task is dispatched; bypassing it would create a CollectionJob-less task that has nowhere to record its lifecycle.

A task worker process executes the task outside the request-response lifecycle. The task resolves the on-grid `Collector`, resolves the registered collector class from `collector_registry`, builds `CollectorConfig`, instantiates the class, and calls `run()`. The task body owns CollectionJob lifecycle transitions — RUNNING at task start, SUCCESSFUL/FAILED at task end (see `req-tap-cares-collector-job-sole-writer`).

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
| req-tap-cares-collector-task-execution-4 | Resolve In Worker | Implemented | The worker resolves Collector state and collector class registration after task execution begins. | Inside `run_collector`: looks up Collector + CollectionJob via service-layer reads (or ORM for INTERNAL_ONLY types), then calls `get_collector(registry_key)`. |
| req-tap-cares-collector-task-execution-5 | No Nested Subprocess In v0 | Implemented | v0 does not require the task worker to spawn a second collector subprocess. | |
| req-tap-cares-collector-task-execution-6 | Enqueue Only Via run_collection | Proposed | `run_collector.enqueue(...)` is called only from `run_collection`. No other code path in `tap_cares` or in plugins enqueues the task directly. | Enforced by convention; bypassing `run_collection` would produce a CollectionJob-less task with no lifecycle record. |

## Collector Read Boundary
----
RID: `req-tap-cares-collector-read-boundary`
Status: `Refactoring`

Collector modules must not mutate TAP graph state through arbitrary write paths, and must not mutate `CollectionJob` at all.

Collectors gather data and perform collector-specific interpretation. The `run_collection` entry point and the `run_collector` task body own grid writes for job state, status, and accumulated outputs (see `req-tap-cares-collector-job-sole-writer`). Collector modules may read TAP state only through approved search/read surfaces.

The initial read path should favor TAP search APIs and service-layer read operations. This keeps collector reads aligned with future authorization, dimensions, and security policy work.

For collection results, the approved mutation path is the GRIFT import surface defined in [Collector GRIFT Import Surface](#collector-grift-import-surface). This is an explicit carve-out: collector modules may cause grid mutation by submitting a GRIFT batch through the approved import path — that submission writes Batch + entity rows to the grid through `grift_import`, but it does **not** write to the calling `CollectionJob`. Tracking of imported batch IDs accumulates on the collector instance and is persisted to `CollectionJob.grift_batches` by the task body at terminal state, not by `self.submit_grift(...)` itself.

Collector modules should not import TAP models, call generic write services, call `write_batch()` directly, or otherwise bypass GRIFT import semantics. They must not mutate `CollectionJob` even through the helpers' previous signatures — the new helpers do not accept a `job` parameter and the helpers cannot reach a CollectionJob without one.

Because v0 collector code still runs as Python inside a Django task worker process, this requirement is initially a contract and design constraint rather than a full sandbox. Stronger enforcement is tracked in [Strict Collector Isolation](#strict-collector-isolation).

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-collector-read-boundary-1 | No Mutation Outside GRIFT | Implemented | Collector modules are prohibited by contract from directly creating, updating, or deleting TAP-managed nodes or edges outside the approved GRIFT import surface. | GRIFT import is the explicit exception (`CollectorBase.submit_grift`). |
| req-tap-cares-collector-read-boundary-2 | Approved Read Surfaces | Implemented | Collector modules read TAP state through approved search/read surfaces rather than ad hoc ORM access. | Contract; not enforced at runtime in v0 (see -5). |
| req-tap-cares-collector-read-boundary-3 | Runtime Owns Job Writes | Proposed | `run_collection` and the `run_collector` task body are the sole writers of `CollectionJob` rows. Collector modules cannot reach a CollectionJob through the helpers; collector results accumulate on the collector instance and are persisted by the task body. | See `req-tap-cares-collector-job-sole-writer`. |
| req-tap-cares-collector-read-boundary-4 | Future Auth Alignment | Implemented | Collector read design must remain compatible with future authorization and dimension-scoped security. | |
| req-tap-cares-collector-read-boundary-5 | Enforcement Gap Named | Implemented | The spec explicitly recognizes that v0 in-process Python cannot fully sandbox collector code. | |

## Collector GRIFT Import Surface
----
RID: `req-tap-cares-collector-grift-import`
Status: `Refactoring`

Collector result mutations must route through TAP's GRIFT import surface.

GRIFT import is the top-most exposed grid ingestion affordance for batch-shaped interchange. It sits above the lower-level service batch plumbing: the importer validates the GRIFT document, applies GRIFT batch identity and ordering rules, decides create-versus-replace behavior, handles importer diagnostics, and then executes the resulting service-layer write batch.

In v0, collector instances submit collected results through `CollectorBase.submit_grift(document)` — a method on the collector base class that calls the in-process `grift_import()` and accumulates the resulting batch IDs on the collector instance. The collector contract treats GRIFT import as the approved result submission boundary. Collector modules must not call lower-level mutation primitives such as `write_batch()`, node/edge write helpers, direct ORM saves, or direct `Entity` updates.

#### Signature change from v0-pre-refactor

The helper previously took a `job` parameter and wrote `CollectionJob.grift_batches` inline. The new shape removes both:

```python
# In CollectorBase
def submit_grift(self, document) -> GriftImportResult:
    result = grift_import(document, ...)
    self.grift_batches["imported"].extend(b.batch_entity_id for b in result.imported_batches)
    self.grift_batches["skipped"].extend(b.batch_entity_id for b in result.skipped_batches)
    return result
```

`self.grift_batches` is an instance-level accumulator. The task body persists the accumulated dict to `CollectionJob.grift_batches` in a single patch at terminal state (see `req-tap-cares-collector-job-sole-writer`).

This removes the previous staleness pattern where `submit_collector_grift` and the task body's lifecycle saves both wrote to the same row through separate ORM instances.

#### Job correlation

`CollectionJob.grift_batches` carries `{"imported": [...], "skipped": [...]}` after the task completes. Each list is the union of batch IDs across all `submit_grift` calls in the run. Successful empty runs produce empty lists. Failed runs produce empty lists (since the task body persists from the same accumulator regardless of terminal status; if a block flag aborted before any submission, the lists are empty).

Future strict isolation may replace the in-process call with a TAP API result-submission endpoint. That endpoint should preserve the same contract: collector code submits GRIFT; TAP validates, authorizes, imports, records provenance, and returns structured import results.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-collector-grift-import-1 | GRIFT Is Result Boundary | Implemented | Collector result mutations route through GRIFT import rather than ad hoc grid writes. | `CollectorBase.submit_grift` wraps `grift_import()`. |
| req-tap-cares-collector-grift-import-2 | v0 In-Process Import Allowed | Implemented | v0 collector execution uses in-process `grift_import()` through `CollectorBase.submit_grift`. | |
| req-tap-cares-collector-grift-import-3 | No Raw write_batch | Implemented | Collector modules do not call `write_batch()` or lower-level node/edge mutation helpers directly. | Contract; not enforced at runtime in v0. |
| req-tap-cares-collector-grift-import-4 | Method On CollectorBase | Proposed | `submit_grift` is a method on `CollectorBase` taking `(self, document)` rather than a free helper taking `(job, document)`. It does not receive or mutate `CollectionJob`. | Removes the v0-pre-refactor multi-writer pattern. |
| req-tap-cares-collector-grift-import-5 | Instance-Level Accumulator | Proposed | Imported and skipped batch IDs accumulate in `self.grift_batches` on the collector instance. The task body persists the dict to `CollectionJob.grift_batches` once at terminal state. | |
| req-tap-cares-collector-grift-import-6 | Job Correlation | Proposed | `CollectionJob.grift_batches` carries `{"imported": [...], "skipped": [...]}` populated by the task body from the collector instance's accumulator. | |
| req-tap-cares-collector-grift-import-7 | Future API Compatible | Implemented | The v0 contract remains compatible with replacing in-process import with an API-based GRIFT submission surface under strict isolation. | `submit_grift` takes a document and returns a `GriftImportResult`; replacing the in-process call with an API round trip changes only the helper internals. |

## CollectionJob Model
----
RID: `req-tap-cares-collector-job-model`
Status: `Refactoring`

`CollectionJob` is the on-grid execution record for one collector run.

A `Collector` is the root/capability node. A `CollectionJob` is a subordinate run instance that records the current lifecycle state of one attempted execution of that collector. The job exists so humans, management surfaces, schedulers, and future agents can see that collector execution is happening on the grid rather than inside an invisible background subsystem.

`CollectionJob` must be implemented as a standard TAP-managed `BaseModel` node using the model-building skill at `tap_grid/skills/add-model/SKILL.md`. The model should follow ordinary TAP model conventions rather than re-specifying boilerplate in this requirement.

`CollectionJob` declares `INTERNAL_ONLY: ClassVar[bool] = True` per `req-grid-entity-internal`. Generic `create_node` / `patch_node` / `replace_node` / `delete_node` and GRIFT import all reject the `collection_job` entity type. The sole legal creator is `run_collection(...)` (see [Run Collection Entry Point](#run-collection-entry-point)), which uses `_create_node_internal` from `tap_grid.services`. The sole legal post-creation mutator is the `run_collector` task body (RUNNING transition at task start, terminal-state patch at task end); collector code never sees a CollectionJob handle — see [CollectionJob Sole-Writer Invariant](#collectionjob-sole-writer-invariant).

CollectionJob-specific model requirements:

- `CollectionJob` has a human-readable `name`.
- `CollectionJob` has a plain-text `description`.
- `CollectionJob` has a `status` `CharField` driven by a `models.TextChoices` enum (see [CollectionJob Lifecycle Status](#collectionjob-lifecycle-status)).
- `CollectionJob` has a `task_result_id` `CharField(max_length=128, blank=True, default="")`. This stores the `TaskResult.id` returned by Django's Tasks API — a backend-defined string, **not** a UUID. The built-in `immediate` and `dummy` backends use 32-char random strings (`get_random_string(32)`); other backends may differ. `max_length=128` is comfortably above the current built-in but small enough to remain index-friendly. Empty string represents "not yet enqueued / enqueue raised."
- `CollectionJob` has `enqueued_at`, `started_at`, and `finished_at` `DateTimeField(null=True, blank=True)` timestamps; each is populated as the corresponding lifecycle transition occurs.
- `CollectionJob` has an `error_summary` `CharField(max_length=2048, blank=True, default="")` field for the at-a-glance terminal-failure one-liner. Structured per-event detail (codes, messages, context) lives in `results` (below); `error_summary` is the human-facing single line that shows up wherever the job is summarized.
- `CollectionJob` has a `results` `JSONField` carrying the structured per-event log for this run (see [CollectionJob Results Log](#collectionjob-results-log) below).
- `CollectionJob` has a `grift_batches` `JSONField` carrying `{"imported": [<UUIDv7>...], "skipped": [<UUIDv7>...]}` — the lists of GRIFT batch entity IDs the run imported and skipped. Populated by the task body at terminal state from the collector instance's accumulator (see `req-tap-cares-collector-grift-import-5`).
- The `CollectionJob` display projection emits both the raw `status` value and a `status_display` field carrying the human-readable label (via Django's auto-generated `get_status_display()`).
- The v0 default dimension is `{"tap_cares": "collection_job"}`.

The job does not snapshot `Collector.collector_registry` in v0. The job's collector provenance comes from the `Collector --HAS_JOB--> CollectionJob` edge. If immutable runner snapshots become necessary, that should be added as a separate requirement.

### CollectionJob Results Log

The `results` field is the structured per-event log for one collector run. It captures successes, warnings, and errors uniformly so consumers (UIs, audits, future Action rules) have a single place to read what happened.

#### Shape

```python
results = models.JSONField(default=_empty_results_dict, blank=True)

def _empty_results_dict() -> dict[str, list]:
    return {"info": [], "warn": [], "error": []}
```

Top-level shape is **pre-defined arrays per level**, never a flat list with embedded `level` fields. This keeps "show me errors" / "did anything warn?" as direct lookups (`results["error"]`) rather than filter operations, and keeps the JSON Schema strict — no level outside the three is permitted.

Per-entry shape (same for all three buckets):

```json
{
  "site":    "<UUIDv7>",
  "code":    "<UPPER_SNAKE>",
  "message": "<human-readable prose>",
  "context": { /* free-form */ }
}
```

| Field | Purpose |
| --- | --- |
| `site` | UUIDv7 hardcoded at the helper callsite, generated via `scripts/uuid7`. Identifies the exact line of code that emitted the entry. Survives refactors; grep the codebase for the UUID to locate the callsite. |
| `code` | Machine-readable category (`MASS_DELETION`, `UPSTREAM_OVERSIZED`, `RUN_COMPLETED`, …). Stable across runs and rewordings; what filtering and future Action rules key off. |
| `message` | Human-readable prose for this run. Includes specifics (counts, ratios, offending fragments); the `code` stays stable while `message` describes the particular occurrence. |
| `context` | Free-form structured payload. Empty object when none. Collector-defined keys; consumers treat unknown keys as opaque. |

All four fields are **required** in stored entries. The pinned JSON schema (below) rejects entries missing any of them.

#### Pinned schema

The shape is pinned at `tap_cares/schemas/collection_job_results.schema.json` per the JSON Schema Policy in `MEMORY.md`. The `record_*` helpers validate every entry against this schema before append; malformed entries raise rather than silently writing bad data.

#### Service helpers

The result-recording helpers are **methods on `CollectorBase`**, not free functions, and they operate on instance-level accumulator state rather than on a `CollectionJob` row:

```python
class CollectorBase(ABC):
    def __init__(self, config: CollectorConfig) -> None:
        self.config = config
        self.results: dict[str, list] = {"info": [], "warn": [], "error": []}
        self.grift_batches: dict[str, list] = {"imported": [], "skipped": []}

    def record_info(self, site: str, code: str, message: str, *, context: dict | None = None) -> None: ...
    def record_warn(self, site: str, code: str, message: str, *, context: dict | None = None) -> None: ...
    def record_error(self, site: str, code: str, message: str, *, context: dict | None = None) -> None: ...
```

Each helper:

1. Builds the entry from the four arguments (defaulting `context` to `{}` if `None`).
2. Validates the entry against the pinned schema.
3. Appends to `self.results[<level>]`.

**No database write happens during `record_*`.** The accumulated `self.results` dict is persisted to `CollectionJob.results` by the task body in a single patch at terminal state (see [CollectionJob Sole-Writer Invariant](#collectionjob-sole-writer-invariant)). This is the structural fix that removes the v0-pre-refactor multi-writer / staleness pattern: there is exactly one writer to CollectionJob, and that writer reads from a single in-memory accumulator at the moment of write.

Collectors never manipulate `CollectionJob.results` directly; they always go through the helpers. `site` is **required positional** — forgetting it raises `TypeError`, which keeps every entry traceable to a single line of source.

The `tap_cares/results.py` module that previously exposed `record_info(job, ...)` free functions is being removed as part of the refactor.

#### Site UUID uniqueness

A repository-wide pytest scans every `self.record_info(…)` / `self.record_warn(…)` / `self.record_error(…)` call literal across collector subclasses and asserts that no two callsites share the same UUIDv7. Catches copy-paste mistakes at CI time. The test lives in `tap_cares/tests/test_results_site_uniqueness.py` (or migrates with the helpers; the test continues to scan for the same UUIDv7-uniqueness invariant under the new call shape).

#### `error_summary` vs `results["error"]`

The two coexist with distinct roles:

- `error_summary` (CharField 2048) — the at-a-glance one-liner for a terminal failure. The collector sets it explicitly when failing the run. Renders wherever the job is summarized (admin list, job detail header).
- `results["error"]` — the full structured detail. One entry per discrete error event, each with its own site / code / context. Renders in the "what went wrong" expanded view.

If a run produces multiple error events, `error_summary` reflects the most important one (collector's call); `results["error"]` carries the full set.

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
| req-tap-cares-collector-job-model-9 | Results Field Exists | Implemented | `CollectionJob` has a `results` `JSONField` defaulting to `{"info": [], "warn": [], "error": []}` (via a callable default helper). | |
| req-tap-cares-collector-job-model-10 | Pre-Defined Severity Buckets | Implemented | The top-level shape of `results` is three pre-defined arrays keyed `info` / `warn` / `error`. No flat-array form; entries never carry a `level` field (severity is implied by which bucket holds them). | |
| req-tap-cares-collector-job-model-11 | Four-Field Entry Shape | Implemented | Every result entry has exactly four required fields: `site` (UUIDv7), `code` (UPPER_SNAKE), `message` (string), `context` (object). No other fields permitted. | |
| req-tap-cares-collector-job-model-12 | Pinned Results Schema | Implemented | The results shape is pinned at `tap_cares/schemas/collection_job_results.schema.json` with `additionalProperties: false` at both the top-level and per-entry. | |
| req-tap-cares-collector-job-model-13 | record_* Are Instance Methods | Proposed | The result-recording helpers are methods on `CollectorBase` (`self.record_info(site, code, message, *, context=None)` and the `warn` / `error` siblings). Each validates against the pinned schema and appends to `self.results[<level>]`. They do not accept a `CollectionJob` and do not write to the database. | Replaces the previous free-function shape in `tap_cares/results.py`. |
| req-tap-cares-collector-job-model-14 | Site Is Required Positional | Implemented | `site` is a required positional argument on the helpers. Calls missing it raise `TypeError` at runtime / fail type-checking, ensuring every stored entry traces to one line of source. | |
| req-tap-cares-collector-job-model-15 | Site UUID Uniqueness Test | Implemented | A repository-wide pytest scans every `self.record_info` / `self.record_warn` / `self.record_error` callsite across collector subclasses and asserts no two share the same `site` UUID. | `tap_cares/tests/test_results_site_uniqueness.py`. |
| req-tap-cares-collector-job-model-16 | error_summary Stays Distinct | Implemented | `error_summary` (CharField 2048) survives as the at-a-glance terminal-failure one-liner; structured per-event detail lives in `results["error"]`. The two are complementary, not redundant. | |
| req-tap-cares-collector-job-model-17 | INTERNAL_ONLY | Proposed | `CollectionJob.INTERNAL_ONLY = True`. Generic `create_node` / `patch_node` / `replace_node` / `delete_node` and GRIFT import all reject the `collection_job` entity type. | |
| req-tap-cares-collector-job-model-18 | run_collection Is Sole Creator | Proposed | The only legal path that creates a CollectionJob row is `run_collection(...)` (see [Run Collection Entry Point](#run-collection-entry-point)), which uses `_create_node_internal` from `tap_grid.services`. | |
| req-tap-cares-collector-job-model-19 | Accumulator Pattern For results | Proposed | The collector instance accumulates result entries in `self.results` during `run()`. The task body persists the accumulated dict to `CollectionJob.results` in a single patch at terminal state. No mid-run writes to the row. | Resolves the v0-pre-refactor staleness pattern. |
| req-tap-cares-collector-job-model-20 | grift_batches Field | Proposed | `CollectionJob.grift_batches` is a `JSONField` with shape `{"imported": [<UUIDv7>...], "skipped": [<UUIDv7>...]}`, populated by the task body at terminal state from `collector_instance.grift_batches`. | Field was present in v0-pre-refactor but undeclared in the spec; declaring it now. |

## CollectionJob Sole-Writer Invariant
----
RID: `req-tap-cares-collector-job-sole-writer`
Status: `Proposed`

Exactly one piece of code mutates a `CollectionJob` row in a given run, and it does so in a small, predictable set of moments.

#### Writers

| Phase | Writer | Operation | Fields written |
| --- | --- | --- | --- |
| Run kickoff | `run_collection` | `_create_node_internal("collection_job", ...)` | `name`, initial `status` (`READY`), `enqueued_at`, default fields |
| Task start | `run_collector` task body | `_patch_node_internal` (or service-layer patch routed through `_create_node_internal`'s sibling for INTERNAL_ONLY types) | `status` (`RUNNING`), `started_at`, `task_result_id` |
| Task success | `run_collector` task body | one patch | `status` (`SUCCESSFUL`), `finished_at`, `results`, `grift_batches` |
| Task failure | `run_collector` task body | one patch | `status` (`FAILED`), `finished_at`, `error_summary`, `results`, `grift_batches` |

Three writes per run, total. None of them race. The task body holds no long-lived ORM instance across `collector.run()`; each patch is a fresh service-layer call.

#### What's not a writer

- Collector code is **not** a writer. It accumulates `self.results` and `self.grift_batches` in-memory; the task body persists those accumulators at terminal state.
- `record_info` / `record_warn` / `record_error` are **not** writers. They mutate `self.results` on the collector instance.
- `submit_grift` is **not** a writer of CollectionJob. It writes grid state through `grift_import` (which creates Batch + entity rows), and it appends to `self.grift_batches` on the collector instance. It does not touch the CollectionJob row.
- `enqueue_collection` is gone; its replacement `run_collection` is the kickoff writer, but it does not write to the row again after `.enqueue()` returns. The redundant post-enqueue `task_result_id` fallback that existed in v0-pre-refactor is removed; the task body writes `task_result_id` at task start.

#### Why this matters

The v0-pre-refactor code had at least seven write sites touching `CollectionJob` across four files, using `update_fields=[...]` as a poor man's column-level lock against a stale ORM instance held in `tasks.py` across the duration of `collector.run()`. The pattern worked under careful interleaving but fell apart under any scrutiny.

The sole-writer invariant replaces that pattern with a much simpler structural property: the task body owns the row, holds it for the minimum time required, and persists everything else (results, grift batches) from in-memory accumulators in one shot. Read-modify-write windows are vanishingly small; staleness has nowhere to live.

#### One known limit

If the task itself dies hard (segfault, OOM, `kill -9`), neither terminal patch fires and the job sits at `RUNNING` forever. This is a Django Tasks reaping concern that exists for any task system; a separate "stuck job sweep" is the right answer and is out of scope for this requirement. The sole-writer invariant does not pretend to solve uncatchable process death.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-collector-job-sole-writer-1 | Three Writes Per Run | Proposed | A normal run produces exactly three writes to the CollectionJob row: kickoff (READY), task start (RUNNING), task end (SUCCESSFUL or FAILED). | |
| req-tap-cares-collector-job-sole-writer-2 | Task Body Is Sole Mid/End Writer | Proposed | After `run_collection` returns, the only writer to the CollectionJob row is the `run_collector` task body. | |
| req-tap-cares-collector-job-sole-writer-3 | Collector Code Holds No Job Handle | Proposed | The collector instance has access to `self.config.collection_job_entity_id` (an ID) but never receives or fetches a CollectionJob instance. Helpers do not take a `job` parameter. | |
| req-tap-cares-collector-job-sole-writer-4 | Accumulators Persist At Terminal | Proposed | `self.results` and `self.grift_batches` on the collector instance are persisted to `CollectionJob.results` and `CollectionJob.grift_batches` in the same terminal-state patch. | |
| req-tap-cares-collector-job-sole-writer-5 | No update_fields Gymnastics | Proposed | The task body uses ordinary service-layer patches; no `update_fields=[...]` workarounds for concurrent writers, because there are no concurrent writers. | |
| req-tap-cares-collector-job-sole-writer-6 | No Long-Lived Stale Instance | Proposed | The task body does not hold a `CollectionJob` ORM instance across `collector.run()`. Each patch operates on a fresh service-layer round trip. | |
| req-tap-cares-collector-job-sole-writer-7 | Stuck-Job Reaping Out Of Scope | Proposed | Uncatchable task death (segfault, OOM, kill -9) is acknowledged as an unsolved case; a separate stuck-job sweep is the right fix and is out of scope. | |

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

tap-cares collector execution owns status updates. `run_collection` creates the job in `READY`. The `run_collector` task body transitions to `RUNNING` at task start and to `SUCCESSFUL` or `FAILED` at task end. These are the only writers — see [CollectionJob Sole-Writer Invariant](#collectionjob-sole-writer-invariant). The collector module class does not update job status directly and does not receive a CollectionJob handle.

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

## Collector Failure Mode
----
RID: `req-tap-cares-collector-failure-mode`
Status: `Proposed`

How a collector signals a failed run is a framework convention, not a per-collector decision. Individual collectors specify *which conditions* trigger failure (their safety checks, threshold values, vocabulary of error codes) but they all use this single protocol to communicate failure to the runtime.

#### Failure protocol (collector side)

To fail a run, a collector:

1. Calls `self.record_error(site, code, message, *, context=...)` to accumulate one or more structured error entries in `self.results["error"]`. Each entry traces to a specific source location via its UUIDv7 `site`.
2. Optionally sets `self.error_summary` to a one-line description of the most important failure event. This is the human-facing at-a-glance string that renders in admin lists and job detail headers. If the collector doesn't set it, the task body derives a fallback from the raised exception.
3. Raises a Python exception out of `run()`. The exception terminates the run; control returns to the task body, which writes terminal state.

Whether *any particular* `record_error` call must be paired with a raise is a per-collector decision. The KSI collector treats every recorded error as block-class and aborts on the first one; another collector could record multiple errors and continue, raising only when a threshold is reached. The framework's `record_error` does not auto-raise.

#### Failure protocol (runtime side)

The `run_collector` task body:

1. Catches any exception raised by `instance.run()`.
2. Writes a single FAILED-state patch to `CollectionJob` per `req-tap-cares-collector-job-sole-writer`: `status=FAILED`, `finished_at`, `error_summary` (collector-set if present, otherwise derived from the exception's class and message), `results` (the full accumulator including all error entries), `grift_batches` (whatever was submitted before the abort).
3. Re-raises so Django Tasks' own failure machinery sees the failure.

#### What this guarantees

- Exactly one terminal-state write to `CollectionJob` per failed run.
- Structured failure detail (codes, messages, context, source sites) lives in `results["error"]`.
- At-a-glance failure summary lives in `error_summary`.
- Both come from the same accumulator at the same write moment — no risk of `results["error"]` and `error_summary` disagreeing about what failed.

#### What this does not guarantee

- That a particular error code halts the run. That's per-collector policy; collectors signal "abort" by raising, not by calling `record_error`.
- That all collected results survive uncatchable process death (segfault, OOM, `kill -9`). The task body never runs in that case; the job sits at `RUNNING` until a future stuck-job sweep reaps it. See `req-tap-cares-collector-job-sole-writer-7`.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-collector-failure-mode-1 | record_error + Raise Is The Protocol | Proposed | A collector fails a run by calling `self.record_error(...)` to accumulate structured detail and then raising an exception. The task body catches and persists. | |
| req-tap-cares-collector-failure-mode-2 | Single Terminal Write | Proposed | Failure produces exactly one terminal-state patch to `CollectionJob`, carrying status=FAILED plus the full accumulator. | See `req-tap-cares-collector-job-sole-writer`. |
| req-tap-cares-collector-failure-mode-3 | error_summary Source Of Truth | Proposed | `error_summary` is collector-set via `self.error_summary = "..."`; the task body persists it. If the collector did not set it, the task body derives a fallback from the raised exception. | |
| req-tap-cares-collector-failure-mode-4 | Framework Does Not Auto-Halt | Proposed | `record_error` is a pure accumulator call; it does not raise. Per-collector policy decides whether a recorded error halts the run. | |
| req-tap-cares-collector-failure-mode-5 | Re-Raise For Task Backend | Proposed | The task body re-raises after writing FAILED state so Django Tasks' own failure machinery sees the failure. | |
| req-tap-cares-collector-failure-mode-6 | Plugin Specs Reference This | Proposed | Per-collector safety specs (KSI, future Emitter receivers, etc.) describe their own check vocabulary and policy but reference this requirement for the failure-signaling protocol instead of re-specifying mechanics. | |

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

## Shared Collector Runtime Helpers
----
RID: `req-tap-cares-collector-runtime-helpers`
Status: `Backlog`

Standard collector tasks — cloning a git repo, fetching a URL, unpacking an archive, parsing a known file format — should be available as shared helpers so each new collector does not reimplement them. The Collector Module Class spec already nods at this direction ("Reusable behavior belongs in tap-cares collector runtime helpers and shared base classes, not in plugin-specific factory setup"); this requirement names the surface and defers its construction until concrete duplication appears.

The proposed shape is composition-first, not inheritance:

- Helpers live in a `tap_cares/helpers/` package, one module per concern (e.g. `git.py`, `http.py`, `archive.py`).
- Collectors discover helpers through ordinary Python imports (`from tap_cares.helpers.git import clone`). No registry — helpers are utilities, not pluggable interfaces, and do not need to be addressable from grid data the way collectors are.
- Helpers are functions returning small dataclasses. No singletons, no module-level state.
- Helpers accept what they need as keyword arguments (tmpdir paths, log sinks, secrets, retry policy) rather than reaching into a global context.

Plugin-local helpers may live in `plugins/<slug>/helpers/`. They graduate to `tap_cares/helpers/` when a second collector needs the same capability. This "wait for N=2" discipline keeps the shared surface small and grounded in real reuse.

An open design question that this requirement deliberately defers: whether collectors should receive a `CollectorContext` object that bundles tmpdir lifecycle, a log sink that feeds `CollectionJob.results`, secret resolution, and retry/rate-limit policy. The first two helpers (likely `git.clone` and `http.fetch`) should accept raw kwargs; the context shape, if it materializes, should be crystallized only after three concrete collectors agree on what they actually need passed in.

This work is explicitly **not blocking v0**. The first concrete collector (FedRAMP 20x KSI) hardcodes its behavior; helpers become valuable when the second and third collectors arrive and start duplicating each other. Until then, prefer copy-paste over premature abstraction.

A subclass-based `CollectorBase` extension (e.g. a `GitCollectorBase` that owns clone + checkout lifecycle) is explicitly **not** the v0 direction. Inheritance designed off a single concrete collector tends to misfit the next one; the helper-composition path stays open to crystallizing into a base class later, but does not force the shape early.

### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-tap-cares-collector-runtime-helpers-1 | Backlog Requirement Exists | Backlog | Shared collector runtime helpers are tracked as a named backlog requirement. | |
| req-tap-cares-collector-runtime-helpers-2 | Helpers Package Location | Backlog | Shared collector helpers live in `tap_cares/helpers/`, one module per concern (e.g. `git.py`, `http.py`, `archive.py`). | |
| req-tap-cares-collector-runtime-helpers-3 | Plain Import Discovery | Backlog | Collectors discover helpers through ordinary Python imports. No registry, no scope:key lookup, no grid-driven helper resolution. | |
| req-tap-cares-collector-runtime-helpers-4 | Function-First Shape | Backlog | Helpers are functions returning small dataclasses. Reusable subclass bases of `CollectorBase` are not added until at least three concrete collectors demonstrate a shared lifecycle. | |
| req-tap-cares-collector-runtime-helpers-5 | Kwargs Not Globals | Backlog | Helpers accept tmpdir paths, log sinks, secrets, and policy via keyword arguments rather than reaching into a shared global or module-level context. | |
| req-tap-cares-collector-runtime-helpers-6 | CollectorContext Deferred | Backlog | A bundled `CollectorContext` object passed into collectors is explicitly deferred until at least three concrete collectors agree on its contents. | |
| req-tap-cares-collector-runtime-helpers-7 | Promotion On Reuse | Backlog | Plugin-local helpers in `plugins/<slug>/helpers/` are promoted to `tap_cares/helpers/` only when a second collector adopts them. | |
| req-tap-cares-collector-runtime-helpers-8 | Not Required For v0 | Backlog | v0 collector execution is not required to use or provide shared helpers. The first concrete collector (FedRAMP 20x KSI) hardcodes its behavior. | |

## Future

- Define collection job status/log/error nodes and edges beyond coarse lifecycle status.
- Define richer collection result records and job-to-batch graph relationships.
- Define management surfaces for collectors and collection jobs.
- Build out shared collector runtime helpers once a second concrete collector demonstrates the duplication pattern (see [Shared Collector Runtime Helpers](#shared-collector-runtime-helpers)).
