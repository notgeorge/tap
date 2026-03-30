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
| req-grid-service-delete-future | [Deferred Delete Policy Design](#deferred-delete-policy-design) | Implemented | Explicitly deferred in spec |


### Baseline Delete Semantics
----
RID: `req-grid-service-delete-baseline`
Status: `Implemented`

The minimum delete contract for TAP is that deleting a node removes its associated entity and any associated edges, preserving the graph's baseline integrity guarantees.

#### Status Details
`delete_node()` routes through `write_batch()` / `_execute_write_pipeline()`. The pipeline calls `instance.entity.delete()` which cascades via Django FK cascade to edges.

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
Status: `Implemented`

Delete policy beyond the baseline guarantees is explicitly deferred rather than left ambiguous.

#### Status Details
This requirement is satisfied by the spec itself explicitly documenting the deferral.

#### Implementation
Deferred areas include:

- configurable cascade policies
- block versus allow semantics on delete
- soft delete
- archive/tombstone behaviors
- selective unlink behaviors
- plugin-specific delete hooks

This requirement exists to make the backlog explicit and prevent accidental implicit policy.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-delete-future-1 | Rich Delete Policy Deferred | Implemented | The baseline delete spec explicitly defers richer policy decisions rather than implying them. | |
| req-grid-service-delete-future-2 | Dedicated Future Spec Anticipated | Implemented | The specification records the need for a dedicated follow-on delete policy spec. | |

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
