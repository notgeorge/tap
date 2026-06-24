"""manage.py boot — profile resolution + deploy guard (req-boot-profile)."""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


@pytest.fixture(autouse=True)
def _no_ambient_profile(monkeypatch):
    monkeypatch.delenv("TAP_BOOT_PROFILE", raising=False)
    monkeypatch.delenv("DJANGO_SUPERUSER_USERNAME", raising=False)


@pytest.mark.django_db
def test_require_profile_without_profile_fails():
    with pytest.raises(CommandError, match="requires an explicit profile"):
        call_command("boot", "--require-profile")


@pytest.mark.django_db
def test_require_profile_with_allow_empty_runs_auth_only():
    # No raise: an explicit allow-empty deploy boot is a valid auth-only standup.
    call_command("boot", "--require-profile", "--allow-empty")


@pytest.mark.django_db
def test_unknown_profile_fails_loud():
    with pytest.raises(CommandError, match="not found"):
        call_command("boot", "--profile", "no-such-profile")


@pytest.mark.django_db
def test_list_shows_known_profiles(capsys):
    call_command("boot", "--list")
    out = capsys.readouterr().out
    assert "samsite" in out
    assert "base" in out
