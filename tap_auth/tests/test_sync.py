"""Tests for the auth bootstrap sync (req-tap-auth-capabilities, req-tap-auth-builtins)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from tap_auth import sync
from tap_auth.capabilities import ALL_CAPABILITY_NAMES, codename_for
from tap_auth.models import Capability, ProtectedGroup

User = get_user_model()


def _inject_rogue_capability(name: str = "rogue.cap") -> None:
    """Create a Capability + Permission not present in the canonical registry."""
    content_type = ContentType.objects.get_for_model(Capability)
    perm = Permission.objects.create(content_type=content_type, codename=codename_for(name), name="rogue")
    Capability.objects.create(name=name, description="rogue", risk="low", permission=perm)


@pytest.mark.django_db
class TestSyncCapabilities:
    def test_creates_all_with_permissions(self):
        result = sync.sync_capabilities()
        assert Capability.objects.count() == len(ALL_CAPABILITY_NAMES)
        assert Capability.objects.exclude(permission=None).count() == len(ALL_CAPABILITY_NAMES)
        # created+updated covers the full registry regardless of whether the
        # session-level auth seed already created the rows (conftest).
        assert result["created"] + result["updated"] == len(ALL_CAPABILITY_NAMES)

    def test_idempotent(self):
        sync.sync_capabilities()
        second = sync.sync_capabilities()
        assert Capability.objects.count() == len(ALL_CAPABILITY_NAMES)
        assert second["created"] == 0
        assert second["updated"] == len(ALL_CAPABILITY_NAMES)

    def test_public_name_projects_codename(self):
        sync.sync_capabilities()
        cap = Capability.objects.get(name="grid.read")
        assert cap.permission is not None
        assert cap.permission.codename == "grid_read"

    def test_undeclared_drift_hard_fails(self):
        sync.sync_capabilities()
        _inject_rogue_capability()
        with pytest.raises(sync.AuthSyncError, match="undeclared capability drift"):
            sync.sync_capabilities()

    def test_declared_prune_removes(self):
        sync.sync_capabilities()
        _inject_rogue_capability()
        sync.sync_capabilities(declared_prune=("rogue.cap",))
        assert not Capability.objects.filter(name="rogue.cap").exists()
        assert not Permission.objects.filter(codename="rogue_cap").exists()

    def test_stale_prune_declaration_hard_fails(self):
        sync.sync_capabilities()
        with pytest.raises(sync.AuthSyncError, match="declared-but-not-present"):
            sync.sync_capabilities(declared_prune=("never.existed",))


@pytest.mark.django_db
class TestSyncGroupsAndActors:
    def test_protected_groups_created_with_bundles(self):
        sync.sync_capabilities()
        sync.sync_protected_groups()
        keys = set(ProtectedGroup.objects.values_list("builtin_key", flat=True))
        assert keys == {"tap_admin", "tap_bootloader", "tap_scheduler", "tap_collector"}
        assert Group.objects.get(name="tap_admin").permissions.count() == len(ALL_CAPABILITY_NAMES)
        collector_caps = set(Group.objects.get(name="tap_collector").permissions.values_list("codename", flat=True))
        assert collector_caps == {"grid_read", "grid_write", "grid_import_grift", "cares_run_collectors"}

    def test_group_bundle_is_hard_synced(self):
        sync.sync_capabilities()
        sync.sync_protected_groups()
        collector = Group.objects.get(name="tap_collector")
        # Inject a stray grant; a re-sync must remove it (set() semantics).
        collector.permissions.add(Permission.objects.get(codename="grid_purge"))
        sync.sync_protected_groups()
        assert not collector.permissions.filter(codename="grid_purge").exists()

    def test_program_actors_created_unusable_password(self):
        sync.sync_auth()
        bootloader = User.objects.get(tap_builtin_key="tap_bootloader")
        assert bootloader.user_kind == "program"
        assert bootloader.is_tap_builtin is True
        assert not bootloader.has_usable_password()
        assert list(bootloader.groups.values_list("name", flat=True)) == ["tap_bootloader"]

    def test_tap_test_created_in_test_mode(self):
        # The suite runs under TAP_TEST_MODE=True (tap.test_settings).
        sync.sync_auth()
        test_actor = User.objects.get(tap_builtin_key="tap_test")
        assert test_actor.user_kind == "program"
        assert "tap_admin" in test_actor.groups.values_list("name", flat=True)

    def test_ensure_test_actor_refuses_outside_test_mode(self, settings):
        settings.TAP_TEST_MODE = False
        with pytest.raises(sync.AuthSyncError, match="TAP_TEST_MODE"):
            sync.ensure_test_actor()

    def test_full_sync_idempotent(self):
        sync.sync_auth()
        sync.sync_auth()
        assert User.objects.filter(tap_builtin_key="tap_bootloader").count() == 1
        assert ProtectedGroup.objects.count() == 4
