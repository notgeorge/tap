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
| req-grid-entity-type | [Entity Type Declaration](#entity-type-declaration) | Implemented | BaseModel subclasses declare `ENTITY_TYPE`; registered in the model registry |
| req-grid-entity-base | [BaseModel Auto-Creates Entity](#basemodel-auto-creates-entity) | Implemented | `BaseModel.save()` auto-creates its Entity atomically when none is set |
| req-grid-entity-resolve | [Entity Resolution](#entity-resolution) | Implemented | `Entity.resolve()` uses the model registry to return the concrete typed object |
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
Implemented and verified. The entity spine mapping was the original architecture; the auto-creation and confirmation behavior was added in the session that produced `req-grid-entity-base`.

#### Implementation
The mapping is:

| Layer | Role |
| --- | --- |
| `Entity` | Canonical concrete reference for every BaseModel instance containing cross-cutting metadata |
| `BaseModel` subclass | Typed one-to-one implementation of an instance that references the Entity Id|

`BaseModel.save()` creates a new Entity automatically when a new instance is saved without an existing entity. On save it stores the appropriate Entity and typed class into its particular table. See `req-grid-entity-base` for the full auto-creation behavior.

#### Development
The initial implementation didn't automatically tie Entity and BaseModel creation together. `req-grid-entity-base` closes that gap. The `entity` OneToOneField is non-nullable at the schema level; the `save()` override ensures the field is populated before Django's insert, so no schema change was required.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-entity-spine-1 | Entity Is Canonical Instance | Implemented | `Entity` is treated as the canonical concrete base instance stored in the entity spine. | |
| req-grid-entity-spine-2 | One-to-One Extension | Implemented | Each typed entity model extending `BaseModel` maps to exactly one `Entity` through a one-to-one relationship. | |
| req-grid-entity-spine-3 | BaseModel Creates Entity | Implemented | When saving a new BaseModel instance without an entity set, an `Entity` is automatically created using the subclass's `ENTITY_TYPE` and `get_display_name()`. See `req-grid-entity-base`. | |
| req-grid-entity-spine-4 | BaseModel Confirms Entity | Implemented | When saving a BaseModel instance that already has an entity set, it confirms the Entity exists on the spine and that its `entity_type` matches the subclass's `ENTITY_TYPE`. Raises `ValueError` otherwise. | |

#### Future


---

### Entity Type Declaration
----
RID: `req-grid-entity-type`
Status: `Implemented`

#### Status Details
Implemented and verified. All concrete BaseModel subclasses across `tap_grid`, `tap_flip`, `tap_viz`, and all plugins now declare `ENTITY_TYPE`.

#### Implementation
Each non-abstract BaseModel subclass declares `ENTITY_TYPE` in its class body:

```python
class Concept(BaseModel):
    ENTITY_TYPE: ClassVar[str] = "concept"
```

During `__init_subclass__`, any subclass that declares `ENTITY_TYPE` in its own `__dict__` (not inherited) is registered in the model registry in `tap_grid/registry.py`:

```python
_ENTITY_MODEL_REGISTRY: dict[str, type] = {}

def register_entity_type(entity_type: str, model_cls: type) -> None:
    ...  # raises ImproperlyConfigured on duplicate slug registered to a different class

def get_model_class(entity_type: str) -> type:
    ...  # raises KeyError with descriptive message if not found
```

`__init_subclass__` also switches edge constraint registration to use `ENTITY_TYPE` as the key (previously used `cls.__name__.lower()`), with a fallback for abstract intermediaries that define edge shapes without declaring a concrete type.

Registered types as of implementation: `edge`, `concept`, `precept`, `batch`, `layout`, `dimension`, `character`, `location`, `artifact`, `race`, `faction`, `sentinel`, `citadel`, `wanderer`.

#### Development
`__init_subclass__` already handled FLIP config and edge constraint registration. Adding the model registry there keeps all class-level setup in one place and avoids a separate `AppConfig.ready()` import dance. Using `cls.__dict__.get("ENTITY_TYPE")` (not `getattr`) ensures only classes that explicitly declare the attribute are registered — inherited values from abstract parents do not accidentally trigger registration.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-entity-type-1 | ENTITY_TYPE Required | Implemented | Every concrete BaseModel subclass declares `ENTITY_TYPE: ClassVar[str]`. Attempting to save a subclass without it raises `ImproperlyConfigured`. | |
| req-grid-entity-type-2 | Registry Population | Implemented | `__init_subclass__` registers the subclass in `_ENTITY_MODEL_REGISTRY` keyed by `ENTITY_TYPE`. | |
| req-grid-entity-type-3 | No Duplicate Types | Implemented | Registering a duplicate `ENTITY_TYPE` raises `ImproperlyConfigured` at class definition time. | |
| req-grid-entity-type-4 | Abstract Subclasses Excluded | Implemented | Abstract BaseModel subclasses omit `ENTITY_TYPE` and are not registered. | |

#### Future
Consider a management command or system check that validates all registered entity types against the current entity spine contents to surface data integrity issues at startup.

---

### BaseModel Auto-Creates Entity
----
RID: `req-grid-entity-base`
Status: `Implemented`

#### Status Details
Implemented and verified. All 265 tests pass including the new auto-creation, entity confirmation, and edge endpoint validation tests.

#### Implementation
`BaseModel.save()` is overridden to handle Entity auto-creation:

```python
def save(self, *args, **kwargs):
    entity_type = getattr(self.__class__, "ENTITY_TYPE", None)
    if entity_type is None:
        raise ImproperlyConfigured(...)

    if self.entity_id is None:
        with transaction.atomic():
            base_dims = dict(getattr(self.__class__, "DEFAULT_DIMENSIONS", {}))
            caller_dims = getattr(self, "_initial_dimensions", {})
            self.entity = Entity.objects.create(
                entity_type=entity_type,
                display_name=self.get_display_name(),
                originating_grid_id=self.originating_grid_id,
                dimensions={**base_dims, **caller_dims},
            )
            super().save(*args, **kwargs)
    else:
        self._confirm_entity()
        super().save(*args, **kwargs)
```

`get_display_name()` returns `""` by default; subclasses override it to provide a meaningful label. `Edge` overrides it to produce `"<from_id> --[<type>]--> <to_id>"`.

`_confirm_entity()` validates that the entity exists and its `entity_type` matches `self.ENTITY_TYPE`. Raises `ValueError` if either check fails.

`DEFAULT_DIMENSIONS` (optional `ClassVar[dict[str, str]]` on BaseModel subclasses) seeds the `dimensions` field on the auto-created Entity. Caller-supplied `_initial_dimensions` are merged on top. See `spec-grid-dimension.md` for full dimension semantics.

`Edge` overrides `save()` to add endpoint validation before delegating to `BaseModel.save()`:
- Confirms `from_entity` exists on the spine; raises `ValueError` if not.
- Confirms `to_entity` exists on the spine; raises `ValueError` if not.
- Inherits `DEFAULT_DIMENSIONS` from the source node's model class.
This check runs before any write, so a failed validation leaves no orphaned Entity row.

`create_edge()` in `tap_grid/services.py` was refactored to rely on `Edge.save()` auto-creation rather than manually pre-creating the backing Entity.

#### Development
`transaction.atomic()` ensures the Entity row and the domain model row are either both committed or both rolled back. Without this, a failure between the two creates an orphaned Entity row on the spine.

Passing an explicit `entity=` on construction remains valid for migration compatibility and testing. The `_confirm_entity()` path handles that case and enforces consistency rather than silently accepting whatever is passed.

The dimensions integration was added concurrently with the dimension spec work; the Entity `dimensions` JSONField and the `DEFAULT_DIMENSIONS` class variable on BaseModel were introduced as part of `spec-grid-dimension.md`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-entity-base-1 | Auto-Creation on Save | Implemented | Saving a new BaseModel subclass instance without `entity` set automatically creates an `Entity` row with the correct `entity_type` and `display_name`. | |
| req-grid-entity-base-2 | Atomic Transaction | Implemented | Entity creation and BaseModel row insertion are wrapped in `transaction.atomic()`. A failure in either rolls back both. | |
| req-grid-entity-base-3 | Overridable Display Name | Implemented | `get_display_name()` returns `""` by default; subclasses may override to provide a meaningful name without requiring callers to set it. | |
| req-grid-entity-base-4 | Explicit Entity Still Valid | Implemented | Passing an explicit `entity=` remains valid; the save path skips auto-creation and instead confirms the entity (spine-4). | |
| req-grid-entity-base-5 | create_edge Refactored | Implemented | `tap_grid/services.py create_edge()` no longer manually creates its backing Entity; it relies on `Edge.save()` auto-creation instead. | |
| req-grid-entity-base-6 | Edge Endpoint Validation | Implemented | `Edge.save()` confirms both `from_entity` and `to_entity` exist on the spine before any write. Raises `ValueError` with a clear message identifying which endpoint is missing. | |
| req-grid-entity-base-7 | No Orphan on Failed Validation | Implemented | A failed endpoint check in `Edge.save()` leaves no orphaned Entity row on the spine. | |

#### Future
Once FLIP is fully active, Entity creation through this path should be recorded as a provenance event. In v0 this is deferred; the mechanism should be hookable so FLIP can be wired in without changing this code.

---

### Entity Resolution
----
RID: `req-grid-entity-resolve`
Status: `Implemented`

#### Status Details
Implemented and verified. `entity.resolve()` and `resolve_entity()` are live and tested for `Concept`, `Precept`, and `Edge`.

#### Implementation
`Entity` has a `resolve()` instance method:

```python
def resolve(self) -> "BaseModel":
    from tap_grid.registry import get_model_class
    model_cls = get_model_class(self.entity_type)
    return model_cls.objects.get(entity_id=self.pk)
```

`tap_grid/registry.py` provides a module-level helper for resolving from a UUID alone:

```python
def resolve_entity(entity_id: UUID) -> "BaseModel":
    entity = Entity.objects.get(pk=entity_id)
    return entity.resolve()
```

Two DB hits total: one for the Entity row (to get `entity_type`), one for the concrete table. If the Entity is already in hand, `entity.resolve()` skips the first hit.

#### Development
Django's `related_name="%(class)s"` on the OneToOneField creates reverse accessors (`entity.concept`, `entity.edge`, etc.) but using them requires knowing the type in advance. `resolve()` replaces the need to try accessors speculatively and provides a stable API surface that does not change as new entity types are added.

The model registry is always fully populated before any request or task can call `resolve()` because `__init_subclass__` fires at class definition time during app startup.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-entity-resolve-1 | Resolve Returns Typed Object | Implemented | `entity.resolve()` returns the concrete BaseModel subclass instance corresponding to that Entity. | |
| req-grid-entity-resolve-2 | resolve_entity Helper | Implemented | `resolve_entity(entity_id)` in `tap_grid/registry.py` resolves from a UUID without requiring a pre-fetched Entity instance. | |
| req-grid-entity-resolve-3 | Unregistered Type Raises Error | Implemented | Resolving an entity whose `entity_type` is not in the registry raises `KeyError` with a descriptive message listing registered types. | |
| req-grid-entity-resolve-4 | Edge Resolves Correctly | Implemented | `entity.resolve()` works for entities whose type is `"edge"`, returning the `Edge` instance. | |

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
