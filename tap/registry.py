"""Generic runtime registry classes — a platform-wide TAP capability.

This is a cross-cutting platform utility (a peer of ``tap/jsonfiles.py`` and
``tap/logging.py``), not a graph concept: it has no dependency on ``tap_grid``
models. Any app may build a registry from it without importing the graph app.
The grid-specific registries (entity-model, search-runner) and helpers live in
``tap_grid/registry.py`` and build on these base classes.

Provides two registry shapes:
  Registry[T]        — globally-unique key space; fail-fast on duplicate.
  ScopedRegistry[T]  — scope-namespaced key space; scope auto-inferred from
                       value.__module__ so two plugins may register the same
                       short key without collision.

A module-level meta_registry enumerates all named Registry instances so the
full system state is visible from one place for debugging and admin tooling.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from django.core.exceptions import ImproperlyConfigured


class Registry[T]:
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
        title: str = "",
        description: str = "",
        creator: str = "",
        _skip_meta: bool = False,
    ) -> None:
        self._name = name
        self._merge_fn = merge_fn
        self._data: dict[str, T] = {}
        self.title = title or name.replace("_", " ").title()
        self.description = description
        self.creator = creator or inspect.stack()[1].frame.f_globals.get("__name__", "")
        if not _skip_meta:
            meta_registry.register(name, self)

    def register(self, key: str, value: T) -> None:
        """Register key → value.

        Raises ImproperlyConfigured if key already exists and no merge_fn is set.
        """
        if key in self._data:
            if self._merge_fn is not None:
                self._data[key] = self._merge_fn(self._data[key], value)
                return
            raise ImproperlyConfigured(
                f"Registry '{self._name}': key '{key}' is already registered. " "Remove the duplicate registration."
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


class ScopedRegistry[T]:
    """Named, typed, scope-namespaced runtime registry.

    Scope is auto-inferred from value.__module__ at registration time.
    The same short key may be registered by different scopes without collision.
    The fully-qualified key format is 'scope:key'.

    Optional ``validate_key`` / ``validate_scope`` callbacks enforce per-subsystem
    format rules. When provided, they run on both ``register()`` and ``get()``
    public entrypoints (including the parsed halves of a ``"scope:key"`` lookup)
    so malformed inputs fail loud at the boundary rather than at first dictionary
    use. Callbacks raise (typically ``ImproperlyConfigured`` for bad
    registrations, a domain-specific exception for bad lookups); the registry
    does not catch or wrap. Defaults of ``None`` preserve pre-validator behavior.
    """

    def __init__(
        self,
        name: str,
        merge_fn: Callable[[T, T], T] | None = None,
        *,
        validate_key: Callable[[str], None] | None = None,
        validate_scope: Callable[[str], None] | None = None,
        title: str = "",
        description: str = "",
        creator: str = "",
    ) -> None:
        self._name = name
        self._merge_fn = merge_fn
        self._validate_key = validate_key
        self._validate_scope = validate_scope
        self._data: dict[str, dict[str, T]] = {}  # scope → key → value
        self.title = title or name.replace("_", " ").title()
        self.description = description
        self.creator = creator or inspect.stack()[1].frame.f_globals.get("__name__", "")
        meta_registry.register(name, self)

    def _infer_scope(self, value: T, scope: str | None) -> str:
        if scope is not None:
            return scope
        module: str | None = getattr(value, "__module__", None)
        if not module:
            raise ValueError(
                f"ScopedRegistry '{self._name}': cannot infer scope for {value!r}. " "Pass scope= explicitly."
            )
        return module

    def register(self, key: str, value: T, scope: str | None = None) -> None:
        """Register (scope, key) → value. Scope inferred from value.__module__ if not provided.

        If ``validate_scope`` / ``validate_key`` were supplied at construction,
        they run before any internal state is touched so a rejected registration
        leaves the registry unchanged.
        """
        effective_scope = self._infer_scope(value, scope)
        if self._validate_scope is not None:
            self._validate_scope(effective_scope)
        if self._validate_key is not None:
            self._validate_key(key)
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

        If validators were supplied at construction, they run on the resolved
        scope and key before dictionary lookup, including the parsed halves of
        a ``"scope:key"`` argument.
        """
        if ":" in key and scope is None:
            scope, key = key.rsplit(":", 1)

        if scope is not None and self._validate_scope is not None:
            self._validate_scope(scope)
        if self._validate_key is not None:
            self._validate_key(key)

        if scope is not None:
            scope_data = self._data.get(scope, {})
            if key not in scope_data:
                raise KeyError(f"ScopedRegistry '{self._name}': key '{scope}:{key}' not found.")
            return scope_data[key]

        matches = {s: d[key] for s, d in self._data.items() if key in d}
        if not matches:
            raise KeyError(f"ScopedRegistry '{self._name}': no value for key '{key}'. " f"All keys: {self.keys()}")
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

meta_registry: Registry[Any] = Registry(
    "__meta__",
    title="Meta Registry",
    description="Bootstrap registry that tracks all other registries.",
    _skip_meta=True,
)


__all__ = ["Registry", "ScopedRegistry", "meta_registry"]
