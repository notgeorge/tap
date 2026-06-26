"""Tests for tap_boot.checks.check_database_cache_table.

The check guards the latent ``tap_cache`` provisioning fault: when the default
cache backend is DatabaseCache, its ``LOCATION`` table must exist.

These exercise the check logic *directly* with ``override_settings`` rather
than relying on the table being absent — the dev DB already has ``tap_cache``
hand-created, and the test DB's presence is incidental, so we steer the
``LOCATION`` and ``BACKEND`` to drive each branch deterministically.
"""

from __future__ import annotations

import pytest
from django.db import DEFAULT_DB_ALIAS
from django.test import override_settings

from tap_boot.checks import DATABASE_CACHE_BACKEND, check_database_cache_table

_DB_CACHE = {
    "default": {"BACKEND": DATABASE_CACHE_BACKEND, "LOCATION": "tap_cache"},
}
_LOCMEM_CACHE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


@pytest.mark.spec("req-tap-health-bootcheck-1")
@pytest.mark.django_db
def test_error_when_cache_table_missing():
    """DatabaseCache + a non-existent table yields exactly one E001 error."""
    missing = {
        "default": {
            "BACKEND": DATABASE_CACHE_BACKEND,
            "LOCATION": "definitely_not_a_real_table",
        },
    }
    with override_settings(CACHES=missing):
        errors = check_database_cache_table(app_configs=None, databases=[DEFAULT_DB_ALIAS])
    assert len(errors) == 1
    assert errors[0].id == "tap_boot.E001"
    assert "createcachetable" in errors[0].hint


@pytest.mark.spec("req-tap-health-bootcheck-2")
@pytest.mark.django_db
def test_ok_when_cache_table_exists():
    """DatabaseCache pointed at an existing table produces no error.

    ``django_session`` always exists (sessions migration), so it stands in for
    a present cache table to exercise the table-found branch deterministically.
    """
    present = {
        "default": {"BACKEND": DATABASE_CACHE_BACKEND, "LOCATION": "django_session"},
    }
    with override_settings(CACHES=present):
        errors = check_database_cache_table(app_configs=None, databases=[DEFAULT_DB_ALIAS])
    assert errors == []


@pytest.mark.spec("req-tap-health-bootcheck-3")
def test_skips_non_database_cache_backend():
    """A non-DatabaseCache backend is irrelevant to this check — no error, no DB."""
    with override_settings(CACHES=_LOCMEM_CACHE):
        errors = check_database_cache_table(app_configs=None, databases=[DEFAULT_DB_ALIAS])
    assert errors == []


@pytest.mark.spec("req-tap-health-bootcheck-4")
def test_skips_when_database_not_available():
    """No permitted DB alias means the check must not introspect — it skips."""
    with override_settings(CACHES=_DB_CACHE):
        assert check_database_cache_table(app_configs=None, databases=None) == []
        assert check_database_cache_table(app_configs=None, databases=[]) == []
