"""Canonical TAP capability registry (req-tap-auth-capabilities).

TAP capabilities are the platform's public authorization vocabulary; Django
permissions are the backend projection. This module is the **source of truth**:
the `Capability` DB table and the projected `auth.Permission` rows are hard-synced
from `CAPABILITIES` here (tap_auth/sync.py), and runtime authorization checks
resolve capabilities by their public name (e.g. ``grid.read``).

The public name is the contract (``grid.read``); the projected Django permission
codename is an implementation detail (``grid_read``), via `codename_for()`.

Role bundles (the explicit, least-privilege capability sets granted to the
protected built-in groups) live here too so the privilege each built-in actor
receives is reviewable in one place. Per spec-tap-boot-v0 `req-boot-phases`, the
bootloader bundle deliberately excludes destructive grid demolition
(`grid.purge`, `grid.delete`) so a boot bug cannot nuke the grid.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


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


# Canonical v1 capability registry. Operation-level (not model-level) in v1.
CAPABILITIES: tuple[CapabilitySpec, ...] = (
    CapabilitySpec("grid.read", "Read TAP graph nodes and edges.", RiskLevel.LOW),
    CapabilitySpec("grid.write", "Create or update TAP graph nodes and edges.", RiskLevel.MEDIUM),
    CapabilitySpec("grid.delete", "Delete (tombstone) TAP graph nodes and edges.", RiskLevel.HIGH),
    CapabilitySpec("grid.import_grift", "Import a GRIFT batch into the grid.", RiskLevel.MEDIUM),
    CapabilitySpec("grid.admin", "Administer grid-level types and configuration.", RiskLevel.HIGH),
    CapabilitySpec(
        "grid.purge",
        "Irreversibly hard-delete graph data (DEBUG-gated; destroys history).",
        RiskLevel.CRITICAL,
    ),
    CapabilitySpec(
        "auth.manage_users",
        "Create, modify, deactivate, and manage user/actor accounts and sessions.",
        RiskLevel.HIGH,
    ),
    CapabilitySpec(
        "auth.manage_providers",
        "Configure authentication providers and identity settings.",
        RiskLevel.HIGH,
    ),
    CapabilitySpec("config.manage", "Manage instance configuration and settings.", RiskLevel.MEDIUM),
    CapabilitySpec("plugins.manage", "Install, enable, disable, or configure plugins.", RiskLevel.HIGH),
    CapabilitySpec("cares.run_collectors", "Run collectors and ingestion jobs.", RiskLevel.MEDIUM),
    CapabilitySpec(
        "ai.delegate",
        "Delegate bounded authority to AI actors acting on a user's behalf.",
        RiskLevel.HIGH,
    ),
)

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


# ---------------------------------------------------------------------------
# Role bundles — the explicit capability set each protected built-in group holds.
# Least-privilege and reviewable in one place (req-tap-auth-capabilities-5,
# req-boot-phases least-privilege boot actor).
# ---------------------------------------------------------------------------

# tap_admin: every capability, explicitly (no hidden implication rules).
ADMIN_BUNDLE: tuple[str, ...] = ALL_CAPABILITY_NAMES

# tap_bootloader: everything boot needs and no more. Excludes destructive grid
# demolition (grid.purge, grid.delete) so a boot bug cannot nuke the grid, and
# ai.delegate (boot does not delegate). See spec-tap-boot-v0 req-boot-phases.
BOOTLOADER_BUNDLE: tuple[str, ...] = (
    "grid.read",
    "grid.write",
    "grid.import_grift",
    "grid.admin",
    "auth.manage_users",
    "auth.manage_providers",
    "config.manage",
    "plugins.manage",
    "cares.run_collectors",
)

# tap_cares.collector: the single shared bundle for ALL collectors in v0. Per-collector
# (plugin-defined) actors/bundles are deferred to the plugin refactor; see the
# spec Backlog. Collectors read existing nodes to resolve links, write/import
# their collected GRIFT batches, and run under the collector runtime.
COLLECTOR_BUNDLE: tuple[str, ...] = (
    "grid.read",
    "grid.write",
    "grid.import_grift",
    "cares.run_collectors",
)

# tap_cares.scheduler: writes its own operational bookkeeping (Schedule/ScheduleFire
# nodes + edges) and triggers collection runs. The triggered run itself executes
# as the collector actor, not the scheduler.
SCHEDULER_BUNDLE: tuple[str, ...] = (
    "grid.read",
    "grid.write",
    "cares.run_collectors",
)
