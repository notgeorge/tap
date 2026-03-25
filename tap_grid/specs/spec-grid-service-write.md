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

