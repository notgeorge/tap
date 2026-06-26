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

# The principal classes a role may be assignable to (req-tap-auth-roles).
PRINCIPAL_HUMAN = "human"
PRINCIPAL_PROGRAM = "program"

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
    assignable_to: frozenset[str] = field(default_factory=frozenset)
    """The principal classes this role may be granted to — ``"human"`` (via
    ``auth.initial_grants`` login) and/or ``"program"`` (a built-in program actor).
    The security boundary that keeps program-only roles unreachable from login
    config and human-only roles off program actors (req-tap-auth-roles)."""

    def grantable_to(self, principal_class: str) -> bool:
        """Whether this role may be granted to ``principal_class`` ('human'/'program')."""
        return principal_class in self.assignable_to


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
            assignable_to=frozenset(body["assignable_to"]),
        )
    return roles


# Canonical role registry, loaded from roles.json at import.
ROLES: dict[str, RoleSpec] = _load_roles()

# Roles assignable to each principal class (req-tap-auth-roles), derived from each
# role's declared ``assignable_to``. HUMAN_ASSIGNABLE_ROLES is exactly the set a
# person may be granted at login via ``auth.initial_grants`` — program-only roles
# (``tap_bootloader``, ``tap_cares.*``) are excluded so login config can never hand
# a person a program actor's authority; the auth-boot-section ``initial_grants``
# enum is held in sync with this set, and program-actor bindings against
# PROGRAM_ASSIGNABLE_ROLES, by guard tests.
HUMAN_ASSIGNABLE_ROLES: frozenset[str] = frozenset(k for k, s in ROLES.items() if s.grantable_to(PRINCIPAL_HUMAN))
PROGRAM_ASSIGNABLE_ROLES: frozenset[str] = frozenset(k for k, s in ROLES.items() if s.grantable_to(PRINCIPAL_PROGRAM))

# Back-compat alias: "login-grantable" is exactly "human-assignable" (login is the
# human grant path). Kept so the adapter/boot/schema-guard read intent-first.
LOGIN_GRANTABLE_ROLES: frozenset[str] = HUMAN_ASSIGNABLE_ROLES


def is_login_grantable(key: str) -> bool:
    """Whether ``key`` is a role a human may be granted at login (req-tap-auth-roles).

    False for unknown roles and for every program-only role — the defensive check
    the adapter and boot validation both consult so a misconfigured
    ``initial_grants`` can never grant a non-grantable role to a person."""
    return key in HUMAN_ASSIGNABLE_ROLES


def role_capabilities(key: str) -> tuple[str, ...]:
    """Return the resolved capability names a role grants; raise if the role is unknown."""
    try:
        return ROLES[key].capabilities
    except KeyError:
        raise ImproperlyConfigured(f"Unknown role '{key}' (not defined in roles.json).") from None
