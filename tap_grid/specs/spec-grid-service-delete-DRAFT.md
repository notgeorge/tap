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
| req-grid-service-delete-baseline | [Baseline Delete Semantics](#baseline-delete-semantics) | Proposed | Current minimum required delete behavior |
| req-grid-service-delete-scope | [Delete Scope And Wrappers](#delete-scope-and-wrappers) | Proposed | Node and edge delete entry points |
| req-grid-service-delete-future | [Deferred Delete Policy Design](#deferred-delete-policy-design) | Proposed | Explicitly backlog richer policy work |


### Baseline Delete Semantics
----
RID: `req-grid-service-delete-baseline`
Status: `Proposed`

The minimum delete contract for TAP is that deleting a node removes its associated entity and any associated edges, preserving the graph’s baseline integrity guarantees.

#### Status Details
This requirement captures the minimum agreed contract and intentionally does not attempt to solve richer cascade policy design yet.

#### Implementation
Baseline guarantees:

- deleting a `BaseModel`-backed node deletes its associated `Entity`
- deleting that entity removes associated edges through cascade behavior
- deleting an edge removes its backing entity

Delete semantics beyond this baseline, such as configurable cascade policy, soft delete, or selective unlinking behavior, are deferred.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-delete-baseline-1 | Node Delete Removes Entity | Proposed | Deleting a node through the service layer removes its associated entity. | |
| req-grid-service-delete-baseline-2 | Node Delete Removes Related Edges | Proposed | Deleting a node through the service layer removes related edges via the established cascade path. | |
| req-grid-service-delete-baseline-3 | Edge Delete Removes Backing Entity | Proposed | Deleting an edge through the service layer removes its backing entity. | |

#### Future
Define whether edge removal should also support unlink-only semantics separate from full delete.


### Delete Scope And Wrappers
----
RID: `req-grid-service-delete-scope`
Status: `Proposed`

Delete operations should be exposed through the same explicit service-layer entry points as other writes.

#### Status Details
Current implementation has low-level delete helpers but not yet a full delete-specific contract.

#### Implementation
Delete entry points should include:

- `delete_node(target, ...)`
- `delete_edge(target, ...)`
- `write_batch(...)` entries that perform delete operations

Delete results should use the same structured envelope and error taxonomy as other writes.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-delete-scope-1 | Node Delete Entry Point | Proposed | The service layer defines a public node delete entry point. | |
| req-grid-service-delete-scope-2 | Edge Delete Entry Point | Proposed | The service layer defines a public edge delete entry point. | |
| req-grid-service-delete-scope-3 | Delete Uses Shared Write Contract | Proposed | Delete operations participate in the same batching, error, and response conventions as other writes. | |

#### Future
Consider whether discovery should publish delete support or delete policy metadata once richer delete design exists.


### Deferred Delete Policy Design
----
RID: `req-grid-service-delete-future`
Status: `Proposed`

Delete policy beyond the baseline guarantees is explicitly deferred rather than left ambiguous.

#### Status Details
The project expects a future dedicated delete specification to cover richer policy questions.

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
| req-grid-service-delete-future-1 | Rich Delete Policy Deferred | Proposed | The baseline delete spec explicitly defers richer policy decisions rather than implying them. | |
| req-grid-service-delete-future-2 | Dedicated Future Spec Anticipated | Proposed | The specification records the need for a dedicated follow-on delete policy spec. | |

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

