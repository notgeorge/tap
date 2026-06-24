"""ensure_initial_admin: create-or-update from env + tap_admin join (req-tap-auth-boot)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from tap_auth.sync import GROUP_ADMIN, ensure_initial_admin


@pytest.fixture
def admin_env(monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "bootadmin")
    monkeypatch.setenv("DJANGO_SUPERUSER_EMAIL", "bootadmin@example.test")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "s3cret-pw-xyz")


@pytest.mark.django_db
def test_creates_superuser_and_joins_tap_admin(admin_env):
    user = ensure_initial_admin()
    assert user is not None
    assert user.is_superuser and user.is_staff
    assert user.email == "bootadmin@example.test"
    assert user.check_password("s3cret-pw-xyz")
    assert user.groups.filter(name=GROUP_ADMIN).exists()


@pytest.mark.django_db
def test_idempotent(admin_env):
    ensure_initial_admin()
    ensure_initial_admin()
    User = get_user_model()
    assert User.objects.filter(username="bootadmin").count() == 1
    assert User.objects.get(username="bootadmin").groups.filter(name=GROUP_ADMIN).count() == 1


@pytest.mark.django_db
def test_noop_without_username(monkeypatch):
    monkeypatch.delenv("DJANGO_SUPERUSER_USERNAME", raising=False)
    User = get_user_model()
    before = User.objects.count()
    assert ensure_initial_admin() is None
    assert User.objects.count() == before
