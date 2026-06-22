"""Tests for the on-by-default enforcement primitives (req-tap-auth-policy)."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group

from tap_auth import policy, sync
from tap_auth.enforcement import (
    assert_read_authorized,
    assert_write_authorized,
    requires_capability,
)
from tap_auth.errors import CapabilityDenied, MissingActor, UnguardedOperation
from tap_auth.models import User
from tap_grid.caller_context import CallerContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def synced():
    sync.sync_auth()


@pytest.fixture(autouse=True)
def _clean_ledger():
    policy.reset_authorization_ledger()
    yield
    policy.reset_authorization_ledger()


def _admin_ctx() -> CallerContext:
    user = User.objects.create_user(username="alice", password="x")
    user.groups.add(Group.objects.get(name="tap_admin"))
    return CallerContext(user=user)


def _no_caps_ctx() -> CallerContext:
    return CallerContext(user=User.objects.create_user(username="bob", password="x"))


class TestRequiresCapability:
    def test_allows_authorized_and_backstop_passes_inside(self, synced):
        @requires_capability("grid.write")
        def guarded_write(*, caller_context: CallerContext | None = None) -> str:
            # Inside the guarded scope the write backstop must pass.
            assert_write_authorized(caller_context)
            return "ok"

        assert guarded_write(caller_context=_admin_ctx()) == "ok"

    def test_denies_unauthorized(self, synced):
        @requires_capability("grid.write")
        def guarded_write(*, caller_context: CallerContext | None = None) -> str:
            return "ok"

        with pytest.raises(CapabilityDenied):
            guarded_write(caller_context=_no_caps_ctx())

    def test_missing_actor(self, synced):
        @requires_capability("grid.write")
        def guarded_write(*, caller_context: CallerContext | None = None) -> str:
            return "ok"

        with pytest.raises(MissingActor):
            guarded_write(caller_context=CallerContext(user=None))

    def test_resolves_from_contextvar(self, synced):
        @requires_capability("grid.read")
        def guarded_read(*, caller_context: CallerContext | None = None) -> str:
            assert_read_authorized(caller_context)
            return "ok"

        from tap_grid.caller_context import set_caller_context

        set_caller_context(_admin_ctx())
        try:
            assert guarded_read() == "ok"  # ctx resolved from contextvar
        finally:
            set_caller_context(None)

    def test_scope_does_not_leak_after_call(self, synced):
        ctx = _admin_ctx()

        @requires_capability("grid.write")
        def guarded_write(*, caller_context: CallerContext | None = None) -> str:
            return "ok"

        guarded_write(caller_context=ctx)
        # After the guarded call returns, its scope is popped — a bare backstop
        # check now sees no recorded decision.
        with pytest.raises(UnguardedOperation):
            assert_write_authorized(ctx)


class TestWriteBackstop:
    def test_unguarded_write_fails_closed(self, synced):
        with pytest.raises(UnguardedOperation, match="unguarded write"):
            assert_write_authorized(_admin_ctx())

    def test_passes_when_write_cap_recorded(self, synced):
        token = policy.push_authorization_scope()
        try:
            policy.record_authorization("grid.write")
            assert_write_authorized(_admin_ctx())  # no raise == pass
        finally:
            policy.pop_authorization_scope(token)

    def test_read_cap_alone_does_not_authorize_write(self, synced):
        token = policy.push_authorization_scope()
        try:
            policy.record_authorization("grid.read")
            with pytest.raises(UnguardedOperation):
                assert_write_authorized(_admin_ctx())
        finally:
            policy.pop_authorization_scope(token)


class TestReadBackstop:
    def test_unguarded_read_fails_closed(self, synced):
        with pytest.raises(UnguardedOperation, match="unguarded read"):
            assert_read_authorized(_admin_ctx())

    def test_passes_when_read_cap_recorded(self, synced):
        token = policy.push_authorization_scope()
        try:
            policy.record_authorization("grid.read")
            assert_read_authorized(_admin_ctx())  # no raise == pass
        finally:
            policy.pop_authorization_scope(token)
