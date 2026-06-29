"""Tests for `manage.py health` (req-tap-health-exposure-2)."""

from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command

from tap_health.registry import register_health_probe
from tap_health.results import ProbeResult


def _run(*args: str) -> tuple[str, int]:
    """Call the command, returning (stdout, exit_code). Exit 0 unless SystemExit."""
    out = StringIO()
    code = 0
    try:
        call_command("health", *args, stdout=out)
    except SystemExit as exc:
        code = int(exc.code or 0)
    return out.getvalue(), code


@pytest.mark.spec("req-tap-health-exposure-2")
def test_exit_zero_when_healthy(isolated_probe_registry):
    register_health_probe("a", ProbeResult.healthy, critical=True)
    output, code = _run()
    assert code == 0
    assert "healthy" in output


@pytest.mark.spec("req-tap-health-exposure-2")
def test_exit_nonzero_on_critical_unhealthy(isolated_probe_registry):
    register_health_probe("crit", lambda: ProbeResult.unhealthy("x.broke"), critical=True)
    output, code = _run()
    assert code == 1
    assert "unhealthy" in output


@pytest.mark.spec("req-tap-health-exposure-2")
def test_json_is_full_projection(isolated_probe_registry):
    register_health_probe(
        "crit",
        lambda: ProbeResult.unhealthy("x.broke", detail="boom", context={"k": "v"}),
        group="core",
        critical=True,
    )
    output, code = _run("--json")
    assert code == 1
    payload = json.loads(output)
    entry = payload["checks"]["crit"]
    assert entry["code"] == "x.broke"  # machine code present in CLI (trusted/full)
    assert entry["context"] == {"k": "v"}
    assert payload["status"] == "unhealthy"
