# Grid Edge Specification

## Philosophy

Edges are the connective tissue of the grid. They model directed, typed relationships between entity instances and are themselves first-class entities on the spine. The edge model is intentionally minimal: type, direction, and optional properties. Richness comes from the entities they connect and the constraints placed on them, not from the edge itself.

## Goals

|    |               |                                                                                                |
| :---: | ---        | ---                                                                                            |
| 1. | Directed      | Edges have an explicit source (`from_entity`) and target (`to_entity`)                         |
| 2. | Typed         | Edges carry a type slug that defines the nature of the relationship                            |
| 3. | Constrained   | Edge creation is validated against configurable node and edge-type constraints                 |
| 4. | First-Class   | Edges are entities: each `Edge` instance has a backing Entity on the spine                     |


## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-grid-edge-endpoints | [Edge Endpoint Validation](#edge-endpoint-validation) | Implemented | `Edge.save()` confirms both endpoints exist in the DB before creating the backing Entity |
| req-grid-edge-model | [Edge Model Declaration](#edge-model-declaration) | Implemented | `Edge` model fields, indexes, and entity spine integration |
| req-grid-edge-constraints | [Edge Constraint Validation](#edge-constraint-validation) | Implemented | Permission Union model for node and edge-type constraints |
| req-grid-edge-service | [Edge Service Layer](#edge-service-layer) | Implemented | `create_edge()` as the canonical mutation path for edge creation |
| req-grid-edge-nono | [No Edges Between Edges](#no-edges-between-edges) | Implemented | Service-layer rule prohibiting edges whose endpoints are themselves edges |
| req-grid-edge-properties | [Edge Property Validation](#edge-property-validation) | Implemented | Optional JSON Schema validation backed by an in-memory edge property schema registry |
| req-grid-edge-produced-batch | [PRODUCED_BATCH Standard Edge](#produced_batch-standard-edge) | Implemented | Canonical edge from any batch producer to a `Batch` entity; replaces embedded batch-ID lists |


## Explanation

Edges are modeled using a standard directed graph representation: a source entity, a target entity, and a type label on the connection. Because edges are backed by `BaseModel`, every edge row on `tap_edge` has a corresponding row on the entity spine. This makes edges first-class participants in the graph — they can carry dimensions, be referenced by entity ID, and be resolved via the model registry just like any other entity type.

The constraint system governs which edges are valid. Constraints can be declared by node types (what outbound/inbound edges they support) or by edge types (which source and target node types they can connect). Validation uses a Permission Union model: the edge is allowed if either constraint system permits it, but explicit blocks always win. See `req-grid-edge-constraints` for the full semantics.

Endpoint validation sits below constraint validation in the stack: it is a hard prerequisite that ensures the entities being connected actually exist before any further checks or writes proceed.


### Edge Endpoint Validation
----
RID: `req-grid-edge-endpoints`
Status: `Implemented`

Edges connect two existing entities. Before `Edge.save()` creates a backing Entity or writes to the database, it must confirm that both `from_entity` and `to_entity` reference Entity rows that actually exist. This prevents orphaned or dangling edges from entering the graph and gives `Edge.save()` the concrete entity types it needs to resolve `DEFAULT_DIMENSIONS` inheritance (see `req-grid-dimension-dc`).

#### Status Details
Implemented in `tap_grid/models.py` as `Edge.save()`. Tests in `tap_grid/tests/test_models.py` under `TestEdgeEndpointValidation`.

#### Implementation
`Edge.save()` overrides `BaseModel.save()`. At the start of the auto-creation path (when `entity_id is None`), before any write, it validates that `from_entity_id` and `to_entity_id` are set and that their rows exist:

```python
# Inside Edge.save() — fires before super().save()
if not Entity.objects.filter(pk=self.from_entity_id).exists():
    raise ValueError(
        f"Edge.from_entity {self.from_entity_id} does not exist on the spine."
    )
if not Entity.objects.filter(pk=self.to_entity_id).exists():
    raise ValueError(
        f"Edge.to_entity {self.to_entity_id} does not exist on the spine."
    )
```

The validation runs before backing Entity creation so that a failed check never leaves an orphaned Entity row on the spine.

At the service layer, `create_edge()` receives full `Entity` instances, so the caller's FK assignment implicitly sets valid IDs. The model-level check is a safety net for any path that bypasses the service layer (e.g., direct `Edge.objects.create()` in tests or migrations).

#### Development

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-edge-endpoints-1 | From Entity Validated | Implemented | `Edge.save()` raises `ValueError` if `from_entity_id` does not correspond to an existing Entity row. | |
| req-grid-edge-endpoints-2 | To Entity Validated | Implemented | `Edge.save()` raises `ValueError` if `to_entity_id` does not correspond to an existing Entity row. | |
| req-grid-edge-endpoints-3 | Validation Precedes Write | Implemented | Both endpoint checks complete before any Entity row is created or any DB write for the Edge occurs. | |

#### Future
Consider batching both DB checks into a single query (`Entity.objects.filter(pk__in=[from_id, to_id]).count() == 2`) to reduce round-trips under high write volume.


### Edge Model Declaration
----
RID: `req-grid-edge-model`
Status: `Implemented`

#### Status Details
Implemented as part of initial tap_grid scaffolding. Retroactively specified here.

#### Implementation
`Edge` is declared in `tap_grid/models.py` as a concrete `BaseModel` subclass with `ENTITY_TYPE = "edge"`.

Fields:

| Field | Type | Notes |
| --- | --- | --- |
| `from_entity` | ForeignKey → Entity, CASCADE | Source of the directed relationship. Reverse accessor: `edges_out` |
| `to_entity` | ForeignKey → Entity, CASCADE | Target of the directed relationship. Reverse accessor: `edges_in` |
| `edge_type` | CharField(max_length=255, db_index=True) | Type slug (e.g. `MENTORS`, `APPLIES_TO`). No FK — decoupled for speed |
| `properties` | JSONField(default=dict, blank=True) | JSON payload for this edge instance; may be any valid JSON unless constrained by `property_schema` |

Inherited from `BaseModel`: `entity` (OneToOneField to spine), `originating_grid_id`, `batch_id`, `created_at`, `updated_at`.

Compound indexes on `(from_entity, edge_type)` and `(to_entity, edge_type)` support the primary traversal patterns — "all edges of type X leaving node A" and "all edges of type X arriving at node B" — without full table scans.

`get_display_name()` returns a human-readable label: `"{from_entity_id} --[{edge_type}]--> {to_entity_id}"`.

Because `Edge` extends `BaseModel`, every `Edge` has a backing Entity on the spine. Edges can carry dimensions, be resolved by entity ID, and be deleted by cascading from their backing Entity.

#### Development

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-edge-model-1 | Edge BaseModel Subclass | Implemented | `Edge` is a concrete `BaseModel` subclass with `ENTITY_TYPE = "edge"` declared in `tap_grid/models.py`. | |
| req-grid-edge-model-2 | Endpoint Foreign Keys | Implemented | `from_entity` and `to_entity` are ForeignKeys to `Entity` with `on_delete=CASCADE` and reverse accessors `edges_out` / `edges_in`. | |
| req-grid-edge-model-3 | Edge Type Field | Implemented | `edge_type` is a `CharField(max_length=255, db_index=True)`. | |
| req-grid-edge-model-4 | Properties Field | Implemented | `properties` is a `JSONField(default=dict, blank=True)` for arbitrary edge metadata. | |
| req-grid-edge-model-5 | Traversal Indexes | Implemented | Compound indexes on `(from_entity, edge_type)` and `(to_entity, edge_type)` are defined in `Edge.Meta.indexes`. | Required for performant traversal queries. |
| req-grid-edge-model-6 | Entity Spine Integration | Implemented | Every `Edge` has a backing `Entity` row auto-created by `BaseModel.save()`. Edges can carry dimensions, be resolved by entity ID, and cascade-deleted from their Entity. | |

#### Future


### Edge Constraint Validation
----
RID: `req-grid-edge-constraints`
Status: `Implemented`

#### Status Details
Implemented in `tap_grid/constraints.py`. Retroactively specified here.

#### Implementation
Two constraint systems operate in parallel. An edge is permitted if either system allows it. Explicit blocks always reject.

**Node constraints** (declared on `BaseModel` subclasses as `OUTBOUND_EDGES` / `INBOUND_EDGES`):

```python
OUTBOUND_EDGES = [
    {"nodes": [{"type": "precept"}], "edges": [{"type": "APPLIES_TO"}]},
]
```

- `OUTBOUND_EDGES` — edge types and target node types this node can create outbound edges to
- `INBOUND_EDGES` — edge types and source node types this node can receive
- Omitting `"nodes"` key = wildcard: any target/source node type is allowed for that edge type
- `OUTBOUND_EDGES = []` or `INBOUND_EDGES = []` = explicit block-all — no edge-type constraint can override it
- Registered in `_NODE_REGISTRY` at class-definition time via `BaseModel.__init_subclass__`

**Edge type constraints** (declared in registered app `edge_types` definitions, including core apps and plugins):

```python
edge_types = [
    {"slug": "MENTORS", "sources": [{"type": "character"}], "targets": [{"type": "character"}]},
]
```

- `sources` — which source node types this edge type can connect from
- `targets` — which target node types this edge type can connect to
- Omitting `sources` or `targets` = wildcard for that side
- Multiple apps can register the same edge type; sets are unioned
- Registered in `_EDGE_TYPE_REGISTRY` via `register_edge_type_constraints()`

**Permission Union**: `validate_edge(from_type, to_type, edge_type)` in `tap_grid/constraints.py` applies the union logic and raises `InvalidEdgeError` with a descriptive message if the edge is not permitted. `create_edge()` calls `validate_edge()` before any DB write.

#### Development
The two-system model gives app authors flexibility. A model can declare what edges its node type supports (node constraints) or an edge type declaration can define what nodes it can connect — either is sufficient to permit an edge. Explicit blocks are intentionally stronger than permission grants so a node that declares itself fully closed cannot be bypassed by a permissive edge type.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-edge-constraints-1 | Node Constraint Registration | Implemented | `OUTBOUND_EDGES` and `INBOUND_EDGES` on a `BaseModel` subclass are parsed and registered in `_NODE_REGISTRY` at class-definition time via `__init_subclass__`. | |
| req-grid-edge-constraints-2 | Edge Type Constraint Registration | Implemented | Registered app `edge_types` entries with `sources`/`targets` are registered in `_EDGE_TYPE_REGISTRY` via `register_edge_type_constraints()`. | |
| req-grid-edge-constraints-3 | Permission Union | Implemented | An edge is allowed if node constraints permit it OR edge-type constraints permit it. Either is sufficient. | |
| req-grid-edge-constraints-4 | Explicit Block Wins | Implemented | `OUTBOUND_EDGES = []` or `INBOUND_EDGES = []` blocks all edges unconditionally; edge-type constraints cannot override an explicit block. | |
| req-grid-edge-constraints-5 | InvalidEdgeError Raised | Implemented | `validate_edge()` raises `InvalidEdgeError` with a descriptive message when constraints are violated. | |
| req-grid-edge-constraints-6 | Validated Before Write | Implemented | `create_edge()` calls `validate_edge()` before any DB write; `InvalidEdgeError` propagates to the caller with no DB side effects. | |

#### Future
Consider a management command that audits registered node and edge-type constraints against the entity type registry to surface configuration errors at startup.


### Edge Service Layer
----
RID: `req-grid-edge-service`
Status: `Implemented`

#### Status Details
Implemented in `tap_grid/services.py`. The `create_edge()` function was updated to remove manual Entity pre-creation in favor of `Edge.save()` auto-creation per `req-grid-entity-base-5`. Retroactively specified here.

#### Implementation
`tap_grid/services.py` is the canonical mutation API for edges. All application code that creates or deletes edges should go through these functions rather than direct ORM calls, so that constraint validation is guaranteed and FLIP can be wired in at these call sites without changing callers.

**`create_edge(from_entity, to_entity, edge_type, properties=None, display_name="")`**:
1. Calls `validate_edge(from_entity.entity_type, to_entity.entity_type, edge_type)` — raises `InvalidEdgeError` on violation.
2. Creates the edge via `Edge.objects.create(...)` — `Edge.save()` auto-creates the backing Entity.
3. If `display_name` is provided, updates `edge.entity.display_name` on the backing Entity.
4. Returns the created `Edge` instance.

`create_edge()` takes full `Entity` instances (not IDs) so that `entity_type` is available for constraint validation without an extra DB query.

**`delete_edge(edge)`**:
- Deletes via `edge.entity.delete()`. Cascades to the `Edge` row through the `OneToOneField`. Going through the Entity rather than the Edge directly keeps the deletion pattern consistent with `delete_entity()`.

#### Development

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-edge-service-1 | Validates Before Write | Implemented | `create_edge()` calls `validate_edge()` before any DB write; `InvalidEdgeError` propagates to the caller with no DB side effects. | |
| req-grid-edge-service-2 | Returns Created Edge | Implemented | `create_edge()` returns the `Edge` instance with its backing Entity populated. | |
| req-grid-edge-service-3 | Display Name Override | Implemented | If `display_name` is provided to `create_edge()`, the backing Entity's `display_name` is updated after creation. | |
| req-grid-edge-service-4 | delete_edge Cascades via Entity | Implemented | `delete_edge()` deletes through `edge.entity.delete()`, which cascades to the Edge row. | |

#### Future
Once FLIP is active, `create_edge()` and `delete_edge()` should record provenance events. The integration point is already identified; no call-site changes will be needed.
Consider an `update_edge_properties()` service function for mutating edge properties without recreating the edge.


### No Edges Between Edges
----
RID: `req-grid-edge-nono`
Status: `Implemented`

Edges model relationships between things, not between relationships. Allowing edges whose endpoints are themselves edges collapses the model into a hypergraph with significantly higher traversal complexity. This rule keeps the graph semantically flat.

#### Status Details
Implemented in `tap_grid/services.py` as a guard at the top of `create_edge()`. Tests in `tap_grid/tests/test_services.py` under `TestNoEdgesBetweenEdges`.

#### Implementation
`create_edge()` in `tap_grid/services.py` raises `InvalidEdgeError` if either endpoint's `entity_type` is `"edge"`. This check runs before constraint validation.

```python
# Inside create_edge(), before validate_edge()
if from_entity.entity_type == "edge":
    raise InvalidEdgeError("Edges cannot have other edges as endpoints (from_entity is an edge).")
if to_entity.entity_type == "edge":
    raise InvalidEdgeError("Edges cannot have other edges as endpoints (to_entity is an edge).")
```

This is a service-layer rule only. The database schema does not enforce it — `from_entity` and `to_entity` are plain ForeignKeys to `Entity` with no check constraint on `entity_type`. A connection created by bypassing the service layer will be accepted by the DB.

#### Development

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-edge-nono-1 | Source Cannot Be Edge | Implemented | `create_edge()` raises `InvalidEdgeError` if `from_entity.entity_type == "edge"`. | |
| req-grid-edge-nono-2 | Target Cannot Be Edge | Implemented | `create_edge()` raises `InvalidEdgeError` if `to_entity.entity_type == "edge"`. | |
| req-grid-edge-nono-3 | Check Precedes Constraint Validation | Implemented | The entity type checks fire before `validate_edge()` is called. | |
| req-grid-edge-nono-4 | Schema Does Not Enforce | Implemented | The database schema does not constrain this; enforcement is service-layer only. | Intentional. |

#### Future
If graph query patterns ever require edges-on-edges (e.g., for annotation or provenance edges on graph structure itself), revisit this rule before lifting it — the traversal implications are significant.


### Edge Property Validation
----
RID: `req-grid-edge-properties`
Status: `Implemented`

Edge types may define a `property_schema` JSON Schema in registered app `edge_types` declarations (including core apps and plugins). When defined, this schema is used every time edge properties are created or updated. If no `property_schema` is defined for an edge type, no property validation is performed.

This schema lives in registered `edge_types` declarations and is not sourced from `EntityType` storage.

#### Status Details
Implemented in `tap_grid/constraints.py` (`_EDGE_PROPERTY_SCHEMA_REGISTRY`, `register_edge_property_schema`, `get_edge_property_schema`, `validate_edge_properties`), `tap_grid/models.py` (`Edge.save()`), `tap_grid/services.py` (`update_edge_properties()`), and `tap_plugins/base.py` (`_register_edge_constraints()`). Tests in `tap_grid/tests/test_constraints.py` under `TestEdgePropertySchemaRegistry` and `TestValidateEdgeProperties`, `tap_grid/tests/test_models.py` under `TestEdgePropertyValidation`, and `tap_grid/tests/test_services.py` under `TestUpdateEdgeProperties`.

#### Implementation
**Schema declaration source**
- `property_schema` is declared on edge type definitions in registered app `edge_types`.
- At app startup, declared schemas are loaded into an in-memory registry in `tap_grid/constraints.py`, patterned after `_EDGE_TYPE_REGISTRY`.

**In-memory registry design**
- Registry name: `_EDGE_PROPERTY_SCHEMA_REGISTRY`.
- Key: `edge_type` slug (`str`).
- Value: JSON Schema object (`dict[str, Any]`) used to validate `Edge.properties`.
- Accessors:
  - `register_edge_property_schema(edge_type, property_schema)` for startup registration.
  - `get_edge_property_schema(edge_type)` for runtime lookup during create/update.
- Lifecycle:
  - Populated during app registration from all registered app `edge_types` declarations (core apps and plugins).
  - Read-only during request handling; writes happen only during startup/registration.
- Conflict policy:
  - If a schema is already registered for an `edge_type`, any additional schema registration for that same `edge_type` raises a configuration error.
  - No merge behavior is allowed for property schemas (unlike constraint union), to prevent silent drift/overwrite.

Example:

```python
edge_types = [
    {
        "slug": "USES_PANEL",
        "sources": [{"type": "page"}],
        "targets": [{"type": "panel"}],
        "property_schema": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {"type": "string", "pattern": "^[a-z][a-z0-9-]*$"},
            },
        },
    },
]
```

**Validation scope**
- Validation runs on every edge creation.
- Validation runs on every edge property update.
- This includes any canonical service-layer mutation path and direct model save paths that change `properties`.

**Validation behavior**
- Runtime validation resolves schema via `get_edge_property_schema(edge_type)`.
- If schema exists, validate `properties` against that schema.
- If schema is missing, skip property validation entirely.
- When schema is missing, any JSON value is accepted for `properties`.
- Schema strictness (including `additionalProperties`) is fully controlled by schema authors.

**Error behavior**
- Property schema validation failures raise a dedicated error type: `EdgePropertyValidationError`.
- Validation failure blocks persistence of invalid properties.

#### Development
Property validation should be implemented as a standalone validation step that composes with existing edge constraint checks (`validate_edge`) but remains logically separate from topology permission checks.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-edge-properties-1 | Schema Defined in edge_types | Implemented | `property_schema` may be declared on registered app `edge_types` entries and is used as the runtime source for property validation. | Not sourced from `EntityType`. |
| req-grid-edge-properties-2 | In-Memory Registry Stores Schemas | Implemented | Startup registration loads declared schemas into `_EDGE_PROPERTY_SCHEMA_REGISTRY`, keyed by edge type slug. | Patterned after constraints registries. |
| req-grid-edge-properties-3 | Registry Duplicate Is Error | Implemented | Registering a second schema for an already-registered edge type raises a configuration error. | No merge or overwrite behavior. |
| req-grid-edge-properties-4 | Validate on Create | Implemented | Edge property payloads are validated against registry-provided schema on every edge creation when a schema is defined for the edge type. | |
| req-grid-edge-properties-5 | Validate on Update | Implemented | Edge property payloads are validated against registry-provided schema on every edge property update when a schema is defined for the edge type. | |
| req-grid-edge-properties-6 | Missing Schema Skips Validation | Implemented | If an edge type has no registered schema, property validation is not executed. | |
| req-grid-edge-properties-7 | Any JSON Allowed Without Schema | Implemented | When no schema is registered for an edge type, `properties` may be any valid JSON value. | |
| req-grid-edge-properties-8 | Dedicated Validation Error | Implemented | Schema validation failures raise `EdgePropertyValidationError` rather than `InvalidEdgeError`. | |
| req-grid-edge-properties-9 | Schema Author Controls Strictness | Implemented | The system does not impose default `additionalProperties`; strictness is determined by each schema definition. | |

#### Future
Define a shared helper for schema lookup and validation so create/update paths cannot drift and all property mutations enforce identical behavior.


### PRODUCED_BATCH Standard Edge

RID: `req-grid-edge-produced-batch`
Status: `Implemented`

`PRODUCED_BATCH` is the **canonical, grid-standard edge** from a batch-producing entity to the `Batch` it created. Any code that generates a `Batch` — collectors, GRIFT-import callers, future ingestion or API surfaces — relates the producing record to the resulting `Batch` through a `PRODUCED_BATCH` edge rather than embedding batch entity IDs inside the producer's own fields. `Batch` is `BaseModel`-backed and therefore on the entity spine; the producer→batch relationship is a graph relationship and MUST be expressed as an edge so it is traversable (visualization, traversal language, read surfaces) instead of opaque producer-local JSON.

Endpoints and direction:

- **Direction:** producer → batch. `from_entity` is the producing record (e.g. a `CollectionJob`); `to_entity` is the `Batch`.
- **Target constraint:** `to` is always the `batch` entity type.
- **Source constraint:** open by design — any producer entity type may originate a `PRODUCED_BATCH` edge. New producers reuse the standard edge and do not amend this requirement.
- Registered by **tap_grid core** as an edge-type constraint via `register_edge_type_constraints` (not a per-plugin `edges/*.edge.json` or per-node `OUTBOUND_EDGES` declaration), so the edge is uniform everywhere and owned by the grid. The registration lives in `tap_grid/core_edges.py` (`register_core_edges()`), called from `TapCoreConfig.ready()`.

Property schema (registered via `register_edge_property_schema`):

- `disposition` (string, required): one of `imported` (the producer wrote/created this batch on this run) or `skipped` (the producer submitted this batch but the importer skipped it as already-present / idempotent). This preserves, in one traversable relationship, the information previously carried by an embedded `{"imported": [...], "skipped": [...]}` split.
- No default `additionalProperties` is imposed (per `req-grid-edge-properties-9`); producers may extend with their own validated properties.

Edges are created through the canonical `create_edge()` service path (`req-grid-edge-service`). This requirement supersedes embedded batch-ID-list patterns: a caller that previously stored `{"imported": [...], "skipped": [...]}` (e.g. `CollectionJob.grift_batches`) instead creates one `PRODUCED_BATCH` edge per batch with the appropriate `disposition`. The producer's own sole-writer / terminal-state rules govern *when* the edges are created, not whether.

**Demand signals.** Beyond replacing embedded batch-ID lists, this edge has a second, independent consumer: **relative panel resolution** (`req-web-panel-entity-resolution-relative` in `tap_web/specs/spec-web-panel-entity-resolution-v0.md`) traverses `PRODUCED_BATCH` so a dropped batch-summary panel can resolve "the batch this run produced" from a run-page URL keyed by the producing `CollectionJob`. That consumer is `Proposed` (unbuilt), but no longer *blocked*: this edge now exists, so the prerequisite it named is satisfied. The first producer of these edges is the CARES collector runtime — at terminal state the `run_collector` task body creates one `PRODUCED_BATCH` edge per produced batch (`req-tap-cares-collector-grift-import-6`); the former `CollectionJob.grift_batches` JSONField has been removed.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-edge-produced-batch-1 | Core-Registered Standard Edge | Implemented | tap_grid core registers `PRODUCED_BATCH` edge-type constraints (`to` = `batch`, open source set) plus a `disposition` property schema. Not plugin- or node-declared. | `tap_grid/core_edges.py:register_core_edges()`, called from `TapCoreConfig.ready()`. |
| req-grid-edge-produced-batch-2 | Canonical Producer Relationship | Implemented | Any entity that generates a `Batch` relates to it via a `PRODUCED_BATCH` edge created through `create_edge()`, never via embedded batch-ID fields. | First producer: `tap_cares.tasks._link_produced_batches`. |
| req-grid-edge-produced-batch-3 | Disposition Property | Implemented | Each edge carries `disposition` ∈ {`imported`, `skipped`}, distinguishing batches the run wrote from batches the importer skipped as already-present. | Enforced by the registered property schema (`disposition` required, enum). |
| req-grid-edge-produced-batch-4 | Traversable Replacement | Implemented | Producer→batch relationships are discoverable by graph traversal; consumers query the edge, not producer-local JSON. Supersedes `CollectionJob.grift_batches`. | Read via `tap_grid.batch.produced_batches[_by_producer]`; `CollectionJob.grift_batches` field removed. |

#### Future

Richer per-batch properties (counts, importer diagnostics) are additive `properties` on the same edge type; they do not require a new edge type.


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
