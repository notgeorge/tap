"""Auth bootstrap sync — idempotent, hard-sync, security-critical (req-tap-auth-boot).

These functions converge the DB to the canonical code/spec definitions:

- `sync_capabilities()` hard-syncs the `Capability` table + projected `auth.Permission`
  rows to match `tap_auth.capabilities.CAPABILITIES` exactly, hard-failing on
  undeclared drift and applying only explicitly declared prunes.
- `sync_protected_groups()` creates/protects the built-in groups and hard-syncs
  each group's capability grants from its role bundle.
- `sync_builtin_actors()` creates/updates the protected program actors
  (`tap_bootloader`, `tap_cares.scheduler`, `tap_cares.collector`, and — only under
  `TAP_TEST_MODE` — `tap_test`) and ensures their group membership.

These touch Django auth + tap_auth management tables (not TAP-managed graph
entities), so they use direct ORM — auth bootstrap is explicitly out-of-scope of
the service-layer/no-`User=None` contract, like migrations. They are invoked by
an explicit command (and, later, the bootloader's `auth` section handler), never
silent app-startup mutation.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from tap_auth import capabilities as caps
from tap_auth.models import Capability, ProtectedGroup

logger = logging.getLogger(__name__)

# Built-in identities. Group builtin_key == member program-actor tap_builtin_key
# where a role has a single dedicated actor; tap_admin is a group whose members
# are humans (initial admins) plus tap_test.
GROUP_ADMIN = "tap_admin"
GROUP_BOOTLOADER = "tap_bootloader"
GROUP_SCHEDULER = "tap_cares.scheduler"
GROUP_COLLECTOR = "tap_cares.collector"

ACTOR_BOOTLOADER = "tap_bootloader"
ACTOR_SCHEDULER = "tap_cares.scheduler"
ACTOR_COLLECTOR = "tap_cares.collector"
ACTOR_TEST = "tap_test"

# group builtin_key -> bundle of capability names it grants (hard-synced).
_GROUP_BUNDLES: dict[str, tuple[str, ...]] = {
    GROUP_ADMIN: caps.ADMIN_BUNDLE,
    GROUP_BOOTLOADER: caps.BOOTLOADER_BUNDLE,
    GROUP_SCHEDULER: caps.SCHEDULER_BUNDLE,
    GROUP_COLLECTOR: caps.COLLECTOR_BUNDLE,
}


class AuthSyncError(Exception):
    """Raised when a sync cannot converge safely (undeclared drift, stale prune,
    or an illegal test-only mutation)."""


def sync_capabilities(*, declared_prune: tuple[str, ...] = ()) -> dict[str, int]:
    """Hard-sync the Capability table + projected Permissions to the registry.

    Creates/updates a `Capability` row and a backing `auth.Permission` for every
    entry in `CAPABILITIES`. Removal is never implicit: a capability present in
    the DB but absent from the registry is **undeclared drift** and hard-fails,
    unless its name is in `declared_prune`, in which case it (and its permission)
    is removed. A `declared_prune` entry that is not actually present is a stale
    declaration and also hard-fails (req-tap-auth-capabilities).

    Returns a small dict of counts for the caller/log.
    """
    content_type = ContentType.objects.get_for_model(Capability)
    registry_names = set(caps.ALL_CAPABILITY_NAMES)
    declared = set(declared_prune)

    with transaction.atomic():
        # 1) Upsert every registry capability + its projected permission.
        created = 0
        updated = 0
        for spec in caps.CAPABILITIES:
            permission, _ = Permission.objects.get_or_create(
                content_type=content_type,
                codename=caps.codename_for(spec.name),
                defaults={"name": spec.description[:255] or spec.name},
            )
            if permission.name != (spec.description[:255] or spec.name):
                permission.name = spec.description[:255] or spec.name
                permission.save(update_fields=["name"])
            _, was_created = Capability.objects.update_or_create(
                name=spec.name,
                defaults={
                    "description": spec.description,
                    "risk": spec.risk.value,
                    "permission": permission,
                },
            )
            created += int(was_created)
            updated += int(not was_created)

        # 2) Detect drift: DB capabilities not in the registry.
        db_names = set(Capability.objects.values_list("name", flat=True))
        drift = db_names - registry_names

        stale_prune = declared - db_names
        if stale_prune:
            raise AuthSyncError(
                "declared capability prune does not match reality (declared-but-not-present): " f"{sorted(stale_prune)}"
            )

        undeclared = drift - declared
        if undeclared:
            raise AuthSyncError(
                "undeclared capability drift — capabilities present in DB but absent from the "
                f"registry and not in the declared prune list: {sorted(undeclared)}. Add them to "
                "the prune declaration or restore them in the registry, then re-run."
            )

        # 3) Apply only the declared removals (capability + its permission).
        pruned = 0
        for name in sorted(drift & declared):
            cap = Capability.objects.filter(name=name).first()
            if cap is None:
                continue
            perm = cap.permission
            cap.delete()
            if perm is not None:
                perm.delete()
            pruned += 1

        logger.info(
            "[09ca] capability sync: %s created, %s updated, %s pruned (registry=%s)",
            created,
            updated,
            pruned,
            len(registry_names),
        )
        return {"created": created, "updated": updated, "pruned": pruned}


def _permissions_for(names: tuple[str, ...]) -> list[Permission]:
    """Resolve the projected Permissions for a bundle of capability names."""
    codenames = [caps.codename_for(n) for n in names]
    perms = list(
        Permission.objects.filter(
            codename__in=codenames,
            content_type=ContentType.objects.get_for_model(Capability),
        )
    )
    if len(perms) != len(codenames):
        found = {p.codename for p in perms}
        missing = [c for c in codenames if c not in found]
        raise AuthSyncError(
            f"bundle references capabilities with no synced permission: {missing}. "
            "Run sync_capabilities() before sync_protected_groups()."
        )
    return perms


def sync_protected_groups() -> None:
    """Create/protect the built-in groups and hard-sync their capability grants."""
    with transaction.atomic():
        for builtin_key, bundle in _GROUP_BUNDLES.items():
            group, _ = Group.objects.get_or_create(name=builtin_key)
            ProtectedGroup.objects.update_or_create(
                group=group,
                defaults={"builtin_key": builtin_key, "is_protected": True},
            )
            # Hard-sync: the group holds exactly the bundle's permissions.
            group.permissions.set(_permissions_for(bundle))
            logger.info("[b247] protected group synced: %s (%s caps)", builtin_key, len(bundle))


def _ensure_program_actor(builtin_key: str, group_key: str) -> None:
    """Create-or-authoritatively-repair a protected program actor + its membership.

    This is a HARD sync, not additive: the actor's managed fields are repaired to
    their canonical values and its group membership is set to *exactly* the one
    intended group (`groups.set`, not `groups.add`). A built-in actor therefore
    cannot drift — e.g. be demoted to `human`, deactivated, or accumulate a stray
    privileged group like `tap_admin` — across re-syncs (req-tap-auth-builtins).
    """
    user_model = get_user_model()
    user, created = user_model.objects.get_or_create(
        tap_builtin_key=builtin_key,
        defaults={
            "username": builtin_key,
            "user_kind": "program",
            "is_tap_builtin": True,
            "is_active": True,
        },
    )
    if created:
        # Program actors never log in with a password.
        user.set_unusable_password()
        logger.info("[8693] built-in program actor created: %s", builtin_key)

    # Repair drifted managed fields back to canonical (tap_builtin_key is left
    # untouched — it is immutable; save() enforces that). A usable password on a
    # program actor is also drift: these identities are never password-login
    # surfaces, so a usable password is repaired back to unusable rather than left
    # as a standing credential (req-tap-auth-builtins).
    # The deactivation trio is cleared too: a built-in that someone (or a buggy
    # flow) deactivated must come back *fully* active on re-sync — clearing
    # is_active alone would leave a `deactivated_at` that policy still denies on,
    # since `policy.is_actor_active` requires both is_active AND no deactivated_at
    # (the zombie built-in; doc-auth-per-app-standards "one definition of active").
    fields = {
        "user_kind": "program",
        "is_tap_builtin": True,
        "is_active": True,
        "deactivated_at": None,
        "deactivated_reason": "",
        "deactivated_by_actor_id": None,
    }
    password_drifted = not created and user.has_usable_password()
    if password_drifted:
        user.set_unusable_password()
        logger.warning("[1d56] repaired usable password on built-in program actor: %s", builtin_key)
    drifted = created or password_drifted or any(getattr(user, name) != value for name, value in fields.items())
    if drifted:
        for name, value in fields.items():
            setattr(user, name, value)
        user.save()

    # Authoritative membership: exactly this one group, no strays.
    user.groups.set([Group.objects.get(name=group_key)])


def sync_builtin_actors() -> None:
    """Create/update the protected program actors and their memberships.

    `tap_test` is created ONLY when `TAP_TEST_MODE` is true (req-tap-auth-builtins);
    attempting it outside test mode is a hard failure, and in non-test mode it is
    silently skipped.
    """
    with transaction.atomic():
        _ensure_program_actor(ACTOR_BOOTLOADER, GROUP_BOOTLOADER)
        _ensure_program_actor(ACTOR_SCHEDULER, GROUP_SCHEDULER)
        _ensure_program_actor(ACTOR_COLLECTOR, GROUP_COLLECTOR)

        if getattr(settings, "TAP_TEST_MODE", False):
            # tap_test is a program actor in tap_admin (broad fixture).
            _ensure_program_actor(ACTOR_TEST, GROUP_ADMIN)
            logger.info("[35a9] tap_test actor synced (TAP_TEST_MODE on)")
        else:
            logger.info("[920c] tap_test actor skipped (TAP_TEST_MODE off)")


def ensure_test_actor() -> object:
    """Create-and-return the `tap_test` program actor; hard-fail outside test mode.

    Test fixtures call this to obtain the canonical authorized test actor. It
    refuses to mint `tap_test` unless `TAP_TEST_MODE` is true, so test-only
    built-ins can never appear in a real instance (req-tap-auth-actor-model).
    """
    if not getattr(settings, "TAP_TEST_MODE", False):
        raise AuthSyncError("refusing to create tap_test outside TAP_TEST_MODE")
    _ensure_program_actor(ACTOR_TEST, GROUP_ADMIN)
    return get_user_model().objects.get(tap_builtin_key=ACTOR_TEST)


def sync_auth(*, declared_prune: tuple[str, ...] = ()) -> None:
    """Run the full auth bootstrap sync in the canonical order (req-tap-auth-boot).

    capability sync -> protected group sync -> built-in actor sync. This is the
    sequence the bootloader's `auth` section handler will run; for now it is
    driven by the explicit management command.
    """
    sync_capabilities(declared_prune=declared_prune)
    sync_protected_groups()
    sync_builtin_actors()
    logger.info("[4279] auth sync complete")
