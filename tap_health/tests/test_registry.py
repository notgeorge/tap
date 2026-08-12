"""Tests for the health-probe registry (req-tap-health-probe-registry)."""

from __future__ import annotations

import pytest
from django.core.exceptions import ImproperlyConfigured

from tap_health.registry import HealthProbe, register_health_probe
from tap_health.results import ProbeResult
from tap_health.selection import READINESS


def _ok() -> ProbeResult:
    return ProbeResult.healthy()


@pytest.mark.spec("req-tap-health-probe-registry-1")
def test_register_and_retrieve(isolated_probe_registry):
    register_health_probe("alpha", _ok, group="core", critical=True, requires=("cap.read",), sets=(READINESS,))
    stored = isolated_probe_registry.get("alpha")
    assert isinstance(stored, HealthProbe)
    assert stored.name == "alpha"
    assert stored.group == "core"
    assert stored.critical is True
    assert stored.requires == ("cap.read",)


@pytest.mark.spec("req-tap-health-probe-registry-1")
def test_duplicate_name_raises(isolated_probe_registry):
    register_health_probe("dup", _ok, sets=(READINESS,))
    with pytest.raises(ImproperlyConfigured):
        register_health_probe("dup", _ok, sets=(READINESS,))


@pytest.mark.spec("req-tap-health-probe-registry-8")
def test_defaults(isolated_probe_registry):
    register_health_probe("bare", _ok, sets=(READINESS,))
    stored = isolated_probe_registry.get("bare")
    assert stored.group == "core"
    assert stored.critical is False
    assert stored.requires == ()
