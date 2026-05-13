"""tap_cares collector registry.

req-tap-cares-collector-registry, req-tap-cares-collector-registration
(spec-tap-cares-collector.md).

Mirrors the search runner registry pattern in `tap_grid/registry.py`:
    - `collector_registry` is a ScopedRegistry[type[CollectorBase]] using the
      validator hooks added by req-grid-registry-scope-validators
    - `register_collector(key, cls, *, name, description, scope=None)` is the
      dual-existence registration entry point: it registers the runner class
      AND upserts the on-grid Collector node with deterministic UUIDv5
      identity. See `tap_grid/specs/spec-grid-dual-existence.md`.
    - `_validate_collector_token` is the single source of truth for the
      scope:key format. The Collector model's validate() hook calls it too so
      model-side and registry-side enforcement cannot drift
      (req-tap-cares-collector-registry-10).
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Final

from django.core.exceptions import ImproperlyConfigured
from django.db.utils import OperationalError, ProgrammingError

from tap_cares.collectors.base import CollectorBase
from tap_cares.exceptions import (
    CollectorNotFoundError,
    InvalidCollectorRegistryKeyError,
)
from tap_grid.registry import ScopedRegistry

logger = logging.getLogger(__name__)

_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")

# Deterministic UUIDv5 namespace for Collector grid-side identity.
# Derived once from a stable seed string; the value is frozen for the lifetime
# of the v0 collector subsystem. Changing this value would re-identify every
# Collector node on every grid — not permitted (req-tap-cares-collector-registration-8).
NAMESPACE_COLLECTOR: Final[uuid.UUID] = uuid.uuid5(uuid.NAMESPACE_DNS, "tap_cares.collector")


def _validate_collector_token(value: str) -> None:
    """Reject malformed scope or key tokens.

    Used as both validate_scope and validate_key on collector_registry, and
    invoked by Collector.validate() on each half of the persisted
    `collector_registry` field so model and registry stay aligned.
    """
    if not isinstance(value, str) or not _TOKEN_PATTERN.fullmatch(value):
        raise InvalidCollectorRegistryKeyError(
            f"Invalid collector registry token {value!r}. Must match {_TOKEN_PATTERN.pattern}."
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
    *,
    name: str,
    description: str,
    scope: str | None = None,
) -> None:
    """Register a collector capability — both halves of the dual-existence pattern.

    Performs two coupled actions:
      1. Registers `cls` in `collector_registry` under `scope:key`. If `scope`
         is omitted, it is inferred from `cls.__module__`.
      2. Upserts the on-grid `Collector` node with deterministic identity:
         entity_id = uuid5(NAMESPACE_COLLECTOR, f"{scope}:{key}").

    Rejects anything that is not a CollectorBase subclass
    (req-tap-cares-collector-module-class-6). `name` and `description` are
    required: every collector that lands on the grid carries human-readable
    identity for admin surfaces (req-tap-cares-collector-registration-3).

    Spec: req-tap-cares-collector-registration.
    """
    if not (isinstance(cls, type) and issubclass(cls, CollectorBase)):
        raise ImproperlyConfigured(
            f"register_collector: {cls!r} must be a subclass of CollectorBase."
        )

    # Phase 1: sub-grid registration of the runner class.
    collector_registry.register(key, cls, scope=scope)

    # Phase 2: grid-side upsert of the Collector node.
    effective_scope = scope or cls.__module__
    qualified_key = f"{effective_scope}:{key}"
    _ensure_collector_node(qualified_key, name=name, description=description)


def _ensure_collector_node(
    qualified_key: str,
    *,
    name: str,
    description: str,
) -> None:
    """Upsert the on-grid Collector node for a registered runner.

    Identity is `uuid5(NAMESPACE_COLLECTOR, qualified_key)`. On first
    registration creates the row via `_create_node_internal` (Collector is
    INTERNAL_ONLY so the generic service layer would reject it). On subsequent
    registrations updates `name` and/or `description` if they have drifted;
    otherwise no-op.

    If the database is not yet ready (e.g. during `makemigrations` before
    migrations have been applied), this function silently skips and returns.
    Subsequent app.ready() runs will retry once the DB is usable. This keeps
    Django management commands working during fresh-install bootstrap without
    forcing a separate post-migrate hook.
    """
    # Local imports keep this module importable before Django apps are fully
    # set up (e.g. during settings evaluation in some test harnesses).
    from tap_cares.models import Collector
    from tap_grid.services import _create_node_internal, _patch_node_internal

    entity_id = uuid.uuid5(NAMESPACE_COLLECTOR, qualified_key)

    try:
        existing = Collector.objects.filter(entity_id=entity_id).first()
    except (OperationalError, ProgrammingError):
        # DB not migrated yet, or tap_cares tables don't exist.
        # Silent skip; the next app.ready() will pick it up after migrate.
        logger.debug(
            "Collector grid-node upsert skipped (DB not ready): %s", qualified_key
        )
        return
    except Exception:
        # Catch-all for other DB-access blockers — e.g. pytest-django's
        # "Database access not allowed" guard for tests that don't mark
        # themselves with @pytest.mark.django_db. The runner registration
        # still succeeded; the on-grid upsert can wait for a context that
        # actually has a database available.
        logger.debug(
            "Collector grid-node upsert skipped (DB access blocked): %s",
            qualified_key,
        )
        return

    if existing is None:
        result = _create_node_internal(
            "collector",
            {
                "name": name,
                "description": description,
                "collector_registry": qualified_key,
            },
            entity_id=entity_id,
        )
        if not result.success:
            raise ImproperlyConfigured(
                f"_ensure_collector_node({qualified_key!r}) create failed: "
                f"{[(e.code, e.message) for e in result.errors]}"
            )
        return

    # Existing row — patch only the mutable descriptive fields if they have
    # drifted. collector_registry is identity-bearing and not patched here.
    drift: dict[str, str] = {}
    if existing.name != name:
        drift["name"] = name
    if existing.description != description:
        drift["description"] = description
    if not drift:
        return

    result = _patch_node_internal(entity_id, drift)
    if not result.success:
        raise ImproperlyConfigured(
            f"_ensure_collector_node({qualified_key!r}) patch failed: "
            f"{[(e.code, e.message) for e in result.errors]}"
        )


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
            f"No collector registered for key '{collector_key}'. "
            f"Registered: {collector_registry.keys()}"
        ) from None
