"""Behavior tests for the migration-readiness probe (req-tap-health-probes).

The other probes (db/cache/queue) are trivial backend touches exercised via the
service tests; `probe_migrations` carries real branching (plan empty vs pending),
so it gets direct coverage — it is the probe that stops a readiness consumer from
acting on a half-applied schema (the plugin-loading flake).
"""

from __future__ import annotations

import pytest

from tap_health.probes import probe_migrations
from tap_health.results import ProbeStatus


@pytest.mark.django_db
def test_probe_migrations_healthy_when_schema_current():
    # pytest-django applies every migration to the test DB, so the plan is empty.
    result = probe_migrations()
    assert result.status is ProbeStatus.HEALTHY
    assert result.code is None


@pytest.mark.django_db
def test_probe_migrations_unhealthy_when_pending(monkeypatch):
    # Simulate migrate mid-flight: a non-empty plan means unapplied migrations remain.
    monkeypatch.setattr(
        "django.db.migrations.executor.MigrationExecutor.migration_plan",
        lambda self, targets: [("dummy.0002", False)],
    )
    result = probe_migrations()
    assert result.status is ProbeStatus.UNHEALTHY
    assert result.code == "migrations.pending"


@pytest.mark.django_db
def test_probe_migrations_reports_check_failure_without_raising(monkeypatch):
    def _boom(self, targets):
        raise RuntimeError("recorder unreachable")

    monkeypatch.setattr("django.db.migrations.executor.MigrationExecutor.migration_plan", _boom)
    result = probe_migrations()  # never raises — probes report, never raise
    assert result.status is ProbeStatus.UNHEALTHY
    assert result.code == "migrations.check_failed"


def test_probe_migrations_registered_as_critical_core_probe():
    # Registration happens in TapHealthConfig.ready(); the probe must be critical so a
    # stack with pending migrations reports overall-unhealthy (the readiness gate).
    from tap_health.registry import health_probe_registry

    by_name = {name: health_probe_registry.get(name) for name in health_probe_registry.keys()}
    assert "migrations" in by_name, "migrations probe not registered"
    assert by_name["migrations"].critical is True
    assert by_name["migrations"].group == "core"
