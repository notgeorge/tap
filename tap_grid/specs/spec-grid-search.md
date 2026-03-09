# Grid Search Specification

## Philosophy

Search objects are reusable query definitions stored on the grid as first-class entities. They allow panels and other capabilities to reference a stable search definition instead of embedding ad hoc query logic throughout the system.

A Search must be expressive enough to retrieve useful graph-native data, but narrow enough that execution remains understandable, deterministic, and safe. In v1, that means a small set of execution modes, one-hop traversal only, deterministic ordering, and execution exclusively through the service layer.

Searches always return a graph-shaped result envelope. Even when a consumer is primarily interested in nodes or primarily interested in edges, the result is still represented as `nodes` plus `edges`. That keeps the output compatible with future chaining, composition, and graph-native consumers.

## Goals

|    |                  |                                                                                                      |
| :---: | ---           | ---                                                                                                  |
| 1. | Reusable          | Store search definitions once and reference them from panels and other capabilities                  |
| 2. | Safe              | Restrict execution to read-only, service-layer-controlled access against TAP-managed models          |
| 3. | Graph-Native      | Return results as graph data (`nodes` and `edges`) rather than forcing a flat tabular contract      |
| 4. | Extensible        | Support multiple execution modes without hard-coding all query logic into one implementation         |
| 5. | Deterministic     | Require stable ordering and explicit pagination behavior so repeated execution is predictable         |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-grid-search-obj | [Search Objects](#search-objects) | Implemented | Search is a first-class grid entity with reusable query metadata |
| req-grid-search-exec | [Search Execution](#search-execution) | Implemented | Searches execute through a shared service layer only |
| req-grid-search-module | [Module Search Mode](#module-search-mode) | Implemented | Code-backed searches resolve a registered module runner via `ScopedRegistry` |
| req-grid-search-orm | [ORM Search Mode](#orm-search-mode) | Implemented | Declarative ORM DSL with one-hop traversal and deterministic ordering |
| req-grid-search-results | [Search Results](#search-results) | Proposed | Searches always return the canonical 4-key graph envelope (`nodes`, `edges`, `info`, `warnings`) |
| req-grid-search-readonly.sec | [Search Read-Only Execution](#search-read-only-execution) | Implemented | Security requirement enforcing that searches cannot mutate TAP data |
| req-grid-search-authz.sec | [Search Authorization](#search-authorization) | Backlog | Deferred security requirement for search-specific authorization and access controls |

---

### Search Objects
----
RID: `req-grid-search-obj`
Status: `Implemented`

A Search object is the backing entity for a reusable TAP query. It stores the query definition, parameter schema, return preferences, and pagination configuration needed for execution through the TAP service layer.

#### Fields

| Field | Type | Required | Notes |
| --- | --- | :---: | --- |
| `title` | CharField | Yes | Human-readable search name |
| `description` | TextField | No | What the search is intended to retrieve |
| `search_type` | CharField | Yes | Execution mode. In v1: `module` or `orm` |
| `root` | CharField | Yes | Search root. In v1: `node` or `edge` |
| `definition` | JSONField | Yes | Execution-mode-specific search definition |
| `input_schema` | JSONField | No | JSON Schema for domain-specific execution inputs (e.g. a `character_id` parameter). Not used for pagination — `limit` and `offset` are separate execution kwargs. |
| `returns` | JSONField | No | Result preference object controlling primary side, included graph members, and projections |
| `default_limit` | IntegerField | No | Default page size for this search. Null means unpaginated by default. |
| `max_limit` | IntegerField | No | Maximum page size enforced at execution time. Null means uncapped. |

#### Status Details
`Search` model implemented in `tap_grid/models.py` with all fields, `FIELD_SCHEMAS` validation, and cross-field `validate()` hook. Migration `0007_search.py` applied. Tests in `tap_grid/tests/test_search_model.py`.

#### Implementation
A Search is a TAP-managed model derived from `BaseModel`, and therefore hangs off the entity spine like other first-class grid objects.

`search_type` determines how `definition` is interpreted:
- `module` uses a registered search runner key.
- `orm` uses a declarative ORM DSL.

`root` identifies whether the search begins from nodes or edges:
- `node`
- `edge`

`input_schema` is JSON Schema. When present, execution inputs are validated against it before any search runner or ORM logic is invoked.

`returns` is a preference object, not an arbitrary output-shape contract. Search results are always returned in a graph envelope, but `returns` can specify:
- `primary`: `nodes` or `edges`
- `include`: `nodes`, `edges`, or `both`
- optional field projections for `nodes` and `edges`

`default_limit` and `max_limit` are typed integer fields on the model rather than a JSON blob. When a caller provides `limit` or `offset` at execution time, the service layer clamps `limit` to `max_limit` if it is set.

Cross-field invariants on `search_type`, `root`, and `definition` are enforced via the whole-record `validate()` hook (see `req-grid-entity-validation`). For example, a `module` definition that contains unrecognized extra fields raises `ValidationError` at save time.

#### Development
Keep the object surface small. Mode-specific complexity belongs inside `definition`, not in a large set of top-level fields that only apply to one execution mode.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-search-obj-1 | Search Is First-Class Entity | Implemented | Search is represented by its own TAP-managed model derived from `BaseModel`. | |
| req-grid-search-obj-2 | Canonical Search Type Field | Implemented | Search stores `search_type` and supports `module` and `orm` in v1. | |
| req-grid-search-obj-3 | Canonical Root Field | Implemented | Search stores `root` and supports `node` and `edge` in v1. | |
| req-grid-search-obj-4 | Definition Stored as JSON | Implemented | Search stores execution-specific query definition in `definition`. | |
| req-grid-search-obj-5 | Input Schema Uses JSON Schema | Implemented | When `input_schema` is present, execution inputs are validated against it before search execution. | |
| req-grid-search-obj-6 | Returns Is Preference Object | Implemented | `returns` controls primary side, included graph members, and projections, but does not replace the canonical graph result envelope. | |
| req-grid-search-obj-7 | Pagination Fields Are Typed | Implemented | Search stores pagination defaults in typed `default_limit` and `max_limit` IntegerFields (not a JSON blob). `null` means unpaginated / uncapped. | |
| req-grid-search-obj-8 | Module Definition Is Constrained | Implemented | For `search_type="module"`, v1 `definition` supports only a fully-qualified `runner_key`. | |
| req-grid-search-obj-9 | Cross-Field Validation via validate() | Implemented | `search_type`-specific `definition` constraints (e.g. required fields, disallowed extra fields) are enforced in the whole-record `validate()` hook. | |

#### Future
Consider supporting inline code stored directly on the Search node. This requires a separate execution-safety design and is explicitly deferred.

Consider extending `returns` with richer projection / formatting controls once panel and API consumers establish a concrete need.

---

### Search Execution
----
RID: `req-grid-search-exec`
Status: `Implemented`

All searches execute through a shared TAP service-layer entry point. Consumers such as panels, pages, APIs, and future chained searches do not execute search logic directly.

#### Status Details
Service layer implemented in `tap_grid/search_service.py`. `execute_search()` handles input validation, limit clamping, dispatch to mode executors (stubs for orm/module until Phases 4–5), envelope normalization, and info/warnings population.

#### Implementation
Search execution is service-layer only.

The shared service layer is responsible for:
- loading the Search object
- validating execution inputs against `input_schema`
- dispatching to the correct execution mode
- resolving `module` runners from `definition.runner_key`
- validating that execution returns one of the canonical result envelopes
- enforcing deterministic ordering
- applying pagination behavior
- returning the canonical graph-shaped result envelope

Search scope is limited to TAP-managed models derived from `BaseModel`. Searches do not read arbitrary Django application tables.

Read-only execution requirements are specified in `req-grid-search-readonly.sec`.

Consumers call the service layer by reference to a Search object or Search identifier. They do not bypass it and invoke module runners or ORM definitions directly.

For `module` searches:
- `input_schema` validation occurs before runner dispatch
- the service layer resolves the runner from the persisted `definition.runner_key`
- the service layer validates the returned result envelope before returning it to callers

#### Development
This requirement exists so there is exactly one place to add future enforcement for authorization, rate limiting, pagination caps, observability, and execution controls.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-search-exec-1 | Service Layer Only | Implemented | Search execution is exposed through a shared TAP service-layer entry point. | |
| req-grid-search-exec-2 | Inputs Validated First | Implemented | Execution inputs are validated against `input_schema` before search logic runs. | |
| req-grid-search-exec-3 | TAP Model Scope Only | Implemented | Search execution is limited to TAP-managed models derived from `BaseModel`. | Excludes unrelated Django tables. |
| req-grid-search-exec-4 | Deterministic Ordering Required | Implemented | Search execution applies deterministic ordering before pagination or result return. | |
| req-grid-search-exec-5 | Canonical Result Envelope | Implemented | Search execution returns the canonical graph-shaped result envelope for every mode. | |
| req-grid-search-exec-6 | Module Runner Resolved From Definition Key | Implemented | For `search_type="module"`, execution resolves the runner from persisted `definition.runner_key`. | |
| req-grid-search-exec-7 | Runner Result Structure Validated | Implemented | Service-layer execution validates that module runner output matches one of the canonical result envelopes before returning it. | |

#### Future
Add service-layer enforcement for maximum page size once operational experience identifies the right cap.

Add search execution metrics, timing, and failure instrumentation.

---

### Search Read-Only Execution
----
RID: `req-grid-search-readonly.sec`
Status: `Implemented`

Search execution is a security-sensitive surface and must be enforced as read-only. Searches must not mutate TAP data, create records, update records, delete records, or trigger side effects that change persisted application state.

#### Status Details
This requirement separates read-only enforcement from general execution flow so the search security model is explicit and can be referenced independently by execution modes and future authorization work.

#### Implementation
All search modes execute under a read-only contract, enforced by a read-only database connection.

The service layer opens a read-only database connection for all search execution. This prevents writes at the database level rather than relying on author convention or code review. ORM searches compile to queries that run over this connection. Module runners also receive execution context bound to the read-only connection.

This means:
- searches do not create, update, or delete TAP-managed records
- searches do not mutate edge properties, entity properties, or other persisted model fields
- module runners execute under the same read-only connection constraint as declarative search modes
- future execution modes must satisfy this requirement before they are considered valid

This requirement is independent of authorization. A caller being authorized to execute a search does not grant permission to mutate data through search execution.

#### Development
Keeping read-only enforcement as its own security requirement makes it easier to reason about future SQL mode, inline code mode, and authorization work without burying core safety guarantees inside general execution prose.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-search-readonly.sec-1 | Searches Are Read Only | Implemented | Search execution must not mutate persisted TAP data. | |
| req-grid-search-readonly.sec-2 | Enforced Via Read-Only DB Connection | Implemented | The service layer opens a read-only database connection for all search execution. Writes are rejected at the database level, not just by convention. | |
| req-grid-search-readonly.sec-3 | Module Runners Use Read-Only Connection | Implemented | `module` search runners execute over the same read-only connection. They cannot bypass it via a separate Django connection. | |
| req-grid-search-readonly.sec-4 | Requirement Applies To Future Modes | Implemented | Any future search execution mode must satisfy the read-only requirement before adoption. | |
| req-grid-search-readonly.sec-5 | Separate From Authorization | Implemented | Read-only enforcement is required even when the caller is otherwise authorized to execute the search. | |

#### Future
Define concrete enforcement mechanisms for each execution mode, especially for future SQL-backed and inline-code search execution.

---

### Module Search Mode
----
RID: `req-grid-search-module`
Status: `Implemented`

`module` search mode resolves a registered search runner and delegates execution to that runner through a TAP registry-backed abstraction.

#### Status Details
This requirement formalizes code-backed search behavior without storing executable code directly on the Search object.

#### Implementation
A `module` search stores exactly one module-specific field in `definition`: `runner_key`.

`definition` shape in v1:

```json
{
  "runner_key": "tap_plugins.lotr.searches:character-artifacts"
}
```

Persisted `runner_key` values must be fully qualified in `scope:key` format.
Short keys are not allowed in stored Search definitions.
No additional module-specific definition fields are supported in v1.

Complete example:

```json
{
  "search_type": "module",
  "root": "node",
  "definition": {
    "runner_key": "tap_plugins.lotr.searches:character-artifacts"
  }
}
```

Module search runners are resolved through a first-class `ScopedRegistry`, following the registry patterns defined in `spec-grid-registry.md`.

The registry contract is:
- each runner registers under a scoped key
- duplicate registration of the same scoped key is a configuration error
- persisted searches store fully-qualified keys so runtime lookup is exact and unambiguous

In v1, module runners are plain callables.

The callable contract is:
- receives the Search object
- receives validated execution inputs
- returns one of the canonical search result envelopes

Canonical full result envelope:

```json
{
  "nodes": [...],
  "edges": [...]
}
```

Canonical paginated result envelope:

```json
{
  "count": 0,
  "limit": 25,
  "offset": 0,
  "results": {
    "nodes": [...],
    "edges": [...]
  }
}
```

Module runners execute through the search service layer. They do not bypass service-layer validation or future authorization enforcement.

Failure behavior:
- invalid `module` `definition` is a validation failure
- unresolved `runner_key` is an execution failure
- duplicate runner registration is a configuration failure
- invalid runner result envelope is an execution failure

Recommended exception names for later implementation:
- `InvalidSearchDefinitionError`
- `SearchRunnerNotFoundError`
- `SearchExecutionError`

#### Development
Module mode is the intentionally flexible option for searches that do not fit the declarative ORM DSL. It should remain explicit and registry-backed rather than resolving arbitrary import paths from entity data.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-search-module-1 | Runner Key Required | Implemented | `module` searches require `definition.runner_key`. | |
| req-grid-search-module-2 | Runner Key Fully Qualified | Implemented | Stored `runner_key` values must use fully-qualified `scope:key` format. | |
| req-grid-search-module-3 | Scoped Registry Resolution | Implemented | Module search runners are resolved through a `ScopedRegistry`. | |
| req-grid-search-module-4 | Duplicate Scoped Key Fails | Implemented | Duplicate registration of the same scoped runner key is a configuration error. | |
| req-grid-search-module-5 | Runner Receives Search And Inputs | Implemented | In v1, module runners are plain callables that receive the Search object and validated execution inputs. | |
| req-grid-search-module-6 | Runner Returns Canonical Result Envelope | Implemented | Module runners return one of the canonical full or paginated graph result envelopes. | |
| req-grid-search-module-7 | No Extra Definition Fields In V1 | Implemented | V1 `module` definitions support only `runner_key` and reject additional module-specific fields. | |

#### Future
Consider adding registry inspection and health checks for registered search runners.

---

### ORM Search Mode
----
RID: `req-grid-search-orm`
Status: `Implemented`

`orm` search mode uses a declarative JSON DSL that compiles to read-only TAP ORM queries. The v1 DSL is intentionally narrow: root selection, conjunctive filters, deterministic ordering, optional pagination, and at most one graph hop.

#### Status Details
This requirement defines the smallest ORM DSL that can support useful graph-native searches without drifting into an ad hoc traversal language.

#### Implementation
An `orm` search stores its query in `definition`.

Example shape:

```json
{
  "filters": {
    "entity_type": "character"
  },
  "hops": [
    {
      "direction": "out",
      "edge_type": "WIELDS_ARTIFACT",
      "target_filters": {
        "entity_type": "artifact"
      }
    }
  ],
  "order_by": ["created_at"]
}
```

Filter keys follow Django ORM double-underscore traversal syntax. Fields on the typed model are referenced directly (`"summary": "security"`). Fields on the Entity spine are referenced via `entity__` prefix (`"entity__entity_type": "character"`, `"entity__created_at__gte": "2025-01-01"`). This mirrors the natural Django ORM join path and requires no additional mapping layer.

V1 ORM definition supports:
- root type selected by Search `root` (`node` or `edge`)
- conjunctive root `filters` using Django `__` traversal syntax
- optional `hops` list with at most one hop
- hop `direction`: `out` or `in`
- hop `edge_type`
- hop endpoint filters (`target_filters` / `source_filters`) using the same `__` traversal syntax
- deterministic `order_by`

V1 ORM definition does not support:
- multi-hop traversal
- boolean composition (`OR`, `NOT`, nested logical trees)
- arbitrary joins outside the graph model
- access to non-TAP Django models

One-hop traversal means:
- a `node`-rooted search may inspect edges directly connected to the matched node set
- an `edge`-rooted search may inspect the source or target node set connected to the matched edge set
- traversal does not continue beyond that single relationship boundary

If `order_by` is not provided, execution must fall back to a deterministic default ordering appropriate to the root model.

#### Development
Keep the ORM DSL graph-native and small. If future requirements demand traversal chaining or boolean expression trees, that should be treated as a deliberate expansion, not incrementally smuggled into the v1 structure.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-search-orm-1 | Definition Stored as JSON DSL | Implemented | `orm` searches store query structure in `definition` as JSON. | |
| req-grid-search-orm-2 | Root Chosen by Search Root Field | Implemented | ORM execution begins from the Search object's `root` value (`node` or `edge`). | |
| req-grid-search-orm-3 | Conjunctive Filters Supported | Implemented | V1 ORM search supports conjunctive filters on the selected root set. | |
| req-grid-search-orm-4 | One Hop Maximum | Implemented | V1 ORM search supports at most one graph hop from the root set. | |
| req-grid-search-orm-5 | Hop Direction Explicit | Implemented | A hop explicitly declares `in` or `out` direction. | |
| req-grid-search-orm-6 | Hop Edge Type Explicit | Implemented | A hop may constrain traversal by `edge_type`. | |
| req-grid-search-orm-7 | Endpoint Filters Supported | Implemented | A hop may apply endpoint filters to the connected node set. | |
| req-grid-search-orm-8 | Non-TAP Models Excluded | Implemented | ORM search definitions cannot target models outside TAP-managed `BaseModel` descendants. | |
| req-grid-search-orm-9 | Deterministic Ordering | Implemented | ORM execution applies explicit or default deterministic ordering before pagination. | |

#### Future
Consider supporting boolean composition (`OR`, `NOT`, nested logical expressions`) once real searches demonstrate the need.

Consider supporting traversal chaining or linked searches as a separate query-composition mechanism rather than expanding v1 hops into an ad hoc graph language.

Consider supporting SQL-backed searches as a separate mode if a narrow, read-only, TAP-scoped execution model can be specified safely.

---

### Search Results
----
RID: `req-grid-search-results`
Status: `Proposed`

Searches always return the canonical 4-key graph envelope. Every execution mode returns the same shape. Hard failures raise a `SearchExecutionError` (not an envelope-level error key) so callers can unambiguously distinguish "search ran and produced warnings" from "search failed to execute at all."

#### Status Details
Result-shape consistency is being specified up front so search consumers can build against one canonical contract regardless of search mode.

#### Implementation
Canonical result envelope:

```json
{
  "nodes": [],
  "edges": [],
  "info": {},
  "warnings": {}
}
```

- `nodes`: list of node objects matched by the search
- `edges`: list of edge objects matched or traversed by the search
- `info`: metadata about the execution — e.g. total count, execution time, applied limit/offset, which filters were active
- `warnings`: non-fatal issues — e.g. a filter referenced a deprecated field, a hop produced no results, applied `max_limit` clamping. Keyed by warning code.

Hard execution failures (unresolved runner key, invalid definition at execution time, database error) raise `SearchExecutionError`. They are never silently folded into the envelope.

When pagination is enabled, the canonical paginated result envelope wraps the inner graph envelope:

```json
{
  "count": 0,
  "limit": 25,
  "offset": 0,
  "results": {
    "nodes": [],
    "edges": [],
    "info": {},
    "warnings": {}
  }
}
```

`limit` and `offset` are passed as execution-time kwargs to the service layer. The service layer clamps `limit` to the Search object's `max_limit` if set and records the clamping in `warnings`. `count` is the total number of primary-side results before pagination.

Node and edge members are serialized as JSON objects. `returns` may narrow which side is primary, which graph members are included, and which fields are projected, but it does not change the top-level envelope shape.

`limit`, `offset`, and `count` apply to the `primary` side declared by `returns.primary`. Graph members included from the non-primary side are incidental connected results and are not independently paginated.

#### Development
The 4-key envelope is a deliberate constraint. `info` and `warnings` as first-class keys prevent consumers from scraping error signals out of opaque metadata and keep the contract explicit across all execution modes.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-search-results-1 | 4-Key Envelope | Proposed | All search results return a JSON object with exactly `nodes`, `edges`, `info`, and `warnings` keys. | |
| req-grid-search-results-2 | Paginated Wrapper | Proposed | Paginated results wrap the 4-key envelope in `count`, `limit`, `offset`, and `results`. | |
| req-grid-search-results-3 | Hard Failures Raise | Proposed | Hard execution failures raise `SearchExecutionError` and are never silently placed in the envelope. | |
| req-grid-search-results-4 | info Contains Execution Metadata | Proposed | `info` contains execution metadata (applied limit/offset, count, timing). Structure TBD at implementation time. | |
| req-grid-search-results-5 | warnings Contains Non-Fatal Issues | Proposed | `warnings` is a dict keyed by warning code. Non-fatal issues (deprecated fields, max_limit clamping) are placed here, not in `info`. | |
| req-grid-search-results-6 | JSON Serialized Members | Proposed | Node and edge members in search results are serialized as JSON objects. | |
| req-grid-search-results-7 | Returns Does Not Replace Envelope | Proposed | `returns` may shape inclusion and projection but does not change the top-level 4-key envelope shape. | |
| req-grid-search-results-8 | Pagination Applies To Primary Side | Proposed | `limit`, `offset`, and `count` apply to the `primary` side declared by `returns.primary`, not to the total number of graph members in the full envelope. | |
| req-grid-search-results-9 | max_limit Clamping Recorded | Proposed | When the service layer clamps caller-provided `limit` to `max_limit`, the clamping is recorded in `warnings`. | |

#### Future
Consider defining standard result projection helpers for common consumers such as table panels, graph views, and form pickers.

---

### Search Authorization
----
RID: `req-grid-search-authz.sec`
Status: `Backlog`

Search-specific authorization and access-control behavior is a required security concern, but it is deferred from the initial search specification.

#### Status Details
Backlog requirement created so search execution does not silently inherit undefined security behavior.

#### Implementation
Future work must define:
- whether searches execute in caller context or a narrower search-specific permission model
- whether different search objects can have different access policies
- whether module runners require additional approval or scope controls
- how search execution interacts with page, panel, and API authorization

#### Development
Security posture for searches must be designed before searches are exposed broadly through user-facing pages, APIs, or plugin ecosystems.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-search-authz.sec-1 | Security Requirement Exists | Proposed | Search authorization is tracked as a dedicated security requirement. | |
| req-grid-search-authz.sec-2 | Execution Context Undefined by Default | Proposed | Search execution does not claim an implicit authorization model until this requirement is implemented. | |

#### Future
Define caller-context authorization, search object visibility rules, and execution-policy controls.

## Status Vocabulary

| Status States |  |
| --- | --- |
| Proposed |  |
| Approved for Development | Requirement is accepted and ready to be implemented |
| In Development |  |
| Implemented |  |
| Verified |  |
| Refactoring |  |
| Deprecating |  |
| Deprecated | Not part of the current architecture and should not be implemented |

## RID Format

`req-<application>-<specification>-<feature>-<sub-feature>`

## Requirements Format

`RID: \`...\``  
`Status: \`...\``

| Sub-Sections | (as needed) |
| --- | --- |
| Status Details |  |
| Implementation |  |
| Development |  |
| Acceptance Criteria |  |
| Future |  |
