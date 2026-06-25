"""Canonical TAP capability registry (req-tap-auth-capabilities).

TAP capabilities are the platform's public authorization vocabulary; Django
permissions are the backend projection. The **source of truth** is the
version-controlled declarative file ``tap_auth/capabilities.json`` (schema:
``tap_auth/schemas/capabilities.schema.json``); this module is the thin loader
that validates it and exposes the in-memory registry. The `Capability` DB table
and the projected `auth.Permission` rows are hard-synced from `CAPABILITIES`
(tap_auth/sync.py), and runtime authorization checks resolve capabilities by
their public name (e.g. ``grid.read``).

The public name is the contract (``grid.read``); the projected Django permission
codename is an implementation detail (``grid_read``), via `codename_for()`.

Role bundles (the least-privilege capability sets granted to the protected
built-in groups) live in ``tap_auth/roles.json`` (loaded by `tap_auth.roles`),
**not here** — moving them out of this file is `req-tap-auth-roles`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import jsonschema
from django.core.exceptions import ImproperlyConfigured

_DATA_PATH = Path(__file__).resolve().parent / "capabilities.json"
_SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "capabilities.schema.json"


class RiskLevel(StrEnum):
    """Risk/classification metadata for a capability (req-tap-auth-capabilities-7).

    Queryable from the DB so a future AI/Paladin actor can reason about how
    dangerous an action is without code access.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class CapabilitySpec:
    """One capability definition in the canonical registry."""

    name: str
    """Public TAP vocabulary, e.g. ``grid.read``."""
    description: str
    """Human-readable meaning, stored on the Capability row."""
    risk: RiskLevel


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ImproperlyConfigured(f"capability registry file {path.name} could not be read: {exc}") from exc


def _load_capabilities() -> tuple[CapabilitySpec, ...]:
    """Load + validate ``capabilities.json`` into the canonical registry.

    Fails loud (`ImproperlyConfigured`) on a missing/unreadable file, schema
    violation, or duplicate capability name — never a silent partial registry.
    """
    data = _load_json(_DATA_PATH)
    schema = _load_json(_SCHEMA_PATH)
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(p) for p in exc.absolute_path) or "<root>"
        raise ImproperlyConfigured(f"capabilities.json failed schema validation at {location}: {exc.message}") from exc

    specs = tuple(
        CapabilitySpec(name=c["name"], description=c["description"], risk=RiskLevel(c["risk"]))
        for c in data["capabilities"]
    )
    names = [s.name for s in specs]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ImproperlyConfigured(f"capabilities.json has duplicate capability names: {duplicates}")
    return specs


# Canonical v1 capability registry, loaded from capabilities.json at import.
# Operation-level (not model-level) in v1.
CAPABILITIES: tuple[CapabilitySpec, ...] = _load_capabilities()

ALL_CAPABILITY_NAMES: tuple[str, ...] = tuple(c.name for c in CAPABILITIES)

# The capability each op-class requires at the write backstop (req-tap-auth-policy
# On By Default), checked statelessly against what the actor holds. A create/update
# op requires grid.write; a delete op requires grid.delete *specifically*. Broad
# covers (grid.import_grift, grid.admin) deliberately do NOT satisfy the delete
# check — so a bootloader/collector cannot tombstone through an import cover
# (doc-auth-per-app-standards "split cover semantics"). The grift importer
# authorizes grid.delete explicitly in its own scope when its batch contains
# removals, so an actor lacking it gets a clean denial rather than tripping this
# structural net.
WRITE_CAPABILITY: str = "grid.write"
DELETE_CAPABILITY: str = "grid.delete"

# The single capability every graph READ requires (the read backstop checks for
# exactly this on the Search dispatch chokepoint).
READ_CAPABILITY: str = "grid.read"

_BY_NAME: dict[str, CapabilitySpec] = {c.name: c for c in CAPABILITIES}


def get_capability(name: str) -> CapabilitySpec | None:
    """Return the registered CapabilitySpec for ``name``, or None if unknown."""
    return _BY_NAME.get(name)


def codename_for(name: str) -> str:
    """Project a public capability name to its Django permission codename.

    ``grid.read`` -> ``grid_read``. The public name is the contract; the codename
    is storage. Checked via ``has_perm("tap_auth.grid_read")`` semantics, but TAP
    authorization never calls ``has_perm`` directly (it ignores ``is_superuser``).
    """
    return name.replace(".", "_")
