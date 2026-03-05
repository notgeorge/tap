# Grid Node Specification

## Philosophy

Nodes are the typed participants of the grid. Each node type is a concrete `BaseModel` subclass that pairs a type-specific table with a row on the entity spine. The `BaseModel` pattern provides the machinery that makes a plain Django model a first-class graph citizen — spine attachment, type registration, constraint declaration, and dimension defaults — without requiring plugin authors to know the internals.

## Goals

|    |               |                                                                                                  |
| :---: | ---        | ---                                                                                              |
| 1. | Typed         | Nodes declare a type slug (`ENTITY_TYPE`) that identifies their role in the graph               |
| 2. | Extensible    | Adding a new node type requires only a `BaseModel` subclass; no framework changes are needed    |
| 3. | First-Class   | Nodes are entities: each node instance has a backing `Entity` row on the spine                  |


## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-grid-node-model | [Node Model Declaration](#node-model-declaration) | Implemented | `BaseModel` provides the abstract pattern all node types inherit |
| req-grid-node-display | [Node Display Name](#node-display-name) | Implemented | `get_display_name()` produces the label stored on the backing Entity at creation time |
| req-grid-node-service | [Node Service Layer](#node-service-layer) | Implemented | `create_entity()`, `update_entity()`, and `delete_entity()` as the canonical Entity-level service API |
| req-grid-node-constraints | [Node Constraint Declaration](#node-constraint-declaration) | Implemented | `OUTBOUND_EDGES` / `INBOUND_EDGES` declared on node types; registered at class-definition time |


## Explanation

Nodes in the grid are typed objects. Concretely, a node is any instance of a concrete `BaseModel` subclass — `Concept`, `Precept`, `Dimension`, `Character`, etc. The `BaseModel` pattern ensures:

1. Every node instance has a corresponding `Entity` row on the spine (the canonical reference).
2. Every node type declares an `ENTITY_TYPE` slug, registered in the model registry at class-definition time.
3. Node creation is atomic with Entity creation — no partial state enters the graph.
4. Edge constraints are declared on the node type and enforced at the service layer when edges are created.

Nodes are distinct from edges (which model relationships between nodes) and from `Entity` (the spine record that backs them). The entity spec (`spec-grid-entity.md`) covers Entity-centric concerns: spine structure, type declaration, auto-creation machinery, and resolution. This spec covers node-centric concerns: the `BaseModel` pattern itself, how a new node type is declared, the display name convention, and the service API for node instances.


### Node Model Declaration
----
RID: `req-grid-node-model`
Status: `Implemented`

`BaseModel` is the abstract Django model that every node type inherits from. It provides the common fields, the spine attachment machinery, and the class-definition hooks that register the type in the model registry and constraint system.

#### Status Details
Implemented in `tap_grid/models.py` as `class BaseModel(models.Model)`. Retroactively specified here.

#### Implementation
**Fields inherited by every node type:**

| Field | Type | Notes |
| --- | --- | --- |
| `entity` | OneToOneField → Entity, CASCADE | The backing spine record. Auto-created on first save if not set. |
| `batch_id` | CharField(36, db_index=True) | UUIDv7 of the FLIP batch this change was part of (Phase 2). |

`originating_grid_id`, `created_at`, and `updated_at` live on `Entity` — the authoritative source of record. `BaseModel.save()` touches `entity.updated_at` on every typed-model save so the Entity timestamp stays current.

`BaseModel.Meta` sets `abstract = True` — no `tap_basemodel` table is created.

**`__init_subclass__` hooks** (fire at class-definition time, before any request):

| Hook | Effect |
| --- | --- |
| Model registry | If the subclass declares `ENTITY_TYPE` in its own `__dict__`, calls `register_entity_type()` in `tap_grid/registry.py`. Abstract subclasses that omit `ENTITY_TYPE` are skipped. |
| Constraint registration | If the subclass declares `OUTBOUND_EDGES` or `INBOUND_EDGES`, calls `register_constraints()` in `tap_grid/constraints.py`. |
| FLIP config | Calls `get_model_flip_config()` to cache the subclass's FLIP configuration at class-definition time. |

A minimal concrete node type declaration:

```python
class Concept(BaseModel):
    ENTITY_TYPE: ClassVar[str] = "concept"
    summary = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "core_examples_concept"
```

Creating an instance auto-creates the backing Entity:

```python
concept = Concept.objects.create(summary="Separation of Concerns")
# concept.entity is now a persisted Entity row with entity_type="concept"
```

#### Development

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-node-model-1 | BaseModel Is Abstract | Implemented | `BaseModel` sets `Meta.abstract = True`; no `tap_basemodel` table exists in the schema. | |
| req-grid-node-model-2 | Common Fields Present | Implemented | Every concrete `BaseModel` subclass inherits `entity` and `batch_id`. Timestamps and grid ID live on the backing Entity. | |
| req-grid-node-model-3 | Registry Hook | Implemented | `__init_subclass__` registers the subclass in `_ENTITY_MODEL_REGISTRY` when `ENTITY_TYPE` is declared in the subclass's own `__dict__`. Abstract subclasses that omit `ENTITY_TYPE` are not registered. | |
| req-grid-node-model-4 | Constraint Hook | Implemented | `__init_subclass__` calls `register_constraints()` when `OUTBOUND_EDGES` or `INBOUND_EDGES` is present on the subclass. | |
| req-grid-node-model-5 | FLIP Hook | Implemented | `__init_subclass__` calls `get_model_flip_config()` to cache FLIP config for the subclass at class-definition time. | |

#### Future
Consider a Django system check that validates all registered `ENTITY_TYPE` values against the `EntityType` table at startup to surface misconfigured plugins early or a more clever way to automagically assign names that won't risk namespace pollution.  
Consider revisiting whether `batch_id` should move to `Entity` or be handled differently once FLIP matures — the tight entity-node coupling may change how FLIP tracks provenance.


### Node Display Name
----
RID: `req-grid-node-display`
Status: `Implemented`

When a node is created, `BaseModel.save()` stores a display name on the backing Entity via `get_display_name()`. This label is visible wherever the Entity is referenced without resolving back to the typed model.

#### Status Details
Implemented in `tap_grid/models.py`. Retroactively specified here.

#### Implementation
`BaseModel` defines:

```python
def get_display_name(self) -> str:
    """Return the display name for the auto-created Entity.

    Defaults to empty string. Subclasses may override to provide a
    meaningful label without requiring callers to set it explicitly.
    """
    return ""
```

This method is called inside the auto-creation path of `BaseModel.save()`:

```python
self.entity = Entity.objects.create(
    entity_type=entity_type,
    display_name=self.get_display_name(),
    ...
)
```

The default returns an empty string. Subclasses override it to produce a meaningful label from their own fields:

```python
class Concept(BaseModel):
    def get_display_name(self) -> str:
        return self.summary[:80] if self.summary else ""
```

`Edge` overrides `get_display_name()` to produce a structural label: `"{from_entity_id} --[{edge_type}]--> {to_entity_id}"`.

The display name is a soft label. It is set at creation time and not automatically kept in sync if relevant fields change afterward. Callers that update fields used in `get_display_name()` should update `entity.display_name` explicitly if the label matters downstream.

#### Development

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-node-display-1 | Default Returns Empty String | Implemented | `BaseModel.get_display_name()` returns `""` by default. | |
| req-grid-node-display-2 | Stored on Backing Entity | Implemented | `BaseModel.save()` passes `get_display_name()` as `display_name` when calling `Entity.objects.create()`. | |
| req-grid-node-display-3 | Subclass Override | Implemented | Subclasses may override `get_display_name()` to return a meaningful label without requiring callers to set it. | `Edge` is the primary example in `tap_grid`. |

#### Future
Consider a `sync_display_name()` helper or a post-save signal that re-syncs `entity.display_name` when the domain model's relevant fields are updated, so the Entity label stays consistent over the lifetime of the node.


### Node Service Layer
----
RID: `req-grid-node-service`
Status: `Implemented`

`tap_grid/services.py` provides the canonical service-layer API for Entity-level node operations. Application code that creates, updates, or deletes entity spine records should use these functions rather than direct ORM calls, so that FLIP can be wired in at these call sites without changing callers.

#### Status Details
Implemented in `tap_grid/services.py`. Retroactively specified here.

#### Implementation
**`create_entity(entity_type, display_name="", **kwargs) -> Entity`**:
Creates a bare Entity record directly on the spine. Intended for cases where a typed domain model does not exist or is not needed — e.g., tests that need an entity as an edge endpoint, or raw entity creation where the type has no domain model. For typed node creation, `ModelClass.objects.create(...)` is the standard path; `BaseModel.save()` auto-creates the backing Entity atomically.

**`update_entity(entity, **kwargs) -> Entity`**:
Updates the named fields on an Entity instance and calls `save(update_fields=[...])`. Avoids clobbering unspecified fields. Returns the updated Entity.

**`delete_entity(entity) -> None`**:
Deletes the Entity row. Cascades to the typed domain model row via the `OneToOneField` and to all `Edge` rows that reference this Entity as `from_entity` or `to_entity`.

#### Development

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-node-service-1 | create_entity Creates Spine Record | Implemented | `create_entity()` creates and returns an `Entity` with the given `entity_type` and optional `display_name`. | |
| req-grid-node-service-2 | update_entity Uses update_fields | Implemented | `update_entity()` calls `entity.save(update_fields=[...] + ["updated_at"])` to avoid clobbering unrelated fields. | |
| req-grid-node-service-3 | delete_entity Cascades | Implemented | `delete_entity()` deletes the Entity; the DB cascade removes the domain model row and all referencing edges. | |

#### Future
Once FLIP is active, `create_entity()`, `update_entity()`, and `delete_entity()` should record provenance events. The integration points are already identified; no call-site changes will be needed.
Consider whether typed node creation should route through a `create_node(model_cls, **kwargs)` service function to enforce FLIP recording uniformly across both the bare-entity and typed-model creation paths.


### Node Constraint Declaration
----
RID: `req-grid-node-constraints`
Status: `Implemented`

Node types declare their edge participation rules via `OUTBOUND_EDGES` and `INBOUND_EDGES` class variables. These declarations are registered at class-definition time and consumed by the edge constraint validation system. The full validation semantics — Permission Union, explicit blocks, and edge-type constraints — live in `spec-grid-edge.md` under `req-grid-edge-constraints`.

#### Status Details
Implemented in `tap_grid/models.py` (`BaseModel.__init_subclass__`) and `tap_grid/constraints.py` (`register_constraints()`). Retroactively specified here.

#### Implementation
Node types optionally declare:

```python
class Concept(BaseModel):
    OUTBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {
            "nodes": [{"type": "concept"}, {"type": "precept"}],
            "edges": [{"type": "APPLIES_TO"}],
        },
        {
            "nodes": [{"type": "concept"}],
            "edges": [{"type": "DEPENDS_ON"}],
        },
    ]
    INBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {
            "nodes": [{"type": "concept"}],
            "edges": [{"type": "APPLIES_TO"}, {"type": "DEPENDS_ON"}],
        },
    ]
```

Declaration rules:

| Declaration | Meaning |
| --- | --- |
| Entry with `"nodes"` key | This edge type may connect to/from only the listed node types |
| Entry without `"nodes"` key | Wildcard — this edge type may connect to/from any node type |
| `OUTBOUND_EDGES = []` | Explicit block-all — this node cannot create any outbound edges |
| `INBOUND_EDGES = []` | Explicit block-all — this node cannot receive any inbound edges |
| Attribute omitted entirely | Unconstrained — the node has not expressed a preference; edge-type constraints still apply |

`BaseModel.__init_subclass__` calls `register_constraints(entity_type, outbound, inbound)` which parses the declaration and stores it in `_NODE_REGISTRY` in `tap_grid/constraints.py`.

#### Development

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-node-constraints-1 | OUTBOUND_EDGES Registered | Implemented | When a subclass declares `OUTBOUND_EDGES`, `__init_subclass__` calls `register_constraints()` to store the parsed outbound rules in `_NODE_REGISTRY`. | |
| req-grid-node-constraints-2 | INBOUND_EDGES Registered | Implemented | When a subclass declares `INBOUND_EDGES`, `__init_subclass__` calls `register_constraints()` to store the parsed inbound rules in `_NODE_REGISTRY`. | |
| req-grid-node-constraints-3 | Empty List Is Explicit Block | Implemented | `OUTBOUND_EDGES = []` or `INBOUND_EDGES = []` registers a block-all that cannot be overridden by edge-type constraints. | |
| req-grid-node-constraints-4 | Omitted Attribute Is Unconstrained | Implemented | A node type that omits `OUTBOUND_EDGES` or `INBOUND_EDGES` has no registered constraint for that direction; the constraint system treats it as unconstrained. | |
| req-grid-node-constraints-5 | Wildcard Via Omitting Nodes Key | Implemented | Omitting `"nodes"` from an entry in `OUTBOUND_EDGES` or `INBOUND_EDGES` results in a wildcard — any node type is allowed for those edge types in that direction. | |

#### Future
Consider a management command that audits registered node constraints against the entity type registry to detect mismatched type slugs in constraint declarations at startup.


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
