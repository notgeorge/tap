# Grid Service Read Specification

## Philosophy

The TAP service layer should expose a small, explicit read surface for direct object lookup and type discovery while routing richer graph retrieval through search. This keeps direct reads simple, predictable, and easy to secure, while preserving the search system as the canonical expressive read mechanism.

## Goals

|    |                  |                                                                                 |
| :---: | ---           | ---                                                                             |
| 1. | Narrow            | Direct read APIs are intentionally small and limited                            |
| 2. | Discoverable      | Clients can inspect node and edge types, schemas, constraints, and hotlinks     |
| 3. | Self-Describing   | Read responses can identify their associated schemas and representation contract |


## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-grid-service-read-direct | [Direct Object Reads](#direct-object-reads) | Proposed | Generic and typed single-object lookup |
| req-grid-service-read-discovery | [Discovery Reads](#discovery-reads) | Proposed | Type and service capability discovery |
| req-grid-service-read-search | [Search Boundary](#search-boundary) | Proposed | Rich reads go through search |
| req-grid-service-read-schemas | [Schema Delivery For Reads](#schema-delivery-for-reads) | Proposed | Refs by default, inline by request |


### Direct Object Reads
----
RID: `req-grid-service-read-direct`
Status: `Proposed`

The direct read surface should provide a small set of single-object lookups plus a generic wrapper for callers that have an object reference but do not want to branch on node versus edge handling themselves.

#### Status Details
This is a new contract requirement. Existing code relies on ad hoc ORM queries and specialized helpers.

#### Implementation
Direct read APIs should include:

- `get_object(target, ...)`
- `get_node(target, ...)`
- `get_edge(target, ...)`
- `resolve_entity(target, ...)`

These reads may accept IDs or native model instances. The generic `get_object()` wrapper should detect whether the target resolves to a node or edge and dispatch accordingly.

The caller may request either JSON-safe service envelopes or native model returns.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-read-direct-1 | Generic Object Wrapper | Proposed | Direct reads include a generic wrapper for node/edge dispatch. | |
| req-grid-service-read-direct-2 | IDs And Instances Accepted | Proposed | Single-object read APIs accept object IDs and model instances. | |
| req-grid-service-read-direct-3 | JSON Or Model Return | Proposed | Direct reads support JSON-safe and native model return modes. | |

#### Future
Decide whether a direct `get_entity()` helper is needed for internal plumbing only.


### Discovery Reads
----
RID: `req-grid-service-read-discovery`
Status: `Proposed`

The service layer must provide machine-usable discovery so clients can understand type shape, constraints, hotlinks, and operation support without importing server-side code.

#### Status Details
This is a core affordance for plugin conformance, API portability, and bot usability.

#### Implementation
Discovery reads should include:

- `describe_service_capabilities()`
- `list_node_types()`
- `describe_node_type(type_slug, include_schemas=True)`
- `list_edge_types()`
- `describe_edge_type(edge_type, include_schemas=True)`

Discovery responses should include:

- operation support by type
- read/create/patch/replace schema refs
- resolved schemas by default
- constraint schemas
- hotlink schemas
- any shared schema refs used by those contracts

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-read-discovery-1 | Node Type Discovery Supported | Proposed | The service layer can list and describe node types. | |
| req-grid-service-read-discovery-2 | Edge Type Discovery Supported | Proposed | The service layer can list and describe edge types. | |
| req-grid-service-read-discovery-3 | Discovery Includes Constraints And Hotlinks | Proposed | Type discovery publishes constraint and hotlink information. | |
| req-grid-service-read-discovery-4 | Discovery Bundles Schemas By Default | Proposed | Discovery responses inline relevant schemas by default. | |

#### Future
Add discovery metadata for deprecation and lifecycle state once the broader service contract stabilizes.


### Search Boundary
----
RID: `req-grid-service-read-search`
Status: `Proposed`

Direct read APIs are intentionally narrow. Graph neighborhoods, complex filtering, traversal, pagination-heavy retrieval, and other richer read behavior should go through the shared search service rather than growing the direct read surface.

#### Status Details
This requirement codifies the decision to avoid ad hoc richer read helpers in the service layer.

#### Implementation
Direct reads should not grow convenience helpers for graph traversal or complex retrieval. If the caller wants more than a direct object lookup or discovery bundle, the request should be expressed as a Search and executed through `spec-grid-search.md`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-read-search-1 | Rich Reads Route To Search | Proposed | Complex retrieval beyond direct lookup and discovery is handled through search rather than custom read helpers. | |
| req-grid-service-read-search-2 | No Neighborhood Helper Contract | Proposed | The service layer does not define a dedicated graph neighborhood helper as part of the direct read surface. | |

#### Future
Revisit if time-travel or comparison reads require a separate read family rather than pure search.


### Schema Delivery For Reads
----
RID: `req-grid-service-read-schemas`
Status: `Proposed`

Read results should be self-describing without making every ordinary response unnecessarily heavy.

#### Status Details
This requirement formalizes schema refs for ordinary reads and deduplicated schema delivery for larger result sets.

#### Implementation
Ordinary single-object reads return:

- object result
- schema refs for envelope, payload, constraints, and hotlinks where relevant

If the caller requests inline schemas, the response also includes a `schemas` map keyed by TAP schema ID.

Batch and search-style multi-object reads should:

- publish deduplicated schema refs at the top level
- optionally inline a shared `schemas` map

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-read-schemas-1 | Single Reads Use Refs By Default | Proposed | Ordinary single-object reads identify applicable schemas via schema refs by default. | |
| req-grid-service-read-schemas-2 | Inline Schemas Optional | Proposed | Callers may request inline resolved schemas for ordinary reads. | |
| req-grid-service-read-schemas-3 | Multi-Object Reads Deduplicate | Proposed | Search and batch-style responses publish shared schema refs rather than repeating them per object. | |

#### Future
Define caching guidance for clients that consume schema IDs frequently.


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

