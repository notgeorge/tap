# Grid Service Error Specification

## Philosophy

The TAP service layer should present errors through a stable, expressive contract that is useful to humans, bots, APIs, and admin tooling without leaking raw Django or ORM internals to ordinary callers.

## Goals

|    |                  |                                                                                 |
| :---: | ---           | ---                                                                             |
| 1. | Stable            | Errors use a defined taxonomy rather than ad hoc exception leakage              |
| 2. | Safe              | Public responses avoid exposing sensitive framework internals                   |
| 3. | Useful            | Humans and bots can understand what failed and how to investigate further       |


## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-grid-service-errors-taxonomy | [Stable Error Taxonomy](#stable-error-taxonomy) | Proposed | Exception classes and stable codes |
| req-grid-service-errors-safe | [Safe Public Error Surface](#safe-public-error-surface) | Proposed | User-safe messages, internal details withheld |
| req-grid-service-errors-diagnostic | [Diagnostic References](#diagnostic-references) | Proposed | Deep inspection support for admins and bots |


### Stable Error Taxonomy
----
RID: `req-grid-service-errors-taxonomy`
Status: `Proposed`

The service layer should define a stable family of service exceptions and error codes instead of leaking arbitrary framework exceptions to callers.

#### Status Details
Current code mixes domain exceptions with Django/framework exceptions. This requirement defines the intended contract.

#### Implementation
The taxonomy should distinguish at least:

- validation failure
- constraint violation
- authorization failure
- not found
- conflict
- unsupported operation
- internal failure

Every public-facing service error should carry a stable error code in addition to its Python exception class.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-errors-taxonomy-1 | Stable Service Exceptions | Proposed | Public service operations fail through a documented set of service exception types. | |
| req-grid-service-errors-taxonomy-2 | Stable Error Codes | Proposed | Public service errors include stable machine-usable error codes. | |
| req-grid-service-errors-taxonomy-3 | Core Failure Categories Covered | Proposed | The error taxonomy distinguishes validation, constraint, authz, not found, conflict, unsupported, and internal failures. | |

#### Future
Decide whether the stable error code namespace should also be versioned independently of exception class names.


### Safe Public Error Surface
----
RID: `req-grid-service-errors-safe`
Status: `Proposed`

Public-facing service responses should expose safe error information while preventing accidental leakage of sensitive Django/ORM/framework details.

#### Status Details
This requirement reflects the need for graceful wrapping of lower-level exceptions.

#### Implementation
When lower-level exceptions occur, the service layer should:

- capture them
- map them to the stable error taxonomy
- expose a safe public message
- preserve deeper internal details only for controlled diagnostics and admin follow-up

Raw framework exceptions should not be the normal public contract.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-errors-safe-1 | Safe Public Messages | Proposed | Service errors expose safe human-readable messages suitable for ordinary callers. | |
| req-grid-service-errors-safe-2 | Framework Errors Wrapped | Proposed | Django/ORM/framework exceptions are wrapped into service-layer errors rather than exposed directly by default. | |
| req-grid-service-errors-safe-3 | Sensitive Detail Not Leaked | Proposed | Internal exception detail is not surfaced directly in ordinary public responses. | |

#### Future
Specify how much safe detail is appropriate per response mode once the admin and observability stories are implemented.


### Diagnostic References
----
RID: `req-grid-service-errors-diagnostic`
Status: `Proposed`

The error contract should still support deep investigation by admins, bots, and tooling.

#### Status Details
This requirement balances safe public messaging with operational usefulness.

#### Implementation
Error envelopes and verbose result modes should support:

- stable error code
- safe human-readable message
- structured machine detail payload
- correlation/debug reference
- optional admin/bot-oriented references for deeper backend inspection

These references should enable follow-up investigation without making raw internals part of the ordinary public API surface.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-errors-diagnostic-1 | Correlation Or Debug Reference | Proposed | Errors can include a structured reference that supports deeper investigation. | |
| req-grid-service-errors-diagnostic-2 | Machine Detail Payload | Proposed | Errors can include structured machine-usable details alongside the safe message. | |
| req-grid-service-errors-diagnostic-3 | Verbose Results Support Investigation | Proposed | Verbose response mode can expose additional non-sensitive diagnostic references for admins and bots. | |

#### Future
Integrate these references with whichever logging/observability mechanism TAP standardizes on.


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

