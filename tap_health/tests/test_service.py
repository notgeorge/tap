"""Tests for run_health() — aggregation, isolation, actor-free (req-tap-health-service)."""

from __future__ import annotations

import pytest

from tap_health.registry import register_health_probe
from tap_health.results import ProbeResult, ProbeStatus
from tap_health.selection import READINESS
from tap_health.service import PROBE_RAISED_CODE, run_health


@pytest.mark.spec("req-tap-health-probe-registry-5")
def test_healthy_when_all_healthy(isolated_probe_registry):
    register_health_probe("a", ProbeResult.healthy, critical=True, sets=(READINESS,))
    register_health_probe("b", ProbeResult.healthy, sets=(READINESS,))
    report = run_health(selection="all")
    assert report.status is ProbeStatus.HEALTHY
    assert report.ok is True


@pytest.mark.spec("req-tap-health-probe-registry-5")
def test_critical_unhealthy_flips_overall(isolated_probe_registry):
    register_health_probe("crit", lambda: ProbeResult.unhealthy("x.broke"), critical=True, sets=(READINESS,))
    register_health_probe("ok", ProbeResult.healthy, sets=(READINESS,))
    report = run_health(selection="all")
    assert report.status is ProbeStatus.UNHEALTHY
    assert report.ok is False


@pytest.mark.spec("req-tap-health-probe-registry-5")
def test_noncritical_unhealthy_is_degraded_not_hidden(isolated_probe_registry):
    # A non-critical unhealthy must not flip overall to UNHEALTHY (stays non-blocking),
    # but must surface as DEGRADED — never hidden as healthy (Law 1, Preserve Truth).
    register_health_probe("soft", lambda: ProbeResult.unhealthy("x.soft"), critical=False, sets=(READINESS,))
    register_health_probe("ok", ProbeResult.healthy, critical=True, sets=(READINESS,))
    report = run_health(selection="all")
    assert report.status is ProbeStatus.DEGRADED
    assert report.ok is True
    assert report.full()["checks"]["soft"]["status"] == "unhealthy"


@pytest.mark.spec("req-tap-health-probe-registry-5")
def test_degraded_when_any_degraded_no_critical_unhealthy(isolated_probe_registry):
    register_health_probe("d", lambda: ProbeResult.degraded("x.deg"), sets=(READINESS,))
    register_health_probe("ok", ProbeResult.healthy, critical=True, sets=(READINESS,))
    assert run_health(selection="all").status is ProbeStatus.DEGRADED


@pytest.mark.spec("req-tap-health-probes-3")
def test_unknown_visible_but_does_not_flip(isolated_probe_registry):
    register_health_probe("u", lambda: ProbeResult.unknown("x.unknown"), critical=False, sets=(READINESS,))
    register_health_probe("ok", ProbeResult.healthy, critical=True, sets=(READINESS,))
    report = run_health(selection="all")
    assert report.status is ProbeStatus.HEALTHY  # unknown never flips
    assert report.full()["checks"]["u"]["status"] == "unknown"  # but never dropped


@pytest.mark.spec("req-tap-health-probe-registry-6")
def test_probe_exception_is_isolated(isolated_probe_registry):
    def boom() -> ProbeResult:
        raise RuntimeError("kaboom")

    register_health_probe("boom", boom, critical=True, sets=(READINESS,))
    register_health_probe("fine", ProbeResult.healthy, sets=(READINESS,))
    report = run_health(selection="all")  # must not raise
    checks = report.full()["checks"]
    assert checks["boom"]["status"] == "unhealthy"
    assert checks["boom"]["code"] == PROBE_RAISED_CODE
    assert checks["fine"]["status"] == "healthy"  # other probe still ran


@pytest.mark.spec("req-tap-health-service-5")
def test_run_health_takes_no_caller(isolated_probe_registry):
    register_health_probe("a", ProbeResult.healthy, sets=(READINESS,))
    # Pure producer: no positional caller/actor argument exists. `selection` is
    # keyword-only, so a positional argument of any kind is a TypeError.
    with pytest.raises(TypeError):
        run_health(object())  # type: ignore[call-arg,arg-type]
