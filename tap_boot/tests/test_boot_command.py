"""manage.py boot — profile resolution + required-by-default guard (req-boot-profile)."""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


@pytest.fixture(autouse=True)
def _no_ambient_profile(monkeypatch):
    monkeypatch.delenv("TAP_BOOT_PROFILE", raising=False)
    monkeypatch.delenv("DJANGO_SUPERUSER_USERNAME", raising=False)


@pytest.mark.django_db
def test_missing_profile_fails_without_allow_empty():
    # A profile is required by default — no inverted --require-profile flag.
    with pytest.raises(CommandError, match="profile is required"):
        call_command("boot")


@pytest.mark.django_db
def test_allow_empty_runs_auth_only():
    # The single escape hatch: an intentional auth-only standup, no raise.
    call_command("boot", "--allow-empty")


@pytest.mark.django_db
def test_unknown_profile_fails_loud():
    with pytest.raises(CommandError, match="not found"):
        call_command("boot", "--profile", "no-such-profile")
