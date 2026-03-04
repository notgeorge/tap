# Grid Entity Specification

## Philosophy

This specification captures the current architectural intent for the entity layer. The current direction favors clean abstraction layers: `Entity` as the base for higher layer concepts of `Node` and `Edge` defined as the BaseModel.  Within that model, the entity spine remains the canonical reference for a single concrete node or edge instance.

## Goals

|    |              |                                                                                 |
| :---: | ---       | ---                                                                             |
| 1. | Canonical    | Entity is the canonical reference system-of-record for grid data                |
| 2. | Dimensioned  | Entity models store the dimensionality information for their nodes and edges    |
| 3. | Metadata     | Entity instance contains the metadata common across all nodes and edges         |

## Requirement Status

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-grid-entity-spine | [Entity Spine Mapping](#entity-spine-mapping) | Implemented | `Entity` is the canonical node instance for nodes and edges |
| req-grid-entity-type | [Entity Type Declaration](#entity-type-declaration) | Approved for Development | BaseModel subclasses declare `ENTITY_TYPE`; registered in the model registry |
| req-grid-entity-base | [BaseModel Auto-Creates Entity](#basemodel-auto-creates-entity) | Approved for Development | `BaseModel.save()` auto-creates its Entity atomically when none is set |
| req-grid-entity-resolve | [Entity Resolution](#entity-resolution) | Approved for Development | `Entity.resolve()` uses the model registry to return the concrete typed object |
| req-grid-entity-ee | [Entities Are Entities](#entities-are-entities) | Deprecated | Significant architectural shift; explicitly not part of current direction |


## Explanation

An `Entity` entry on the Entity Table (also called the Entity Spine) represents a single canonical concrete typed (BaseModel) instance. Every typed model instance built on `BaseModel` will corresponds to exactly one `Entity` through a one-to-one mapping. This keeps the cross-cutting metadata on the spine while allowing typed tables such as `Character` to hold type-specific fields and allows edges to be defined as having a source Entity ID and a destination Entity ID.

### Background
The Entity Spine is what makes traversal across Entity types consistent without having to duplicate the metadata fields on every BaseModel derived table.  Honestly I could have gone that route but for reasons even I'm not clear on we're going with the spine approach first.


## Requirements

### Entity Spine Mapping
----
RID: `req-grid-entity-spine`
Status: `Implemented`

#### Status Details
This is being worked out retroactively following creation of the entity spine since we didn't fully spec it out and were just shooting from the hip.

#### Implementation
The mapping is:

| Layer | Role |
| --- | --- |
| `Entity` | Canonical concrete reference for every BaseModel instance containing cross-cutting metadata |
| `BaseModel` subclass | Typed one-to-one implementation of an instance that references the Entity Id|

BaseModel creates a new Entity and applies the necessary default values when a new BaseModel subclass instance is saved without an existing entity. On save it stores the appropriate Entity and typed class into its particular table. See `req-grid-entity-base` for the full auto-creation behavior.

#### Development
The initial implementation didn't actually automatically tie the Entity and BaseModel creation together. Implementing this spec is intended to fix that so that Entity creation happens at the same time as a typed model is created.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-entity-spine-1 | Entity Is Canonical Instance | Implemented | `Entity` is treated as the canonical concrete base instance stored in the entity spine. | |
| req-grid-entity-spine-2 | One-to-One Extension | Implemented | Each typed entity model extending `BaseModel` maps to exactly one `Entity` through a one-to-one relationship. | |
| req-grid-entity-spine-3 | BaseModel Creates Entity | Approved for Development | When saving a new BaseModel instance without an entity set, an `Entity` is automatically created using the subclass's `ENTITY_TYPE` and `get_display_name()`. See `req-grid-entity-base`. | |
| req-grid-entity-spine-4 | BaseModel Confirms Entity | Approved for Development | When saving a BaseModel instance that already has an entity set, it confirms the Entity exists on the spine and that its `entity_type` matches the subclass's `ENTITY_TYPE`. Raises `ValueError` otherwise. | |

#### Future


---

### Entity Type Declaration
----
RID: `req-grid-entity-type`
Status: `Approved for Development`

#### Status Details
Needed to support auto-Entity creation (`req-grid-entity-base`) and model registry lookup (`req-grid-entity-resolve`). Every BaseModel subclass must declare what entity type it represents.

#### Implementation
Each non-abstract BaseModel subclass declares a `ENTITY_TYPE` class variable:

```python
class Concept(BaseModel):
    ENTITY_TYPE: ClassVar[str] = "concept"
```

During `__init_subclass__` (which already fires for FLIP config and edge constraint registration), the subclass is registered in the model registry:

```python
# tap_grid/registry.py
_ENTITY_MODEL_REGISTRY: dict[str, type[BaseModel]] = {}

def register_entity_type(entity_type: str, model_cls: type) -> None:
    _ENTITY_MODEL_REGISTRY[entity_type] = model_cls

def get_model_class(entity_type: str) -> type:
    ...
```

`Edge` is a BaseModel subclass and declares `ENTITY_TYPE = "edge"`. All existing plugin models (`Concept`, `Precept`, `Character`, etc.) must be updated to add their `ENTITY_TYPE`.

Abstract BaseModel subclasses (i.e., those that don't map to their own table) must not be registered and should not declare `ENTITY_TYPE`.

#### Development
`__init_subclass__` already handles FLIP config and edge constraint registration. Adding the model registry there keeps all class-level setup in one place and avoids the need for a separate `AppConfig.ready()` import dance.

The `entity_type` string on `Entity` becomes authoritative only if it matches what's in the registry. This is enforced at save time (`req-grid-entity-spine-4`).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-entity-type-1 | ENTITY_TYPE Required | Approved for Development | Every concrete BaseModel subclass declares `ENTITY_TYPE: ClassVar[str]`. Attempting to save a subclass without it raises `ImproperlyConfigured`. | |
| req-grid-entity-type-2 | Registry Population | Approved for Development | `__init_subclass__` registers the subclass in `_ENTITY_MODEL_REGISTRY` keyed by `ENTITY_TYPE`. | |
| req-grid-entity-type-3 | No Duplicate Types | Approved for Development | Registering a duplicate `ENTITY_TYPE` raises `ImproperlyConfigured` at class definition time. | |
| req-grid-entity-type-4 | Abstract Subclasses Excluded | Approved for Development | Abstract BaseModel subclasses (Meta.abstract = True) are not registered and do not require `ENTITY_TYPE`. | |

#### Future
Consider a management command or system check that validates all registered entity types against the current entity spine contents to surface data integrity issues at startup.

---

### BaseModel Auto-Creates Entity
----
RID: `req-grid-entity-base`
Status: `Approved for Development`

#### Status Details
This is the core gap in the current implementation. Entity creation is currently a manual two-step: call `create_entity()` then pass `entity=...` to the BaseModel subclass constructor. This requirement closes that gap by making Entity creation automatic and atomic.

#### Implementation
`BaseModel.save()` is overridden to handle Entity auto-creation:

```python
def save(self, *args, **kwargs):
    if self.entity_id is None:
        with transaction.atomic():
            entity = Entity.objects.create(
                entity_type=self.ENTITY_TYPE,
                display_name=self.get_display_name(),
                originating_grid_id=self.originating_grid_id,
            )
            self.entity = entity
            super().save(*args, **kwargs)
    else:
        # Entity already set — confirm it (spine-4)
        self._confirm_entity()
        super().save(*args, **kwargs)
```

`get_display_name()` is an overridable method on BaseModel that returns `""` by default. Subclasses may override it to provide a meaningful default:

```python
def get_display_name(self) -> str:
    return ""
```

`_confirm_entity()` validates that the entity exists and that its `entity_type` matches `self.ENTITY_TYPE`. Raises `ValueError` if either check fails.

The `create_edge()` service function in `tap_grid/services.py` must be refactored to remove its manual Entity pre-creation and instead rely on this mechanism. The service call becomes `Edge.objects.create(from_entity=..., to_entity=..., edge_type=...)`.

#### Development
The `entity` OneToOneField is currently non-nullable, which means it is required at the database level. The `save()` override intercepts before the DB write, so the field is populated before Django's insert. No schema change is needed.

Passing an explicit `entity=` on construction remains valid for migration compatibility and testing. The `_confirm_entity()` path handles that case and enforces consistency rather than silently accepting whatever is passed.

`transaction.atomic()` ensures the Entity row and the domain model row are either both committed or both rolled back. Without this, a failure between the two creates an orphaned Entity row on the spine.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-entity-base-1 | Auto-Creation on Save | Approved for Development | Saving a new BaseModel subclass instance without `entity` set automatically creates an `Entity` row with the correct `entity_type` and `display_name`. | |
| req-grid-entity-base-2 | Atomic Transaction | Approved for Development | Entity creation and BaseModel row insertion are wrapped in `transaction.atomic()`. A failure in either rolls back both. | |
| req-grid-entity-base-3 | Overridable Display Name | Approved for Development | `get_display_name()` returns `""` by default; subclasses may override to provide a meaningful name without requiring callers to set it. | |
| req-grid-entity-base-4 | Explicit Entity Still Valid | Approved for Development | Passing an explicit `entity=` remains valid; the save path skips auto-creation and instead confirms the entity (spine-4). | |
| req-grid-entity-base-5 | create_edge Refactored | Approved for Development | `tap_grid/services.py create_edge()` no longer manually creates its backing Entity; it relies on `Edge.save()` auto-creation instead. | |

#### Future
Once FLIP is fully active, Entity creation through this path should be recorded as a provenance event. In v0 this is deferred; the mechanism should be hookable so FLIP can be wired in without changing this code.

---

### Entity Resolution
----
RID: `req-grid-entity-resolve`
Status: `Approved for Development`

#### Status Details
Given an Entity instance (or entity_id), there is currently no clean way to get back to the concrete typed object without knowing its type in advance. This requirement adds that capability via the model registry populated by `req-grid-entity-type`.

#### Implementation
`Entity` gains a `resolve()` instance method:

```python
def resolve(self) -> "BaseModel":
    """Return the concrete typed object for this Entity."""
    from tap_grid.registry import get_model_class
    model_cls = get_model_class(self.entity_type)
    return model_cls.objects.get(entity_id=self.pk)
```

A module-level helper function in `tap_grid/registry.py` provides the same capability from an entity_id alone:

```python
def resolve_entity(entity_id: UUID) -> "BaseModel":
    entity = Entity.objects.get(pk=entity_id)
    return entity.resolve()
```

Two DB hits total: one for the Entity row, one for the concrete table. If the Entity is already in hand the second hit is skipped. Future optimization via a JOIN is possible if performance requires it.

#### Development
Django's `related_name="%(class)s"` on the OneToOneField already creates reverse accessors (`entity.concept`, `entity.edge`, etc.) but using them requires knowing the type in advance. `resolve()` replaces the need to try accessors speculatively. It also provides a single stable API surface that does not change as new entity types are added.

The model registry is populated at class definition time via `__init_subclass__`, so it is always fully populated before any request or task can call `resolve()`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-entity-resolve-1 | Resolve Returns Typed Object | Approved for Development | `entity.resolve()` returns the concrete BaseModel subclass instance corresponding to that Entity. | |
| req-grid-entity-resolve-2 | resolve_entity Helper | Approved for Development | `resolve_entity(entity_id)` in `tap_grid/registry.py` resolves from a UUID without requiring a pre-fetched Entity instance. | |
| req-grid-entity-resolve-3 | Unregistered Type Raises Error | Approved for Development | Resolving an entity whose `entity_type` is not in the registry raises a clear `KeyError` or custom exception with a descriptive message. | |
| req-grid-entity-resolve-4 | Edge Resolves Correctly | Approved for Development | `entity.resolve()` works for entities whose type is `"edge"`, returning the `Edge` instance. | |

#### Future
Consider caching the resolved object on the Entity instance (e.g., `_resolved`) to avoid repeat DB hits when resolve() is called multiple times in the same request. A `select_related` variant that pre-fetches the typed object in a single JOIN query would be a further optimization if graph traversal volume warrants it.

---

### Entities Are Entities
----
RID: `req-grid-entity-ee`
Status: `Deprecated`

#### Status Details
This concept is intentionally shelved. It was a one-off idea rather than a thoroughly developed architectural requirement, and it introduces a major abstraction shift that is not justified by the current direction of the project.

#### Implementation
Do not implement this requirement as part of the current grid model work.

#### Development
The project is converging on a cleaner layered model:

| Layer | Role |
| --- | --- |
| Entity / Edge | Low-level graph primitives and concrete data instances |
| Graph | A coherent graph composed of those primitives |
| Dimensions | Higher-level scoping and organizational metadata applied across the graph |

Forcing entities themselves to be entities collapses abstraction layers in a way that may be possible, but is not desirable for the current design. If this idea is revisited later, it should be reintroduced with a fresh spec and a stronger architectural case.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-entity-ee-1 | Concept Withdrawn | Deprecated | The `Entities Are Entities` concept is not part of the current implementation direction. | |
| req-grid-entity-ee-2 | Preserve Context Only | Deprecated | This spec is retained only as historical context, not as an active implementation target. | |

#### Future

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
