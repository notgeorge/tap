"""tap_cares collector registry.

req-tap-cares-collector-registry (spec-tap-cares-collector.md).

Mirrors the search runner registry pattern in `tap_grid/registry.py`:
    - `collector_registry` is a ScopedRegistry[type[CollectorBase]] using the
      validator hooks added by req-grid-registry-scope-validators
    - `register_collector(key, cls, scope=None)` and `get_collector(key)` are
      the public surface; plugin code should call the helpers
    - `_validate_collector_token` is the single source of truth for the
      scope:key format. The Collector model's validate() hook calls it too so
      model-side and registry-side enforcement cannot drift
      (req-tap-cares-collector-registry-10).
"""

from __future__ import annotations

import re

from django.core.exceptions import ImproperlyConfigured

from tap_cares.collectors.base import CollectorBase
from tap_cares.exceptions import (
    CollectorNotFoundError,
    InvalidCollectorRegistryKeyError,
)
from tap_grid.registry import ScopedRegistry

_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")


def _validate_collector_token(value: str) -> None:
    """Reject malformed scope or key tokens.

    Used as both validate_scope and validate_key on collector_registry, and
    invoked by Collector.validate() on each half of the persisted
    `collector_registry` field so model and registry stay aligned.
    """
    if not isinstance(value, str) or not _TOKEN_PATTERN.fullmatch(value):
        raise InvalidCollectorRegistryKeyError(
            f"Invalid collector registry token {value!r}. " f"Must match {_TOKEN_PATTERN.pattern}."
        )


collector_registry: ScopedRegistry[type[CollectorBase]] = ScopedRegistry(
    "collector",
    validate_key=_validate_collector_token,
    validate_scope=_validate_collector_token,
    title="Collector Registry",
    description="Scoped registry of registered tap_cares collector classes.",
)


def register_collector(
    key: str,
    cls: type[CollectorBase],
    scope: str | None = None,
) -> None:
    """Register a collector class under a scoped key.

    Scope is auto-inferred from cls.__module__ when omitted. Rejects anything
    that is not a CollectorBase subclass at registration time
    (req-tap-cares-collector-module-class-6).
    """
    if not (isinstance(cls, type) and issubclass(cls, CollectorBase)):
        raise ImproperlyConfigured(f"register_collector: {cls!r} must be a subclass of CollectorBase.")
    collector_registry.register(key, cls, scope=scope)


def get_collector(collector_key: str) -> type[CollectorBase]:
    """Return the collector class for a fully-qualified 'scope:key'.

    Raises:
        InvalidCollectorRegistryKeyError: if the key format is invalid.
        CollectorNotFoundError: if no class is registered for the key.
    """
    try:
        return collector_registry.get(collector_key)
    except KeyError:
        raise CollectorNotFoundError(
            f"No collector registered for key '{collector_key}'. " f"Registered: {collector_registry.keys()}"
        ) from None
