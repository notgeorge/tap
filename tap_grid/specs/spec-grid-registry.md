# Grid Registry Specification

## Philosophy

Several subsystems in TAP need a runtime registry: the entity model registry maps entity type slugs to their concrete ORM classes; the panel registry (spec-web-panel.md) will map panel type slugs to their handler classes; future plugin systems will need the same pattern again.

Without a shared abstraction, each subsystem reinvents the same module-level dict, the same duplicate-key guard, the same descriptive miss error, and the same inspection helpers. The result is fragmented, inconsistently behaved registries scattered across the codebase.

Two distinct registry shapes are needed:

- **`Registry[T]`** — globally-unique key space. Every key across the whole system must be unique. Used for entity type slugs, which are a cross-system vocabulary and must not collide.
- **`ScopedRegistry[T]`** — namespaced key space. Keys are unique within a scope but may repeat across scopes. Scope is auto-inferred from the registering value's `__module__`. Used for panel types, plugin registrations, and any other namespace where two independent authors might legitimately choose the same short name.

Both shapes share the same fail-fast duplicate guard, descriptive miss errors, and inspection interface. `tap_grid` also maintains a **meta-registry** — a `Registry` of all `Registry` instances — so the full system state can be enumerated from one place for debugging, admin tooling, and health checks.

## Goals

|    |               |                                                                                                            |
| :---: | ---        | ---                                                                                                        |
| 1. | Reusable      | One implementation used by every subsystem that needs a runtime key → value registry                      |
| 2. | Typed         | Generic type parameter so callers get full mypy and IDE support without casting                            |
| 3. | Fail-fast     | Duplicate key registration raises `ImproperlyConfigured` at startup, not silently at runtime              |
| 4. | Descriptive   | Miss and ambiguous-key lookups raise `KeyError` that lists registered keys and scopes                     |
| 5. | Inspectable   | Registry exposes `keys()`, `all()`, and `__contains__` for introspection and admin tooling                |
| 6. | Scoped        | `ScopedRegistry` auto-infers namespace from the registering value's module; prevents cross-plugin key collisions |
| 7. | Meta-observable | `meta_registry` enumerates all live `Registry` instances so system state is visible from one location   |


## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-grid-registry | [Registry Class](#registry-class) | Implemented | Generic runtime key → value registry with named instance, duplicate guard, and descriptive miss |
| req-grid-registry-scope | [Scoped Registry](#scoped-registry) | Implemented | `ScopedRegistry[T]` auto-infers key namespace from value's module; supports unambiguous short-key lookup |
| req-grid-registry-meta | [Meta-Registry](#meta-registry) | Implemented | Module-level `meta_registry` enumerates all named `Registry` instances |
| req-grid-registry-entity | [Entity Model Registry Migration](#entity-model-registry-migration) | Implemented | Refactor `tap_grid/registry.py` to back the existing entity model registry with a `Registry` instance |


---


### Registry Class
----
RID: `req-grid-registry`
Status: `Implemented`

A `Registry[T]` class that provides a named, typed, fail-fast runtime key → value mapping with a globally-unique key space.

#### Interface

```python
from tap_grid.registry import Registry

# Instantiate one registry per use case
panel_registry: Registry[type[PanelBase]] = Registry("panel")

# Register a key → value pair
panel_registry.register("character-list", CharacterListPanel)

# Look up a key
cls = panel_registry.get("character-list")      # returns CharacterListPanel
cls = panel_registry.get("missing")             # raises KeyError with registered keys listed

# Inspect
panel_registry.keys()                            # ["character-list"]
panel_registry.all()                             # {"character-list": CharacterListPanel}
"character-list" in panel_registry               # True
```

#### Duplicate registration

By default, any attempt to register a key that is already registered raises `django.core.exceptions.ImproperlyConfigured`. Plugin load order must be deterministic; the default treats every collision as a programming error.

For registries where multiple contributors legitimately add to the same key (e.g., edge type constraints where two plugins both extend the same edge type), a `merge_fn` may be provided at construction time:

```python
# Default — raises on any duplicate
entity_registry: Registry[type[BaseModel]] = Registry("entity_model")

# Merge-enabled — calls merge_fn(existing, new) on duplicate; stores the result
edge_constraint_registry: Registry[EdgeTypeConstraints] = Registry(
    "edge_constraints",
    merge_fn=merge_edge_type_constraints,
)
```

`merge_fn` is a callable `(existing: T, new: T) -> T`. When a duplicate key is registered and `merge_fn` is set, the registry calls `merge_fn(existing_value, new_value)` and replaces the stored value with the result. The error is suppressed only when `merge_fn` is explicitly provided — it is never inferred.

#### Registration timing

Registries are populated at startup, before any request is served. Two standard patterns:

| Pattern | When | Used By |
| --- | --- | --- |
| `BaseModel.__init_subclass__` | Class-definition time, before `AppConfig.ready()` | Entity model registry |
| `AppConfig.ready()` | After all models are loaded | Panel registry, plugin registries |

#### Implementation

`Registry[T]` is a concrete generic class defined in `tap_grid/registry.py`. It holds an instance `dict[str, T]` and wraps it with the duplicate guard and descriptive miss logic. No Django models are touched; the class has no ORM dependency.

On `__init__`, the registry registers itself with `meta_registry` (see `req-grid-registry-meta`). The meta-registry raises `ImproperlyConfigured` if two `Registry` instances are created with the same name.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-registry-1 | Generic Type Parameter | Implemented | `Registry[T]` is a generic class; instantiation with a type argument (`Registry[type[Foo]]`) provides full mypy and IDE support. | |
| req-grid-registry-2 | Named Instance | Implemented | Each `Registry` is constructed with a `name: str` used in error messages. | |
| req-grid-registry-3 | register — Raises on Duplicate (no merge_fn) | Implemented | When `merge_fn` is not set, calling `register(key, value)` for an already-registered key raises `ImproperlyConfigured`. The error message includes the registry name and the duplicate key. | |
| req-grid-registry-3b | register — Merges on Duplicate (merge_fn set) | Implemented | When `merge_fn` is set, calling `register(key, value)` for an already-registered key calls `merge_fn(existing, new)` and stores the return value. No error is raised. | |
| req-grid-registry-4 | get — Returns Value | Implemented | `get(key)` returns the registered value for an existing key. | |
| req-grid-registry-5 | get — Descriptive Miss | Implemented | `get(key)` raises `KeyError` for an unknown key; the message includes the registry name, the missing key, and a sorted list of all registered keys. | |
| req-grid-registry-6 | keys() | Implemented | `keys()` returns a sorted list of all registered key strings. | |
| req-grid-registry-7 | all() | Implemented | `all()` returns a shallow copy of the internal `dict[str, T]`. | |
| req-grid-registry-8 | __contains__ | Implemented | `key in registry` returns `True` if the key is registered, `False` otherwise. | |
| req-grid-registry-9 | No ORM Dependency | Implemented | `Registry` imports no Django models. It may import `django.core.exceptions.ImproperlyConfigured`. | |
| req-grid-registry-10 | Auto-registers with Meta-registry | Implemented | `Registry.__init__` registers itself with `meta_registry` by name. Raises `ImproperlyConfigured` if the name is already taken. | |

#### Future

Consider adding a `register_decorator` convenience method so callers can use `@registry.register("key")` syntax instead of explicit `registry.register("key", cls)` calls.

Consider adding a Django system check that warns when a registry is empty at startup (useful for subsystems that expect at least one registration).


---


### Scoped Registry
----
RID: `req-grid-registry-scope`
Status: `Implemented`

`ScopedRegistry[T]` extends `Registry[T]` with a two-level key space: `scope → key → value`. It prevents cross-plugin key collisions without requiring plugin authors to manually namespace their registration keys.

#### Motivation

Any two plugins could independently choose `"users"` as a panel type key. In a flat `Registry`, the second registration raises `ImproperlyConfigured`. In a `ScopedRegistry`, both coexist because the effective key is the `(scope, key)` pair.

#### Scope inference

Scope is the `__module__` attribute of the value being registered. A class defined in `tap_plugins.lotr.panels` has `__module__ = "tap_plugins.lotr.panels"` — that string is the scope. No truncation, no Django app-registry lookup, no stack inspection.

Callers may pass `scope=` explicitly to override inference. This is required when registering values that do not have a meaningful `__module__` (e.g., plain instances or lambdas).

#### Fully-qualified key format

The canonical key is `"{scope}:{short_key}"`, e.g. `"tap_plugins.lotr.panels:users"`. This is the unique identifier used for duplicate detection, error messages, and explicit lookups.

#### Interface

```python
from tap_grid.registry import ScopedRegistry

panel_registry: ScopedRegistry[type[PanelBase]] = ScopedRegistry("panel")

# Registration — scope auto-inferred from CharacterListPanel.__module__
panel_registry.register("users", LotrUsersPanel)        # scope = "tap_plugins.lotr.panels"
panel_registry.register("users", AcmeUsersPanel)        # scope = "tap_plugins.acme.panels" — no collision

# Unambiguous short-key lookup (exactly one scope has this key)
panel_registry.get("character-list")                    # works
panel_registry.get("users")                             # raises KeyError — ambiguous across 2 scopes

# Explicit scoped lookup
panel_registry.get("tap_plugins.lotr.panels:users")     # returns LotrUsersPanel
panel_registry.get("users", scope="tap_plugins.lotr.panels")  # same result

# All matches for a short key across all scopes
panel_registry.get_all("users")
# {"tap_plugins.lotr.panels": LotrUsersPanel, "tap_plugins.acme.panels": AcmeUsersPanel}

# Inspect
panel_registry.keys()      # sorted fully-qualified keys: ["tap_plugins.acme.panels:users", ...]
panel_registry.scopes()    # sorted list of scope strings
panel_registry.all()       # {"tap_plugins.lotr.panels": {"users": LotrUsersPanel}, ...}
```

#### Duplicate detection

Duplicate is defined at the `(scope, key)` level. `ScopedRegistry` inherits the `merge_fn` parameter from `Registry`: if set, duplicates at the same `(scope, key)` are merged rather than rejected. The default (no `merge_fn`) raises `ImproperlyConfigured`.

#### Implementation

`ScopedRegistry[T]` holds `dict[str, dict[str, T]]` (scope → key → value). `register()` infers scope from `value.__module__`, constructs the fully-qualified key, and applies the same duplicate guard as `Registry`. The `meta_registry` auto-registration behavior is inherited from `Registry`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-registry-scope-1 | Scope Inferred from __module__ | Implemented | `register(key, value)` sets scope = `value.__module__`. No stack inspection is performed. | |
| req-grid-registry-scope-2 | Explicit Scope Override | Implemented | `register(key, value, scope="explicit.scope")` uses the provided scope string instead of inference. | |
| req-grid-registry-scope-3 | Duplicate at (scope, key) | Implemented | Re-registering the same `(scope, key)` pair raises `ImproperlyConfigured` with the fully-qualified key in the message. | |
| req-grid-registry-scope-4 | Cross-scope Coexistence | Implemented | Two values with the same short key but different scopes coexist without error. | |
| req-grid-registry-scope-5 | get — Fully-qualified Key | Implemented | `get("scope:key")` returns the value for that exact scoped entry, or raises `KeyError` if not found. | |
| req-grid-registry-scope-6 | get — Scope Kwarg | Implemented | `get(key, scope="scope.string")` is equivalent to `get("scope.string:key")`. | |
| req-grid-registry-scope-7 | get — Unambiguous Short Key | Implemented | `get(key)` (no scope) returns the single value when exactly one scope has that key. | |
| req-grid-registry-scope-8 | get — Ambiguous Short Key Raises | Implemented | `get(key)` raises `KeyError` when multiple scopes have that key; the message lists all matching fully-qualified keys. | |
| req-grid-registry-scope-9 | get_all | Implemented | `get_all(key)` returns a `dict[scope, value]` of all matches across all scopes for the given short key. Returns an empty dict if none. | |
| req-grid-registry-scope-10 | scopes() | Implemented | `scopes()` returns a sorted list of all scope strings that have at least one registered key. | |


---


### Meta-Registry
----
RID: `req-grid-registry-meta`
Status: `Implemented`

`tap_grid/registry.py` exports a module-level `meta_registry` — a plain `Registry[Registry]` instance whose keys are registry names and values are the `Registry` instances themselves.

Every `Registry` (and `ScopedRegistry`) auto-registers itself into `meta_registry` on construction. This means any code can enumerate all live registries and inspect their contents without knowing where each registry is defined.

#### Interface

```python
from tap_grid.registry import meta_registry

meta_registry.keys()
# ["entity_model", "panel", ...]

meta_registry.get("panel")
# <ScopedRegistry[type[PanelBase]] name="panel" entries=3>

meta_registry.all()
# {"entity_model": <Registry ...>, "panel": <ScopedRegistry ...>}

# Inspect the contents of a specific registry
meta_registry.get("panel").all()
```

#### Bootstrap note

`meta_registry` itself is not registered in itself. It is instantiated directly as a module-level singleton before any other registry is created. It does not call `super().__init__()` with a name that would trigger self-registration.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-registry-meta-1 | Module-level Singleton | Implemented | `meta_registry` is a module-level instance in `tap_grid/registry.py`, instantiated before any other registry. | |
| req-grid-registry-meta-2 | Auto-registration on Construction | Implemented | `Registry.__init__` calls `meta_registry.register(self.name, self)` so every new registry appears in the meta-registry automatically. | |
| req-grid-registry-meta-3 | Duplicate Name Raises | Implemented | Creating two `Registry` instances with the same name raises `ImproperlyConfigured` (enforced by the meta-registry's own duplicate guard). | |
| req-grid-registry-meta-4 | meta_registry Not Self-registered | Implemented | `meta_registry` does not appear as an entry in itself. | |
| req-grid-registry-meta-5 | Enumeration | Implemented | `meta_registry.all()` returns a dict of all registered registries keyed by name. The result includes both `Registry` and `ScopedRegistry` instances. | |


---


### Entity Model Registry Migration
----
RID: `req-grid-registry-entity`
Status: `Implemented`

The existing entity model registry in `tap_grid/registry.py` was written before the generic `Registry` class existed. It implements the same duplicate-guard and descriptive-miss pattern but as a standalone module-level dict with free functions. This requirement covers refactoring it to use a `Registry` instance.

Entity type slugs are a globally unique cross-system vocabulary — no two node types may share a slug regardless of which plugin defines them. `Registry[T]` (unscoped) is the correct shape; `ScopedRegistry` is not needed here.

The public API (`register_entity_type`, `get_model_class`, `resolve_entity`) must remain unchanged so no call sites break. Internally, `_ENTITY_MODEL_REGISTRY` becomes a `Registry[type[BaseModel]]` instance.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-registry-entity-1 | Backed by Registry Instance | Implemented | `_ENTITY_MODEL_REGISTRY` in `tap_grid/registry.py` is replaced by a `Registry[type[BaseModel]]` instance. | |
| req-grid-registry-entity-2 | Public API Unchanged | Implemented | `register_entity_type()`, `get_model_class()`, and `resolve_entity()` signatures and behavior are identical to before. | |
| req-grid-registry-entity-3 | No Broken Tests | Implemented | All existing `tap_grid` tests pass without modification after the refactor. | |
| req-grid-registry-entity-4 | Visible in Meta-registry | Implemented | After migration, `meta_registry.get("entity_model")` returns the entity model registry instance. | |


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
