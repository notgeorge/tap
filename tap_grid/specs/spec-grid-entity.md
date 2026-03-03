# Grid Entity Specification

## Philosophy

Entities are the base node of the grid / graph and the canonical place where data about a thing is defined and resides. This specification captures structural decisions about the entity model itself so those decisions can be reviewed, implemented, and later reconstructed from code without relying on historical context.

## Goals

|    |              |                                                                                 |
| :---: | ---       | ---                                                                             |
| 1. | Canonical    | Entity remains the canonical system-of-record node for grid data                |
| 2. | Coherent     | Entity model decisions are documented in one place and can evolve intentionally |
| 3. | Recoverable  | Core entity architecture can be reconstructed from specs and code together      |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-grid-entity-ee | [Entities Are Entities](#entities-are-entities) | Proposed | Converts `EntityType` into a first-class entity model |

### Entities Are Entities
----
RID: `req-grid-entity-ee`  
Status: `Proposed`

#### Status Details
This is a significant structural change to the grid model and should be treated as a distinct architecture change rather than bundled with dimension work.

#### Implementation
Convert the existing `EntityType` definition into a full-fledged `Entity` object and adjust all previously defined entities to suit.

#### Development
This spec is intentionally narrow so it can serve as the landing place for the later project that extracts pre-spec architectural decisions from the current codebase.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-entity-ee-1 | Entity Types Are First-Class | Proposed | Entity type definitions are represented as entity records rather than only registry rows. | |
| req-grid-entity-ee-2 | Existing Definitions Migrated | Proposed | Existing entity type definitions are updated to the new representation without losing their current identifying information. | This likely needs a dedicated migration plan. |

#### Future

## Status Vocabulary

| Status States |  |
| --- | --- |
| Proposed |  |
| In Development |  |
| Implemented |  |
| Verified |  |
| Refactoring |  |
| Deprecating |  |
| Deprecated |  |

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
