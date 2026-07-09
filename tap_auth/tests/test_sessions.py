"""Session invalidation + local-auth toggle tests (increment 5 — req-tap-auth-sessions,
req-tap-auth-local)."""

from __future__ import annotations

import pytest
from django.contrib.auth import SESSION_KEY, authenticate, get_user_model
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client

from tap_auth.errors import AuthzError
from tap_auth.sessions import (
    AmbiguousUserSelector,
    invalidate_all_sessions,
    invalidate_session,
    invalidate_user_sessions,
    resolve_user,
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
class TestResolveUser:
    """`resolve_user` keys off the unique username; email is a fail-loud
    convenience, never a silent pick (req-tap-auth-email-not-identity)."""

    def test_resolves_by_username(self):
        u = User.objects.create_user(username="rick", email="rick@x.com")
        assert resolve_user("rick") == u

    def test_resolves_by_unique_email(self):
        u = User.objects.create_user(username="morty", email="morty@x.com")
        assert resolve_user("morty@x.com") == u

    def test_email_match_is_case_insensitive(self):
        u = User.objects.create_user(username="beth", email="beth@x.com")
        assert resolve_user("BETH@X.COM") == u

    def test_unknown_selector_returns_none(self):
        assert resolve_user("nobody@nowhere.test") is None

    def test_duplicate_email_fails_loud_not_silent_pick(self):
        # duplicate emails are permitted at the DB level; email must not resolve.
        User.objects.create_user(username="jerry1", email="dup@x.com")
        User.objects.create_user(username="jerry2", email="dup@x.com")
        with pytest.raises(AmbiguousUserSelector) as exc:
            resolve_user("dup@x.com")
        assert exc.value.count == 2

    def test_username_wins_even_when_email_ambiguous(self):
        # a unique username is authoritative regardless of email collisions
        target = User.objects.create_user(username="summer", email="dup2@x.com")
        User.objects.create_user(username="other", email="dup2@x.com")
        assert resolve_user("summer") == target


@pytest.mark.django_db
class TestAuthSessionsCommand:
    """The `auth_sessions` command fails loud on an ambiguous email selector for
    either --as-user or --user (req-tap-auth-email-not-identity) — no silent pick
    of the wrong authority or the wrong ban target."""

    def test_ambiguous_as_user_email_fails_loud(self):
        User.objects.create_user(username="op1", email="op@x.com")
        User.objects.create_user(username="op2", email="op@x.com")
        with pytest.raises(CommandError, match="not a unique identifier"):
            call_command("auth_sessions", "--as-user", "op@x.com", "--all")

    def test_ambiguous_target_user_email_fails_loud(self):
        admin = _admin("cmd-admin")
        User.objects.create_user(username="t1", email="t@x.com")
        User.objects.create_user(username="t2", email="t@x.com")
        with pytest.raises(CommandError, match="not a unique identifier"):
            call_command("auth_sessions", "--as-user", admin.username, "--user", "t@x.com")

    def test_unknown_as_user_fails_loud(self):
        with pytest.raises(CommandError, match="not found"):
            call_command("auth_sessions", "--as-user", "ghost", "--all")


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
