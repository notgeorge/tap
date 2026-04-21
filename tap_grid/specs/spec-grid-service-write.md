# Grid Service Write Specification

## Philosophy

Write operations are where the TAP service layer earns its keep. The write contract should let callers submit safe, schema-backed payloads without importing Django model classes, while guaranteeing that model validation, graph invariants, hotlinks, batching, and response shaping all happen consistently.

## Goals

|    |                  |                                                                                 |
| :---: | ---           | ---                                                                             |
| 1. | Consistent        | All node and edge writes use one shared enforcement pipeline                    |
| 2. | Schema-Driven     | Clients can submit JSON-safe write payloads described by published schemas      |
| 3. | Explicit          | Create, patch, and replace semantics are distinct and documented                |
| 4. | Batch-Backed      | Every write participates in batch semantics, including single-object writes     |


## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-grid-service-write-surface | [Write Operation Surface](#write-operation-surface) | Implemented | Canonical public write verbs |
| req-grid-service-write-payloads | [Write Payload Semantics](#write-payload-semantics) | Implemented | Slug-driven payload handling and strict rejection |
| req-grid-service-write-internal | [Internal-Only Write Exclusion](#internal-only-write-exclusion) | Implemented | Default service-layer CRUD verbs reject internal-only model types |
| req-grid-service-write-schema-cleanup | [Service Schema Simplification](#service-schema-simplification) | Implemented | Replace per-verb `SERVICE_CRUD_SCHEMA` with a simpler writable-field contract |
| req-grid-service-write-patch | [Patch And Replace Rules](#patch-and-replace-rules) | Implemented | Deep merge and immutable edge type rules |
| req-grid-service-write-validate | [Write Validation Stack](#write-validation-stack) | Implemented | full_clean, constraints, hotlinks |
| req-grid-service-write-results | [Write Result Envelopes](#write-result-envelopes) | Implemented | Minimal, standard, verbose |


### Write Operation Surface
----
RID: `req-grid-service-write-surface`
Status: `Implemented`

The service layer should publish explicit write verbs for common intents rather than hiding all writes behind one ambiguous mutation call.

#### Status Details
Current implementation exposes a small subset of these operations.

#### Implementation
Canonical write operations should include:

- `create_node(type_slug, payload, ...)`
- `patch_node(target, payload, ...)`
- `replace_node(target, payload, ...)`
- `delete_node(target, ...)`
- `create_edge(from_target, to_target, edge_type, payload, ...)`
- `patch_edge(target, payload, ...)`
- `replace_edge(target, payload, ...)`
- `delete_edge(target, ...)`
- `write_batch(operations, dry_run=False, ...)`

These public verbs should share one internal dispatcher/pipeline.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-write-surface-1 | Explicit Node Verbs | Implemented | The write contract defines create, patch, replace, and delete for nodes. | |
| req-grid-service-write-surface-2 | Explicit Edge Verbs | Implemented | The write contract defines create, patch, replace, and delete for edges. | |
| req-grid-service-write-surface-3 | Shared Internal Dispatcher | Implemented | Public write verbs execute through a common internal write pipeline. | |

#### Future
Decide whether any thin generic write wrapper is needed in addition to the explicit verbs.

### Service Schema Simplification
----
RID: `req-grid-service-write-schema-cleanup`
Status: `Implemented`

The per-model write surface is declared via four concise ClassVars on `BaseModel` subclasses. `SERVICE_CRUD_SCHEMA` is synthesized from these at class definition time and remains available for service-layer consumption and introspection.

#### Status Details
Implemented. The three-verb `SERVICE_CRUD_SCHEMA` dict is no longer written by hand on any concrete model. All 16 concrete subclasses across `tap_grid`, `plugins/lotr`, `tap_web`, and `tap_viz` now use the new contract.

#### Implementation
Concrete `BaseModel` subclasses declare:

1. `FIELD_CRUD_SCHEMA: ClassVar[dict[str, dict]]` — field name to JSON Schema fragment; the complete writable field surface.
2. `CREATE_REQUIRED: ClassVar[list[str]]` — fields required for `create_node`/`create_edge`. Defaults to `[]`.
3. `REPLACE_REQUIRED: ClassVar[list[str]]` — fields required for `replace_node`/`replace_edge`. Defaults to `CREATE_REQUIRED` if not declared.
4. `PATCH_EXTRA_FIELDS: ClassVar[dict[str, dict]]` — verb-specific fields patchable but absent from FIELD_CRUD_SCHEMA (e.g., lifecycle fields like `status`). Defaults to `{}`.

`BaseModel.__init_subclass__` calls `_check_service_contract()` to validate these at class definition time, then calls `_build_service_schemas()` to synthesize and assign `cls.SERVICE_CRUD_SCHEMA`. The service pipeline (`_execute_write_pipeline`) and `describe_node_type()` continue to read `SERVICE_CRUD_SCHEMA` unchanged.

#### Development
The cleanup resolved two mixed concerns that existed in the old design:

- **which fields** are writable (now declared in `FIELD_CRUD_SCHEMA`)
- **what each verb requires** (now declared in `CREATE_REQUIRED` / `REPLACE_REQUIRED`)

Patch semantics (all fields optional, extra lifecycle fields allowed) and replace semantics (reset-to-default for absent optional fields) remain in the service layer.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-write-schema-cleanup-1 | Simpler Writable Field Contract | Implemented | `FIELD_CRUD_SCHEMA` replaces the three-verb `SERVICE_CRUD_SCHEMA` as the per-model writable-field declaration. `SERVICE_CRUD_SCHEMA` is synthesized automatically. | |
| req-grid-service-write-schema-cleanup-2 | Sane Defaults On Create | Implemented | Models with no `CREATE_REQUIRED` (e.g., `Edge`, `Batch`, `LandingPage`) create instances with sane field defaults. | |
| req-grid-service-write-schema-cleanup-3 | Required-On-Create Supported | Implemented | `CREATE_REQUIRED` and `REPLACE_REQUIRED` provide explicit required-field control per verb. Previously deferred; now implemented as part of this cleanup. | |

### Internal-Only Write Exclusion
----
RID: `req-grid-service-write-internal`
Status: `Implemented`

The default service-layer CRUD surface must reject internal-only model types. These types are managed by dedicated subsystem services rather than ordinary generic create, patch, replace, and delete verbs.

#### Status Details
Implemented. `_execute_write_pipeline()` in `tap_grid/services.py` checks `getattr(model_cls, "INTERNAL_ONLY", False)` after resolving `model_cls` for all node verbs and raises `ServiceUnsupportedOperationError` with code `"unsupported_operation"` if the type is internal-only. `Batch` is the first internal-only type and is now rejected by `create_node`, `patch_node`, `replace_node`, and `delete_node`.

#### Implementation
The service-layer rule is:

1. Generic `create_node`, `patch_node`, `replace_node`, and `delete_node` reject internal-only model types.
2. Internal-only model types remain readable through normal read/search services unless another requirement limits that behavior.
3. Dedicated subsystem services may still create or mutate internal-only model types.
4. `Batch` is the first intended internal-only type and should not be writable through generic node CRUD verbs.

#### Development
This keeps public CRUD predictable while still letting TAP model internal graph-native artifacts as first-class entities.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-write-internal-1 | Generic Create Rejects Internal Only | Implemented | `create_node` rejects model types marked internal-only. | `ServiceUnsupportedOperationError` |
| req-grid-service-write-internal-2 | Generic Update Rejects Internal Only | Implemented | `patch_node` and `replace_node` reject internal-only model types. | Check after target entity resolution |
| req-grid-service-write-internal-3 | Generic Delete Rejects Internal Only | Implemented | `delete_node` rejects internal-only model types unless a future dedicated rule says otherwise. | |
| req-grid-service-write-internal-4 | Dedicated Services Still Allowed | Implemented | Internal-only types may still be written through dedicated subsystem service APIs. | `tap_grid/batch.py` uses direct ORM |


### Write Payload Semantics
----
RID: `req-grid-service-write-payloads`
Status: `Implemented`

Public write payloads should be schema-backed, type-aware, and strict.

#### Status Details
This is a new contract requirement intended to eliminate client-side ad hoc JSON-to-model translation.

#### Implementation
Node creation is slug-driven:

- caller provides a node type slug
- caller provides a payload shaped by the published create schema
- service layer resolves slug to model class through the registry
- service layer instantiates and validates the model consistently

Patch and replace writes operate on a target plus a payload described by the corresponding published schemas.

Unknown fields are rejected. Omitted fields remain unchanged unless the chosen operation semantics require full replacement. Explicit nulls clear values only where allowed by schema/model constraints.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-write-payloads-1 | Slug Driven Node Writes | Implemented | Public node creation uses type slugs plus payloads rather than model-class imports. | |
| req-grid-service-write-payloads-2 | Strict Field Rejection | Implemented | Unknown fields in write payloads are rejected rather than ignored. | |
| req-grid-service-write-payloads-3 | Omitted Fields Preserved On Patch | Implemented | Patch semantics leave omitted fields unchanged unless explicitly nulled where allowed. | |

#### Future
Consider support for additional mutation semantics such as underwrite once concrete use cases emerge.


### Patch And Replace Rules
----
RID: `req-grid-service-write-patch`
Status: `Implemented`

Patch and replace are distinct operations and must not be conflated.

#### Status Details
This requirement captures the current contract decisions for structured payload handling.

#### Implementation
Patch semantics:

- omitted fields remain unchanged
- explicit nulls clear values only where schema/model rules allow
- nested JSON payloads use deep merge semantics

Replace semantics:

- caller replaces the addressed payload according to the operation schema
- for edges, replace means replacing edge payload/properties only
- edge type is immutable and may never be changed by replace

`flip_map` is not user-writable and should not be exposed as a client-writeable payload field.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-write-patch-1 | JSONField Deep Merge, Scalars Replace | Implemented | Patch operations apply deep merge semantics to JSONField values. Scalar fields (CharField, IntegerField, etc.) always replace on patch. | |
| req-grid-service-write-patch-2 | Edge Replace Does Not Change Type | Implemented | Replace operations for edges do not allow `edge_type` changes. | |
| req-grid-service-write-patch-3 | Internal Flip Map Not User Writable | Implemented | `flip_map` is not part of the user-writeable payload contract. | |
| req-grid-service-write-patch-4 | Replace Node Covers User-Writable Model Fields | Implemented | `replace_node` replaces all user-writable fields on the `BaseModel`-derived class. Fields on the Entity spine (id, entity_type, originating_grid_id, created_at) are not part of the replace payload. | |


### Write Validation Stack
----
RID: `req-grid-service-write-validate`
Status: `Implemented`

All writes should pass through the same ordered validation stack before persistence.

#### Status Details
Current behavior is split across model methods, helper functions, and surrounding code. This requirement centralizes the intended order.

#### Implementation
Write validation should include:

1. input normalization
2. security/authz hook stub
3. target resolution and object loading
4. schema validation
5. strict field rejection
6. model `full_clean()`
7. service-layer graph constraint checks
8. hotlink validation
9. transaction and batch setup
10. persistence
11. provenance/batch recording
12. response shaping

Model validation is the deepest invariant layer for object shape and field semantics. The service layer orchestrates cross-object and graph-level invariants above that.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-write-validate-1 | Full Clean Always Runs | Implemented | All write operations call `full_clean()` before persistence. | |
| req-grid-service-write-validate-2 | Constraint Checks Explicit | Implemented | The write pipeline includes service-layer graph constraint validation. | |
| req-grid-service-write-validate-3 | Hotlink Checks Explicit | Implemented | The write pipeline includes explicit hotlink validation. | |
| req-grid-service-write-validate-4 | Security Hook Reserved | Implemented | The write pipeline reserves a defined position for future authorization enforcement. | |

#### Future
Document which invariants belong in models versus the service layer once implementation work shakes out edge cases.


### Write Result Envelopes
----
RID: `req-grid-service-write-results`
Status: `Implemented`

Write results should be structured, machine-usable, and flexible enough for lightweight callers and deep admin/bot inspection.

#### Status Details
This requirement defines result envelopes rather than raw booleans or inconsistent per-call outputs.

#### Implementation
Write responses should support:

- minimal
- standard
- verbose

Minimal should include success confirmation, object identity, and batch identity.

Standard should add object summary and warnings.

Verbose should add enough structured context for admins and bots to dig deeper into backend details without exposing raw Django/ORM internals directly to ordinary callers.

Write result envelopes should identify the relevant schema refs and may optionally inline schemas.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-write-results-1 | Structured Result Envelope | Implemented | Write operations return structured envelopes rather than ad hoc raw values alone. | |
| req-grid-service-write-results-2 | Detail Modes Defined | Implemented | The write contract defines minimal, standard, and verbose result modes. | |
| req-grid-service-write-results-3 | Verbose Supports Deep Inspection | Implemented | Verbose mode includes sufficient non-sensitive references and diagnostics for admin or bot follow-up. | |

#### Future
Define exact field-level contents of each result mode once the error and batch contracts are implemented.


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
