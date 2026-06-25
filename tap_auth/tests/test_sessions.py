"""Session invalidation + local-auth toggle tests (increment 5 — req-tap-auth-sessions,
req-tap-auth-local)."""

from __future__ import annotations

import pytest
from django.contrib.auth import SESSION_KEY, authenticate, get_user_model
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.test import Client

from tap_auth.errors import AuthzError
from tap_auth.sessions import (
    invalidate_all_sessions,
    invalidate_session,
    invalidate_user_sessions,
)

User = get_user_model()


def _admin(username: str = "sess-admin"):
    u = User.objects.create_user(username=username, password="x")
    u.groups.add(Group.objects.get(name="tap_admin"))
    return u


def _login(user) -> Client:
    c = Client()
    c.force_login(user)
    return c


@pytest.mark.django_db
class TestSessionInvalidation:
    def test_invalidate_all(self):
        admin = _admin()
        _login(User.objects.create_user(username="a"))
        _login(User.objects.create_user(username="b"))
        assert Session.objects.count() >= 2
        n = invalidate_all_sessions(admin)
        assert n >= 2
        assert Session.objects.count() == 0

    def test_invalidate_user_scoped(self):
        admin = _admin()
        ua = User.objects.create_user(username="ua")
        ub = User.objects.create_user(username="ub")
        _login(ua)
        _login(ub)
        n = invalidate_user_sessions(admin, ua)
        assert n == 1
        remaining = {s.get_decoded().get(SESSION_KEY) for s in Session.objects.all()}
        assert str(ua.pk) not in remaining
        assert str(ub.pk) in remaining  # the banhammer is surgical — ub untouched

    def test_invalidate_one_session_by_key(self):
        admin = _admin()
        client = _login(User.objects.create_user(username="uc"))
        key = client.session.session_key
        assert invalidate_session(admin, key) == 1
        assert not Session.objects.filter(session_key=key).exists()

    def test_denied_without_capability(self):
        # a user NOT in tap_admin cannot invalidate sessions
        bob = User.objects.create_user(username="bob")
        with pytest.raises(AuthzError):
            invalidate_all_sessions(bob)

    def test_denied_user_scope_too(self):
        bob = User.objects.create_user(username="bob2")
        target = User.objects.create_user(username="target")
        with pytest.raises(AuthzError):
            invalidate_user_sessions(bob, target)


@pytest.mark.django_db
class TestLocalAuthToggle:
    def test_password_refused_when_disabled(self, settings):
        settings.TAP_LOCAL_PASSWORD_ENABLED = False
        User.objects.create_user(username="dave", password="secret123")
        # blocked everywhere (this is the same path Django admin login uses)
        assert authenticate(username="dave", password="secret123") is None

    def test_password_allowed_when_enabled(self, settings):
        settings.TAP_LOCAL_PASSWORD_ENABLED = True
        User.objects.create_user(username="erin", password="secret123")
        assert authenticate(username="erin", password="secret123") is not None

    def test_disable_does_not_deactivate_user(self, settings):
        settings.TAP_LOCAL_PASSWORD_ENABLED = False
        user = User.objects.create_user(username="frank", password="secret123")
        assert authenticate(username="frank", password="secret123") is None
        user.refresh_from_db()
        assert user.is_active is True  # disabling login is NOT deactivation
