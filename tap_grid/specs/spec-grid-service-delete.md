# Grid Service Delete Specification

## Philosophy

Delete behavior is a critical part of the service-layer contract because it determines how TAP preserves graph integrity when objects are removed. The initial delete contract should be conservative, explicit, and focused on the baseline guarantees already understood, while leaving richer cascade policy design for a dedicated future pass.

## Goals

|    |                  |                                                                                 |
| :---: | ---           | ---                                                                             |
| 1. | Safe              | Deletions preserve core graph integrity                                         |
| 2. | Explicit          | Delete behavior is defined through the service layer rather than implied         |
| 3. | Extensible        | Future richer delete policies can layer on top of a clear baseline contract      |


## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-grid-service-delete-baseline | [Baseline Delete Semantics](#baseline-delete-semantics) | Implemented | Node/edge delete with entity cascade |
| req-grid-service-delete-scope | [Delete Scope And Wrappers](#delete-scope-and-wrappers) | Implemented | delete_node + delete_edge_by_entity route through write pipeline |
| req-grid-service-delete-tombstone | [Tombstoned Delete Semantics](#tombstoned-delete-semantics) | Implemented | Delete behavior uses `deleted_at` tombstones through the service layer |
| req-grid-service-delete-future | [Deferred Delete Policy Design](#deferred-delete-policy-design) | Refactoring | Explicit deferral narrowed now that tombstones are specified here |


### Baseline Delete Semantics
----
RID: `req-grid-service-delete-baseline`
Status: `Implemented`

The minimum delete contract for TAP is that deleting a node removes its associated entity and any associated edges, preserving the graph's baseline integrity guarantees.

#### Status Details
`delete_node()` routes through `write_batch()` / `_execute_write_pipeline()`. The pipeline now uses tombstone semantics (see `req-grid-service-delete-tombstone`): `deleted_at` is set on the entity and cascade-tombstones connected edges. Physical rows are not removed.

#### Implementation
Baseline guarantees:

- deleting a `BaseModel`-backed node deletes its associated `Entity`
- deleting that entity removes associated edges through cascade behavior
- deleting an edge removes its backing entity

Delete semantics beyond this baseline, such as configurable cascade policy, soft delete, or selective unlinking behavior, are deferred.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-delete-baseline-1 | Node Delete Removes Entity | Implemented | Deleting a node through the service layer removes its associated entity. | |
| req-grid-service-delete-baseline-2 | Node Delete Removes Related Edges | Implemented | Deleting a node through the service layer removes related edges via the established cascade path. | |
| req-grid-service-delete-baseline-3 | Edge Delete Removes Backing Entity | Implemented | Deleting an edge through the service layer removes its backing entity. | |

#### Future
Define whether edge removal should also support unlink-only semantics separate from full delete.

### Tombstoned Delete Semantics
----
RID: `req-grid-service-delete-tombstone`
Status: `Implemented`

The delete contract for TAP uses tombstoned lifecycle transitions rather than immediate destructive removal from canonical tables. Delete remains a service-layer operation and preserves historical existence for later time-travel and audit features.

#### Status Details
`Entity.deleted_at` (nullable, indexed) marks tombstoned entities. `delete_node()` and `delete_edge_by_entity()` set `deleted_at` via `_execute_write_pipeline`. `BaseModel.objects` (LiveManager) excludes tombstoned entities from default queries. `BaseModel.all_objects` provides unfiltered access. Edge tombstone cascade: when a node is tombstoned, all live edges at either endpoint are also tombstoned atomically. Write prohibition: patch/replace verbs on a tombstoned entity raise `ServiceConflictError` with code `"conflict"`.

#### Implementation
The tombstoned delete contract is:

1. Canonical nodes and edges carry `deleted_at`, where `NULL` means still live.
2. Service-layer delete sets `deleted_at` rather than physically removing canonical rows during ordinary delete operations.
3. The delete transition is recorded in history as the final lifecycle event for that object.
4. Normal current-state read/search/write service paths exclude tombstoned objects by default.
5. Historical service paths may still reconstruct tombstoned objects for points in time before `deleted_at`.
6. Edge visibility must be sanity-checked against endpoint existence so service-layer graph reads do not return dangling edges in either current or historical modes.

This requirement defines normal product delete behavior. Hard-delete maintenance or archival compaction, if needed later, should be treated as a separate operational concern.

#### Development
Tombstoning belongs in the delete spec because it is fundamentally a service-layer lifecycle decision:

- what delete means
- what current reads should hide
- what history should preserve

History and time travel then build on that lifecycle contract.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-delete-tombstone-1 | Deleted At Field | Implemented | Canonical service-managed deletes use `deleted_at` with `NULL` meaning still live. | `Entity.deleted_at` nullable DateTimeField with db_index |
| req-grid-service-delete-tombstone-2 | Delete Uses Tombstone Transition | Implemented | Ordinary service-layer delete transitions set tombstone state instead of physically removing canonical rows. | `_execute_write_pipeline` sets `deleted_at` via `.update()` |
| req-grid-service-delete-tombstone-3 | Current Reads Exclude Tombstones | Implemented | Default service-layer current-state reads and searches do not return tombstoned objects. | `LiveManager` on `BaseModel.objects` filters `entity__deleted_at__isnull=True` |
| req-grid-service-delete-tombstone-4 | Delete Preserved For History | Proposed | Tombstoned deletes remain reconstructible through history/time-travel for timestamps before `deleted_at`. | Rows persist; time-travel query spec is backlogged |
| req-grid-service-delete-tombstone-5 | Edge Endpoint Sanity | Proposed | Service-layer graph reads do not return an edge unless its endpoints are valid in the requested visibility mode. | Deferred to graph read spec |

#### Future
Later work may add richer lifecycle states or explicit archive maintenance flows without redefining tombstone semantics as the default delete behavior.


### Delete Scope And Wrappers
----
RID: `req-grid-service-delete-scope`
Status: `Implemented`

Delete operations are exposed through the same explicit service-layer entry points as other writes.

#### Status Details
`delete_node(target)` and `delete_edge_by_entity(target)` both accept entity UUIDs and route through `write_batch()`. They participate in the same batching, dry-run, error taxonomy, and response envelope conventions as other write verbs.

Note: `delete_edge_by_entity` is the spec-compliant pipeline-based entry point for edge deletes. The legacy compat wrapper `delete_edge(edge: Edge)` is deprecated and kept only for backward compatibility with existing callers.

#### Implementation
Delete entry points:

- `delete_node(target, ...)` — removes node + Entity spine via write pipeline
- `delete_edge_by_entity(target, ...)` — removes edge + backing Entity via write pipeline
- `write_batch([WriteOperation(verb="delete_node", target=...)])` — batch delete

Delete results use the same structured `WriteResult` envelope and `ServiceError` taxonomy as other writes.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-delete-scope-1 | Node Delete Entry Point | Implemented | The service layer defines a public node delete entry point. | `delete_node(target)` |
| req-grid-service-delete-scope-2 | Edge Delete Entry Point | Implemented | The service layer defines a public edge delete entry point. | `delete_edge_by_entity(target)` — naming differs from spec due to legacy compat |
| req-grid-service-delete-scope-3 | Delete Uses Shared Write Contract | Implemented | Delete operations participate in the same batching, error, and response conventions as other writes. | |

#### Future
Rename `delete_edge_by_entity` to `delete_edge` once the legacy compat wrapper is removed.


### Deferred Delete Policy Design
----
RID: `req-grid-service-delete-future`
Status: `Refactoring`

Delete policy beyond the baseline guarantees is explicitly deferred rather than left ambiguous.

#### Status Details
This requirement is being narrowed now that tombstone semantics are specified separately in `req-grid-service-delete-tombstone`.

#### Implementation
Deferred areas include:

- configurable cascade policies
- block versus allow semantics on delete
- archive compaction or hard-delete maintenance behaviors
- selective unlink behaviors
- plugin-specific delete hooks

This requirement exists to make the backlog explicit and prevent accidental implicit policy.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-delete-future-1 | Remaining Rich Delete Policy Deferred | Refactoring | The delete spec explicitly defers richer policy decisions not yet covered by baseline or tombstone requirements. | |
| req-grid-service-delete-future-2 | Follow-On Delete Policy Still Anticipated | Refactoring | The specification records remaining future delete-policy work beyond baseline and tombstone semantics. | |

#### Future
When the dedicated delete policy spec is created, it should supersede this backlog requirement with concrete policy rules.


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
