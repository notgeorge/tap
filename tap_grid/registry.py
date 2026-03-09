"""Generic runtime registry classes for TAP service layers.

Provides two registry shapes:
  Registry[T]        — globally-unique key space; fail-fast on duplicate.
  ScopedRegistry[T]  — scope-namespaced key space; scope auto-inferred from
                       value.__module__ so two plugins may register the same
                       short key without collision.

A module-level meta_registry enumerates all named Registry instances so the
full system state is visible from one place for debugging and admin tooling.
"""

from __future__ import annotations

from typing import Any, Callable, Generic, TYPE_CHECKING, TypeVar
from uuid import UUID

from django.core.exceptions import ImproperlyConfigured

if TYPE_CHECKING:
    from tap_grid.models import BaseModel, Entity

T = TypeVar("T")


class Registry(Generic[T]):
    """Named, typed, fail-fast runtime key → value registry.

    Keys must be unique within this instance. Duplicate registration raises
    ImproperlyConfigured unless merge_fn is provided, in which case the
    registry calls merge_fn(existing, new) and stores the result.
    """

    def __init__(
        self,
        name: str,
        merge_fn: Callable[[T, T], T] | None = None,
        *,
        _skip_meta: bool = False,
    ) -> None:
        self._name = name
        self._merge_fn = merge_fn
        self._data: dict[str, T] = {}
        if not _skip_meta:
            meta_registry.register(name, self)  # type: ignore[arg-type]

    def register(self, key: str, value: T) -> None:
        """Register key → value.

        Raises ImproperlyConfigured if key already exists and no merge_fn is set.
        """
        if key in self._data:
            if self._merge_fn is not None:
                self._data[key] = self._merge_fn(self._data[key], value)
                return
            raise ImproperlyConfigured(
                f"Registry '{self._name}': key '{key}' is already registered. "
                "Remove the duplicate registration."
            )
        self._data[key] = value

    def get(self, key: str) -> T:
        """Return the value for key. Raises KeyError with registered keys listed if missing."""
        try:
            return self._data[key]
        except KeyError:
            raise KeyError(
                f"Registry '{self._name}': no value registered for key '{key}'. "
                f"Registered keys: {sorted(self._data.keys())}"
            ) from None

    def get_optional(self, key: str) -> T | None:
        """Return the value for key, or None if not registered."""
        return self._data.get(key)

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def keys(self) -> list[str]:
        """Return a sorted list of all registered keys."""
        return sorted(self._data.keys())

    def all(self) -> dict[str, T]:
        """Return a shallow copy of the registry contents."""
        return dict(self._data)

    def _reset_for_testing(self, data: dict[str, T] | None = None) -> None:
        """Replace internal state with data (or empty). FOR TESTING ONLY."""
        self._data.clear()
        if data is not None:
            self._data.update(data)

    def __repr__(self) -> str:
        return f"<Registry name={self._name!r} keys={self.keys()}>"


class ScopedRegistry(Generic[T]):
    """Named, typed, scope-namespaced runtime registry.

    Scope is auto-inferred from value.__module__ at registration time.
    The same short key may be registered by different scopes without collision.
    The fully-qualified key format is 'scope:key'.
    """

    def __init__(
        self,
        name: str,
        merge_fn: Callable[[T, T], T] | None = None,
    ) -> None:
        self._name = name
        self._merge_fn = merge_fn
        self._data: dict[str, dict[str, T]] = {}  # scope → key → value
        meta_registry.register(name, self)  # type: ignore[arg-type]

    def _infer_scope(self, value: T, scope: str | None) -> str:
        if scope is not None:
            return scope
        module = getattr(value, "__module__", None)
        if not module:
            raise ValueError(
                f"ScopedRegistry '{self._name}': cannot infer scope for {value!r}. "
                "Pass scope= explicitly."
            )
        return module

    def register(self, key: str, value: T, scope: str | None = None) -> None:
        """Register (scope, key) → value. Scope inferred from value.__module__ if not provided."""
        effective_scope = self._infer_scope(value, scope)
        scope_data = self._data.setdefault(effective_scope, {})
        if key in scope_data:
            if self._merge_fn is not None:
                scope_data[key] = self._merge_fn(scope_data[key], value)
                return
            raise ImproperlyConfigured(
                f"ScopedRegistry '{self._name}': key '{effective_scope}:{key}' is already registered."
            )
        scope_data[key] = value

    def get(self, key: str, scope: str | None = None) -> T:
        """Look up a value.

        - Fully-qualified key ('scope:key') or scope kwarg: direct lookup.
        - Short key only: returns the single match if unambiguous; raises KeyError
          if zero matches or if multiple scopes have the same short key.
        """
        if ":" in key and scope is None:
            scope_part, short_key = key.rsplit(":", 1)
            return self.get(short_key, scope=scope_part)

        if scope is not None:
            scope_data = self._data.get(scope, {})
            if key not in scope_data:
                raise KeyError(
                    f"ScopedRegistry '{self._name}': key '{scope}:{key}' not found."
                )
            return scope_data[key]

        matches = {s: d[key] for s, d in self._data.items() if key in d}
        if not matches:
            raise KeyError(
                f"ScopedRegistry '{self._name}': no value for key '{key}'. "
                f"All keys: {self.keys()}"
            )
        if len(matches) > 1:
            candidates = sorted(f"{s}:{key}" for s in matches)
            raise KeyError(
                f"ScopedRegistry '{self._name}': key '{key}' is ambiguous across scopes: "
                f"{candidates}. Use a fully-qualified key or pass scope=."
            )
        return next(iter(matches.values()))

    def get_all(self, key: str) -> dict[str, T]:
        """Return all matches for a short key across all scopes."""
        return {s: d[key] for s, d in self._data.items() if key in d}

    def get_optional(self, key: str, scope: str | None = None) -> T | None:
        """Return the value, or None if not found."""
        try:
            return self.get(key, scope=scope)
        except KeyError:
            return None

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        if ":" in key:
            scope_part, short_key = key.rsplit(":", 1)
            return short_key in self._data.get(scope_part, {})
        return any(key in d for d in self._data.values())

    def keys(self) -> list[str]:
        """Return sorted fully-qualified keys (scope:key)."""
        result: list[str] = []
        for scope, d in self._data.items():
            result.extend(f"{scope}:{k}" for k in d)
        return sorted(result)

    def scopes(self) -> list[str]:
        """Return sorted list of scopes with at least one registration."""
        return sorted(s for s, d in self._data.items() if d)

    def all(self) -> dict[str, dict[str, T]]:
        """Return a shallow copy of the full scope → key → value mapping."""
        return {s: dict(d) for s, d in self._data.items()}

    def _reset_for_testing(self, data: dict[str, dict[str, T]] | None = None) -> None:
        """Replace internal state. FOR TESTING ONLY."""
        self._data.clear()
        if data is not None:
            for scope, d in data.items():
                self._data[scope] = dict(d)

    def __repr__(self) -> str:
        return f"<ScopedRegistry name={self._name!r} scopes={self.scopes()}>"


