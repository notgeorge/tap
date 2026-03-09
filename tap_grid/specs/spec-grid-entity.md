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
| req-grid-entity-validation | [BaseModel Field Validation](#basemodel-field-validation) | Implemented | Three-layer validation (JSON Schema, per-field functions, whole-record hook) on derived model fields; hooked into save() |
| req-grid-entity-cascade | [Edge-Directed Cascade Deletion](#edge-directed-cascade-deletion) | Backlog | When an entity is deleted, cascades should be expressible in terms of edge relationships, not just Django's raw FK CASCADE |


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

The `entity_types` list in `TapPluginConfig` (and equivalent `apps.py` declarations) is a separate layer from the in-memory model registry: the model registry (`_ENTITY_MODEL_REGISTRY`) is populated automatically at class-definition time and is sufficient for all functional operations. The `EntityType` DB table exists solely to serve the API's type catalogue with display metadata (`display_name`, `icon`, `description`, `plugin_name`). This creates duplication — the same type is declared once in the model and again in `apps.py`. The natural resolution is to add `DISPLAY_NAME`, `DESCRIPTION`, `ICON` as class vars on `BaseModel` subclasses and have `__init_subclass__` (or a `ready()`-time sweep of the model registry) populate `EntityType` automatically, eliminating the `entity_types` list entirely.

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
                dimensions={**base_dims, **caller_dims},
            )
            super().save(*args, **kwargs)
    else:
        self._confirm_entity()
        super().save(*args, **kwargs)
        Entity.objects.filter(pk=self.entity_id).update(updated_at=timezone.now())
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

### BaseModel Field Validation
----
RID: `req-grid-entity-validation`
Status: `Implemented`

Allows any `BaseModel` subclass (node or edge) to declare enhanced validation rules on top of Django's built-in field type coercion. The validation concerns **fields defined on the derived model** (e.g. `Concept.summary`, `Precept.statement`), not the BaseModel infrastructure fields (`entity_id`, `ENTITY_TYPE`, etc.), which BaseModel already guards internally.

#### `FIELD_SCHEMAS` — the single source of truth

`FIELD_SCHEMAS: ClassVar[dict[str, dict]]` is the explicit registry of validated fields. It has two responsibilities:

1. **Declare which fields are validated.** Any field not listed is completely ignored by `full_validate()`.
2. **Declare how each field is validated.** Each entry is a typed descriptor with a required `"validation"` key.

Two validation types are supported:

**`"jsonschema"`** — validate the field's value against a JSON Schema:

```python
FIELD_SCHEMAS: ClassVar[dict[str, dict]] = {
    "summary": {
        "validation": "jsonschema",
        "schema": {"type": "string", "minLength": 1, "maxLength": 5000},
    },
    "tags": {
        "validation": "jsonschema",
        "schema": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
    },
}
```

Schema authors control nullability via `{"type": ["string", "null"]}` or `anyOf`; no special-casing of `None` is performed by the framework.

**`"function"`** — validate the field via an instance method named `validate_<fieldname>(self) -> None`. The method reads `self.<fieldname>` directly and raises `django.core.exceptions.ValidationError` on failure:

```python
FIELD_SCHEMAS: ClassVar[dict[str, dict]] = {
    "tags": {"validation": "function"},
}

def validate_tags(self) -> None:
    if any(";" in t for t in self.tags):
        raise ValidationError({"tags": "Tags may not contain semicolons."})
```

Declaring `"validation": "function"` without a matching `validate_<fieldname>()` method is a configuration error (see Startup Invariants below).

#### Layer 2 — Whole-record hook

Override `validate(self) -> None` for cross-field or business-rule validation that spans multiple fields. The base implementation is a no-op. Raise `ValidationError` with a field-keyed dict for field errors, or a plain message for non-field (`__all__`) errors:

```python
class DateRangeNode(BaseModel):
    def validate(self) -> None:
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError({"start_date": ["Must be before end_date."]})
```

#### Startup invariants enforced by `__init_subclass__`

`BaseModel.__init_subclass__` checks the following at **class definition time** (i.e. at startup, before any request is served). Any violation raises `ImproperlyConfigured` immediately:

| Check | Error condition |
| --- | --- |
| Valid `"validation"` key | An entry in `FIELD_SCHEMAS` has a `"validation"` value other than `"jsonschema"` or `"function"` |
| Schema present for jsonschema entries | An entry with `"validation": "jsonschema"` is missing the `"schema"` key |
| Method present for function entries | An entry with `"validation": "function"` has no corresponding `validate_<field>()` method on the class |
| No undeclared validators | A `validate_<field>()` method exists but `field` is not listed in `FIELD_SCHEMAS` |
| Keys are real fields | A `FIELD_SCHEMAS` key does not correspond to a field declared on the derived model |

The last two checks enforce bidirectional consistency: `FIELD_SCHEMAS` and `validate_*` methods must always be in sync. There is no silent fallback.

#### Escape hatch — `@dangerously_ignore_validator`

A method named `validate_<something>` that is intentionally not yet wired into `FIELD_SCHEMAS` must be decorated with `@dangerously_ignore_validator`. This suppresses the "undeclared validator" startup check for that method, allowing authors to pre-stage validation code without fully activating it:

```python
class Concept(BaseModel):
    @dangerously_ignore_validator
    def validate_tags(self) -> None:
        # pre-staged but not yet in FIELD_SCHEMAS — suppresses startup error
        ...
```

`@dangerously_ignore_validator` is a one-line marker decorator defined in `tap_grid.models`. It sets a flag attribute on the method so `__init_subclass__` can skip it. The name is deliberately alarming — it signals that a validator exists but is not running, which is an unusual and potentially risky state.

#### Orchestration — `full_validate()`

`BaseModel.full_validate(self) -> None` runs all declared validators and collects every error before raising:

1. For each field in `FIELD_SCHEMAS`:
   - If `"validation": "jsonschema"`: call `jsonschema.validate(field_value, schema)`; collect any violation message keyed by field name.
   - If `"validation": "function"`: call `validate_<field>(self)`; merge any raised `ValidationError` into the error dict.
2. Call `validate(self)` (whole-record hook); merge its errors.
3. If any errors were collected, raise `ValidationError(collected_dict)`.

All errors are gathered before raising — callers receive the complete picture in a single exception, not just the first failure.

#### Integration with `save()`

`BaseModel.save()` calls `full_validate()` before entity auto-creation or any DB write. The escape hatch `skip_validation=True` bypasses it entirely (needed for data migrations, test fixtures, and admin bulk operations):

```python
concept.save()                      # validation runs
concept.save(skip_validation=True)  # validation skipped
```

#### Edge compatibility

`Edge` extends `BaseModel` and inherits the full validation mechanism. The existing edge property schema registry (`_edge_property_schema_registry`) continues to operate as a separate mechanism for `Edge.properties` and is unaffected.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-entity-validation-1 | FIELD_SCHEMAS Declaration | Implemented | A BaseModel subclass may declare `FIELD_SCHEMAS: ClassVar[dict[str, dict]]`; default is `{}`. Fields not listed are ignored by `full_validate()`. | |
| req-grid-entity-validation-2 | Typed Validation Entries | Implemented | Each entry in `FIELD_SCHEMAS` must have `"validation": "jsonschema"` or `"validation": "function"`. Any other value raises `ImproperlyConfigured` at class definition time. | |
| req-grid-entity-validation-3 | jsonschema Entry Requires Schema Key | Implemented | An entry with `"validation": "jsonschema"` that lacks a `"schema"` key raises `ImproperlyConfigured` at class definition time. | |
| req-grid-entity-validation-4 | function Entry Requires Method | Implemented | An entry with `"validation": "function"` that has no matching `validate_<field>()` method on the class raises `ImproperlyConfigured` at class definition time. | |
| req-grid-entity-validation-5 | Undeclared Validator Raises | Implemented | A `validate_<field>()` method (without `@dangerously_ignore_validator`) whose field is not in `FIELD_SCHEMAS` raises `ImproperlyConfigured` at class definition time. | |
| req-grid-entity-validation-6 | FIELD_SCHEMAS Keys Are Real Fields | Implemented | A `FIELD_SCHEMAS` key that does not match a field declared on the derived model raises `ImproperlyConfigured` at class definition time. | |
| req-grid-entity-validation-7 | JSON Schema Validation | Implemented | `full_validate()` runs `jsonschema.validate(field_value, schema)` for each `"jsonschema"` entry. Violations are collected keyed by field name. | |
| req-grid-entity-validation-8 | Function Validation | Implemented | `full_validate()` calls `validate_<field>(self)` for each `"function"` entry. Raised `ValidationError` messages are merged into the error dict. | |
| req-grid-entity-validation-9 | Whole-Record Hook | Implemented | `full_validate()` calls `self.validate()` after per-field checks. Base implementation is a no-op. Raised errors are merged into the collection. | |
| req-grid-entity-validation-10 | Error Collection | Implemented | `full_validate()` collects all errors from all sources before raising. The final `ValidationError` is in Django dict form `{field: [messages]}`. | |
| req-grid-entity-validation-11 | full_validate Standalone | Implemented | `full_validate()` can be called without saving. Returns normally if all checks pass; raises `ValidationError` if any fail. | |
| req-grid-entity-validation-12 | save() Integration | Implemented | `BaseModel.save()` calls `full_validate()` before any DB write or entity auto-creation. | |
| req-grid-entity-validation-13 | skip_validation Escape Hatch | Implemented | `save(skip_validation=True)` bypasses `full_validate()` entirely. | |
| req-grid-entity-validation-14 | @dangerously_ignore_validator Decorator | Implemented | A `validate_<field>()` method decorated with `@dangerously_ignore_validator` is excluded from startup invariant checks and never called by `full_validate()`. | |
| req-grid-entity-validation-15 | Applies to Edge | Implemented | `Edge` inherits the full validation mechanism. The existing edge property schema registry is unaffected. | |

#### Future

Consider supporting a combined entry type (e.g. `"validation": "jsonschema+function"`) for fields that need both structural schema validation and custom business-rule logic in a single field declaration.

Consider exposing `full_validate()` as a Ninja API endpoint so frontends can perform round-trip validation on partial data (e.g. as a user fills out a form field-by-field) without triggering a save.

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

---

### Edge-Directed Cascade Deletion
----
RID: `req-grid-entity-cascade`
Status: `Backlog`

When an entity is deleted, the graph may have opinions about what else should go. Today, deletion cascades are handled entirely by Django's `on_delete=CASCADE` on the FK between a typed model and its `Entity` spine row — which is correct for keeping the spine consistent, but knows nothing about the graph. Edge relationships can encode richer semantics: deleting a `Concept` that `DEPENDS_ON` another should perhaps propagate that deletion forward; deleting a `Precept` that `APPLIES_TO` many concepts probably should not.

This requirement is the foundation for making deletion a graph-aware, policy-driven operation rather than a raw relational cascade.

#### Future

Questions to resolve when this is picked up:

- **Where do cascade policies live?** Candidates: `OUTBOUND_EDGES` / `INBOUND_EDGES` entries on the model, a separate `CASCADE_POLICY` class variable, or a service-layer policy registry.
- **Directionality**: should deletion cascade along outbound edges (things this entity points to), inbound edges (things pointing at this entity), or both, depending on policy?
- **Cycles**: the graph may contain cycles; cascade logic must guard against infinite loops.
- **Transactionality**: multi-hop cascades should be atomic; partial deletes are worse than no delete.
- **Interaction with FLIP**: every deletion — including cascade-triggered ones — must be recorded as a provenance event. Cascade chains may need a shared batch ID so the audit trail shows the full causal chain.
- **Soft delete**: edge-directed cascade is a natural hook point for introducing soft-delete semantics (mark deleted rather than destroy rows), which would make the whole thing reversible.

---

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
