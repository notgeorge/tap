"""Tests for the plugins-loaded probe (req-tap-health-probes-9).

The probe compares DESIRED (the authoritative resolver) against RUNTIME-LOADED
(the Django app registry) — the check whose absence let a process silently run a
different plugin set than the one it was told to run.
"""

from __future__ import annotations

from unittest import mock

import pytest

from tap_health.results import ProbeStatus
from tap_plugins.health import _app_module, probe_plugins_loaded


@pytest.mark.spec("req-tap-health-probes-9")
def test_healthy_when_every_declared_plugin_is_loaded():
    # tap_grid is a real loaded app: declaring it as desired must read as loaded.
    with mock.patch("tap.preboot.resolved_plugin_app_configs", return_value=["tap_grid"]):
        result = probe_plugins_loaded()
    assert result.status is ProbeStatus.HEALTHY
    assert result.context["desired_count"] == 1


@pytest.mark.spec("req-tap-health-probes-9")
def test_appconfig_path_form_resolves_to_its_app_module():
    # The resolver yields AppConfig paths; the registry keys on the app module.
    # Comparing the two forms naively would report every plugin as missing.
    with mock.patch("tap.preboot.resolved_plugin_app_configs", return_value=["tap_grid.apps.TapGridConfig"]):
        result = probe_plugins_loaded()
    assert result.status is ProbeStatus.HEALTHY


@pytest.mark.spec("req-tap-health-probes-9")
def test_declared_but_unloaded_plugin_is_unhealthy():
    with mock.patch("tap.preboot.resolved_plugin_app_configs", return_value=["tap_plugin.ghost"]):
        result = probe_plugins_loaded()
    assert result.status is ProbeStatus.UNHEALTHY
    assert result.code == "plugins.not_loaded"
    assert result.context["missing"] == ["tap_plugin.ghost"]


@pytest.mark.spec("req-tap-health-probes-9")
def test_unresolvable_plugin_set_is_unknown_not_unhealthy():
    # Not knowing the desired set is a different claim from knowing it is wrong.
    with mock.patch("tap.preboot.resolved_plugin_app_configs", side_effect=OSError("no such file")):
        result = probe_plugins_loaded()
    assert result.status is ProbeStatus.UNKNOWN
    assert result.code == "plugins.unresolvable"


@pytest.mark.spec("req-tap-health-probes-9")
def test_app_module_extraction():
    assert _app_module("pkg.apps.FooConfig") == "pkg"
    assert _app_module("pkg") == "pkg"
    assert _app_module("a.b.apps.C") == "a.b"
    # Not an AppConfig path — a two-segment module must survive intact.
    assert _app_module("a.b") == "a.b"
