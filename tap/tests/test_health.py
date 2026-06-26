"""Tests for the /healthz real-backend health endpoint (tap/health.py).

Covers the happy path (200 + healthy, all probes reported) and the
critical-failure path (a broken cache probe → 503 + unhealthy). The cache
probe is the one that catches the demo-day ``tap_cache`` fault, so its failure
mode is asserted explicitly.

Note: the test suite runs LocMemCache (tap/test_settings.py), so the cache
round-trip genuinely succeeds here; we simulate a missing-backend failure by
patching ``cache.set`` to raise, which mirrors the production
``ProgrammingError: relation "tap_cache" does not exist``.
"""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse


@pytest.mark.spec(
    "req-tap-health-endpoint-2", "req-tap-health-endpoint-3", "req-tap-health-probes-1", "req-tap-health-probes-4"
)
@pytest.mark.django_db
def test_healthz_all_healthy_returns_200():
    """All critical backends up → 200, status healthy, every probe reported."""
    response = Client().get(reverse("healthz"))
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["checks"]["db"]["status"] == "healthy"
    assert payload["checks"]["cache"]["status"] == "healthy"
    # queue is non-critical; healthy or unknown, never absent.
    assert payload["checks"]["queue"]["status"] in {"healthy", "unknown"}


@pytest.mark.spec("req-tap-health-endpoint-3", "req-tap-health-probes-2", "req-tap-health-probes-5")
@pytest.mark.django_db
def test_healthz_unhealthy_when_cache_broken(monkeypatch):
    """A broken cache backend (the tap_cache fault) → 503 + unhealthy cache probe."""

    def _boom(*args, **kwargs):
        raise RuntimeError('relation "tap_cache" does not exist')

    monkeypatch.setattr("tap.health.cache.set", _boom)
    response = Client().get(reverse("healthz"))
    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "unhealthy"
    assert payload["checks"]["cache"]["status"] == "unhealthy"
    assert "tap_cache" in payload["checks"]["cache"]["detail"]
    # db stays healthy — probes are independent.
    assert payload["checks"]["db"]["status"] == "healthy"


@pytest.mark.spec("req-tap-health-unauth-1")
@pytest.mark.django_db
def test_healthz_is_login_exempt():
    """The probe answers without authentication (anonymous client, no redirect)."""
    response = Client().get(reverse("healthz"))
    assert response.status_code in {200, 503}  # answered, not a 302 to login.
