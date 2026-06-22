"""Tests for the tap_auth User spine (req-tap-auth-user-model, req-tap-auth-builtins).

Focused coverage for the canonical user model: AUTH_USER_MODEL wiring, actor
fields, the bidirectional built-in-key constraint (incl. the privilege-escalation
case), key immutability, and admin read-only protection.
"""

from __future__ import annotations

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from tap_auth.models import User, UserKind

pytestmark = pytest.mark.django_db


class TestUserModelWiring:
    def test_auth_user_model_points_here(self):
        assert settings.AUTH_USER_MODEL == "tap_auth.User"
        assert get_user_model() is User

    def test_table_name_and_app(self):
        assert User._meta.db_table == "tap_user"
        assert User._meta.app_label == "tap_auth"

    def test_user_lands_in_first_migration(self):
        """The swapped user model must be in tap_auth's first migration
        (req-tap-auth-user-model-6) so it is a clean dependency root."""
        from importlib import import_module

        from django.db import migrations

        mod = import_module("tap_auth.migrations.0001_initial")
        created = [op.name for op in mod.Migration.operations if isinstance(op, migrations.CreateModel)]
        assert "User" in created

    def test_actor_field_defaults(self):
        user = User.objects.create_user(username="plain", password="x")
        assert user.user_kind == UserKind.HUMAN
        assert user.is_tap_builtin is False
        assert user.tap_builtin_key is None
        assert user.deactivated_at is None


class TestBuiltinKeyConstraint:
    def test_builtin_requires_key_db(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            User.objects.create(username="b", is_tap_builtin=True, tap_builtin_key=None)

    def test_ordinary_user_cannot_reserve_builtin_key_db(self):
        """The privilege-escalation case: an ordinary (non-builtin) row must not be
        able to reserve a built-in key like 'tap_bootloader'."""
        with pytest.raises(IntegrityError), transaction.atomic():
            User.objects.create(username="sneak", is_tap_builtin=False, tap_builtin_key="tap_bootloader")

    def test_clean_rejects_builtin_without_key(self):
        user = User(username="b2", is_tap_builtin=True)
        with pytest.raises(ValidationError):
            user.clean()

    def test_clean_rejects_ordinary_with_key(self):
        user = User(username="b3", is_tap_builtin=False, tap_builtin_key="tap_bootloader")
        with pytest.raises(ValidationError):
            user.clean()

    def test_builtin_key_unique(self):
        User.objects.create(username="one", is_tap_builtin=True, tap_builtin_key="dup")
        with pytest.raises(IntegrityError), transaction.atomic():
            User.objects.create(username="two", is_tap_builtin=True, tap_builtin_key="dup")


class TestBuiltinKeyImmutability:
    def test_save_blocks_changing_key(self):
        user = User.objects.create(username="b", is_tap_builtin=True, tap_builtin_key="tap_x")
        user.tap_builtin_key = "tap_y"
        with pytest.raises(ValidationError, match="immutable"):
            user.save()

    def test_save_blocks_clearing_key(self):
        user = User.objects.create(username="b", is_tap_builtin=True, tap_builtin_key="tap_x")
        user.tap_builtin_key = None
        with pytest.raises(ValidationError, match="immutable"):
            user.save()

    def test_null_to_value_allowed_once(self):
        user = User.objects.create_user(username="plain", password="x")
        user.is_tap_builtin = True
        user.tap_builtin_key = "tap_minted"
        user.save()  # null -> value is the set-once mint, allowed
        user.refresh_from_db()
        assert user.tap_builtin_key == "tap_minted"

    def test_immutability_is_application_layer_only(self):
        """Documents the honest limitation: QuerySet.update() bypasses save()."""
        user = User.objects.create(username="b", is_tap_builtin=True, tap_builtin_key="tap_x")
        # .update() does not run save()/clean(), so it bypasses the guard. This is
        # an accepted v1 limitation (sync.py is the sole intended writer).
        User.objects.filter(pk=user.pk).update(tap_builtin_key="tap_changed")
        user.refresh_from_db()
        assert user.tap_builtin_key == "tap_changed"


class TestDeactivationMetadata:
    def test_deactivation_fields_round_trip(self):
        actor = User.objects.create_user(username="admin", password="x")
        target = User.objects.create_user(username="target", password="x")
        now = timezone.now()
        target.deactivated_at = now
        target.deactivated_reason = "offboarded"
        target.deactivated_by_actor = actor
        target.save()
        target.refresh_from_db()
        assert target.deactivated_at == now
        assert target.deactivated_reason == "offboarded"
        assert target.deactivated_by_actor_id == actor.pk


class TestAdminReadonly:
    def test_builtin_fields_readonly(self):
        from tap_auth.admin import TapUserAdmin

        assert "is_tap_builtin" in TapUserAdmin.readonly_fields
        assert "tap_builtin_key" in TapUserAdmin.readonly_fields


class TestAuthPrefixReservation:
    def test_app_reserves_auth_prefix(self):
        from tap_auth.apps import TapAuthConfig

        assert "/auth" in TapAuthConfig.reserved_url_prefixes
