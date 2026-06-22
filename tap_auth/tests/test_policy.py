"""Tests for the authorization policy gate (req-tap-auth-policy)."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group

from tap_auth import policy, sync
from tap_auth.errors import (
    CapabilityDenied,
    InactiveActor,
    MissingActor,
    UnknownCapability,
)
from tap_auth.models import User
from tap_grid.caller_context import CallerContext


@pytest.fixture
def synced(db):
    """Auth bootstrap applied: capabilities, groups, built-in actors."""
    sync.sync_auth()


@pytest.fixture(autouse=True)
def _clear_ledger():
    """Each test starts and ends with a clean decision ledger."""
    policy.reset_authorization_ledger()
    yield
    policy.reset_authorization_ledger()


def _admin_user() -> User:
    user = User.objects.create_user(username="alice", password="x")
    user.groups.add(Group.objects.get(name="tap_admin"))
    return user


def _no_caps_user() -> User:
    return User.objects.create_user(username="bob", password="x")


@pytest.mark.django_db
class TestAuthorize:
    def test_admin_allowed(self, synced):
        ctx = CallerContext(user=_admin_user())
        # No raise == allowed (authorize returns None).
        policy.authorize(ctx, "grid.read")
        policy.authorize(ctx, "grid.purge")  # admin holds all

    def test_no_caps_denied(self, synced):
        ctx = CallerContext(user=_no_caps_user())
        with pytest.raises(CapabilityDenied):
            policy.authorize(ctx, "grid.read")

    def test_missing_actor(self, synced):
        with pytest.raises(MissingActor):
            policy.authorize(CallerContext(user=None), "grid.read")

    def test_inactive_actor_denied(self, synced):
        user = _admin_user()
        user.is_active = False
        user.save(update_fields=["is_active"])
        with pytest.raises(InactiveActor):
            policy.authorize(CallerContext(user=user), "grid.read")

    def test_deactivated_actor_denied(self, synced):
        from django.utils import timezone

        user = _admin_user()
        user.deactivated_at = timezone.now()
        user.save(update_fields=["deactivated_at"])
        with pytest.raises(InactiveActor):
            policy.authorize(CallerContext(user=user), "grid.read")

    def test_unknown_capability_fails_closed(self, synced):
        ctx = CallerContext(user=_admin_user())
        with pytest.raises(UnknownCapability):
            policy.authorize(ctx, "bogus.capability")

    def test_superuser_is_not_a_bypass(self, synced):
        """is_superuser must grant nothing at the TAP service boundary."""
        root = User.objects.create_superuser(username="root", password="x")
        assert root.is_superuser is True
        ctx = CallerContext(user=root)
        # No tap_admin membership → denied despite superuser.
        with pytest.raises(CapabilityDenied):
            policy.authorize(ctx, "grid.read")


@pytest.mark.django_db
class TestCanPredicate:
    def test_can_returns_bool(self, synced):
        admin_ctx = CallerContext(user=_admin_user())
        none_ctx = CallerContext(user=_no_caps_user())
        assert policy.can(admin_ctx, "grid.write") is True
        assert policy.can(none_ctx, "grid.write") is False

    def test_can_does_not_record_decision(self, synced):
        """can() must never satisfy the enforcement ledger (req-tap-auth-policy)."""
        ctx = CallerContext(user=_admin_user())
        policy.can(ctx, "grid.write")
        assert "grid.write" not in policy.authorized_capabilities()

    def test_can_never_raises(self, synced):
        assert policy.can(CallerContext(user=None), "grid.read") is False
        assert policy.can(CallerContext(user=_admin_user()), "bogus.cap") is False


@pytest.mark.django_db
class TestDecisionLedger:
    def test_authorize_records(self, synced):
        ctx = CallerContext(user=_admin_user())
        policy.authorize(ctx, "grid.read")
        assert "grid.read" in policy.authorized_capabilities()

    def test_reset_clears(self, synced):
        ctx = CallerContext(user=_admin_user())
        policy.authorize(ctx, "grid.read")
        policy.reset_authorization_ledger()
        assert policy.authorized_capabilities() == frozenset()

    def test_denied_not_recorded(self, synced):
        ctx = CallerContext(user=_no_caps_user())
        with pytest.raises(CapabilityDenied):
            policy.authorize(ctx, "grid.read")
        assert "grid.read" not in policy.authorized_capabilities()