# ---------------------------------------------------------------------------
# Meta-registry — enumerates all named Registry/ScopedRegistry instances.
# Instantiated before all other registries; does not self-register.
# ---------------------------------------------------------------------------

meta_registry: Registry[Any] = Registry("__meta__", _skip_meta=True)


# ---------------------------------------------------------------------------
# Entity model registry — maps entity_type slugs to concrete ORM model classes.
# Populated at class-definition time via BaseModel.__init_subclass__.
# ---------------------------------------------------------------------------

_entity_model_registry: Registry[type] = Registry("entity_model")

# Backward compatibility: some callers import _ENTITY_MODEL_REGISTRY directly.
_ENTITY_MODEL_REGISTRY = _entity_model_registry


# ---------------------------------------------------------------------------
# Public API (backward compatible)
# ---------------------------------------------------------------------------


def register_entity_type(entity_type: str, model_cls: type) -> None:
    """Register a model class for the given entity_type slug.

    Called from BaseModel.__init_subclass__ for every concrete subclass that
    declares ENTITY_TYPE.

    Re-registering the same class for the same type is idempotent (no-op).
    Registering a different class for an already-registered type raises
    ImproperlyConfigured.
    """
    if entity_type in _entity_model_registry:
        existing = _entity_model_registry.get(entity_type)
        if existing is model_cls:
            return
        raise ImproperlyConfigured(
            f"Entity type '{entity_type}' is already registered to {existing.__name__}. "
            f"Cannot also register {model_cls.__name__}."
        )
    _entity_model_registry.register(entity_type, model_cls)


def get_model_class(entity_type: str) -> type:
    """Return the model class registered for the given entity_type slug.

    Raises KeyError with a descriptive message if the type is unknown.
    """
    try:
        return _entity_model_registry.get(entity_type)
    except KeyError:
        raise KeyError(
            f"No model registered for entity type '{entity_type}'. "
            f"Registered types: {_entity_model_registry.keys()}"
        ) from None


def resolve_entity(entity_id: UUID) -> "BaseModel":
    """Resolve an entity_id to its concrete typed model instance.

    Performs two DB queries: one to fetch the Entity (to get entity_type),
    one to fetch the concrete domain object. If you already have the Entity
    instance, call entity.resolve() directly to save the first query.
    """
    from tap_grid.models import Entity

    entity: Entity = Entity.objects.get(pk=entity_id)
    return entity.resolve()


# ---------------------------------------------------------------------------
# Search runner registry — maps scoped keys to module search runner callables.
# Populated at AppConfig.ready() time by plugins that provide module runners.
# ---------------------------------------------------------------------------

search_runner_registry: ScopedRegistry[Callable[..., Any]] = ScopedRegistry("search_runner")


def register_search_runner(
    key: str,
    runner: Callable[..., Any],
    scope: str | None = None,
) -> None:
    """Register a search runner callable under a scoped key.

    Scope is auto-inferred from runner.__module__ if not provided.
    Duplicate registration of the same (scope, key) pair raises ImproperlyConfigured.
    """
    search_runner_registry.register(key, runner, scope=scope)


def get_search_runner(runner_key: str) -> Callable[..., Any]:
    """Return the runner callable for a fully-qualified 'scope:key' runner_key.

    Raises SearchRunnerNotFoundError with a descriptive message if not found.
    """
    from tap_grid.exceptions import SearchRunnerNotFoundError

    try:
        return search_runner_registry.get(runner_key)
    except KeyError:
        raise SearchRunnerNotFoundError(
            f"No search runner registered for key '{runner_key}'. "
            f"Registered runners: {search_runner_registry.keys()}"
        ) from None
