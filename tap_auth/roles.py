"""TAP role definitions loader — named capability bundles (req-tap-auth-roles).

Roles are the least-privilege capability sets granted to the protected built-in
groups (`tap_admin`, `tap_bootloader`, `tap_cares.collector`, `tap_cares.scheduler`).
The source of truth is the version-controlled declarative file ``tap_auth/roles.json``
(schema: ``tap_auth/schemas/roles.schema.json``); `tap_auth.sync.sync_protected_groups`
hard-syncs each group's Django permissions to its role here.

Roles are security boundaries. Beyond schema validation, the loader enforces the
semantic invariants the schema cannot express and fails loud (`ImproperlyConfigured`)
at import on any violation:

- every capability a role names must be a defined capability (no typos / rogue caps);
- the ``"*"`` wildcard ("every defined capability, including ones plugins add
  later") is **admin-only**;
- (the `tap_bootloader` least-privilege exclusion of `grid.purge`/`grid.delete` is
  additionally pinned by a guard test, `req-boot-phases` / `req-tap-auth-roles-4`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema
from django.core.exceptions import ImproperlyConfigured

from tap_auth.capabilities import ALL_CAPABILITY_NAMES, get_capability

_DATA_PATH = Path(__file__).resolve().parent / "roles.json"
_SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "roles.schema.json"

# The single role permitted to use the "*" (all-capabilities) wildcard.
ADMIN_ROLE = "tap_admin"

# The capabilities the bootloader role must never hold — destructive grid demolition
# a boot bug must not be able to reach (spec-tap-boot-v0 req-boot-phases). Enforced
# by guard test; documented here as the named invariant.
BOOTLOADER_FORBIDDEN: tuple[str, ...] = ("grid.purge", "grid.delete", "ai.delegate")


@dataclass(frozen=True)
class RoleSpec:
    """One role definition with its capabilities resolved (``"*"`` -> all names)."""

    key: str
    description: str
    capabilities: tuple[str, ...]
    is_wildcard: bool
    description_json: dict[str, Any] = field(default_factory=dict)
    """Optional structured context, synced to ``ProtectedGroup.description_json``."""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ImproperlyConfigured(f"roles file {path.name} could not be read: {exc}") from exc


def _load_roles() -> dict[str, RoleSpec]:
    data = _load_json(_DATA_PATH)
    schema = _load_json(_SCHEMA_PATH)
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(p) for p in exc.absolute_path) or "<root>"
        raise ImproperlyConfigured(f"roles.json failed schema validation at {location}: {exc.message}") from exc

    roles: dict[str, RoleSpec] = {}
    for key, body in data["roles"].items():
        caps_field = body["capabilities"]
        if caps_field == "*":
            if key != ADMIN_ROLE:
                raise ImproperlyConfigured(f"roles.json: the '*' wildcard is admin-only; role '{key}' may not use it.")
            resolved = tuple(ALL_CAPABILITY_NAMES)
            wildcard = True
        else:
            unknown = [c for c in caps_field if get_capability(c) is None]
            if unknown:
                raise ImproperlyConfigured(f"roles.json: role '{key}' names undefined capabilities: {sorted(unknown)}")
            resolved = tuple(caps_field)
            wildcard = False
        roles[key] = RoleSpec(
            key=key,
            description=body["description"],
            capabilities=resolved,
            is_wildcard=wildcard,
            description_json=body.get("description_json", {}),
        )
    return roles


# Canonical role registry, loaded from roles.json at import.
ROLES: dict[str, RoleSpec] = _load_roles()


def role_capabilities(key: str) -> tuple[str, ...]:
    """Return the resolved capability names a role grants; raise if the role is unknown."""
    try:
        return ROLES[key].capabilities
    except KeyError:
        raise ImproperlyConfigured(f"Unknown role '{key}' (not defined in roles.json).") from None
