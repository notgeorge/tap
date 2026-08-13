"""Tests for `manage.py health` (req-tap-health-exposure-2, req-tap-health-selection)."""

from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command

from tap_health.registry import register_health_probe
from tap_health.results import ProbeResult
from tap_health.selection import LIVENESS, READINESS


def _run(*args: str) -> tuple[str, str, int]:
    """Call the command, returning (stdout, stderr, exit_code)."""
    out, err = StringIO(), StringIO()
    code = 0
    try:
        call_command("health", *args, stdout=out, stderr=err)
    except SystemExit as exc:
        code = int(exc.code or 0)
    return out.getvalue(), err.getvalue(), code


@pytest.mark.spec("req-tap-health-exposure-2")
def test_exit_zero_when_healthy(isolated_probe_registry):
    register_health_probe("a", ProbeResult.healthy, critical=True, sets=(READINESS,))
    output, _, code = _run("--set", "readiness")
    assert code == 0
    assert "healthy" in output


@pytest.mark.spec("req-tap-health-exposure-2")
def test_exit_nonzero_on_critical_unhealthy(isolated_probe_registry):
    register_health_probe("crit", lambda: ProbeResult.unhealthy("x.broke"), critical=True, sets=(READINESS,))
    output, _, code = _run("--set", "readiness")
    assert code == 1
    assert "unhealthy" in output


@pytest.mark.spec("req-tap-health-exposure-2")
def test_json_is_full_projection(isolated_probe_registry):
    register_health_probe(
        "crit",
        lambda: ProbeResult.unhealthy("x.broke", detail="boom", context={"k": "v"}),
        group="core",
        critical=True,
        sets=(READINESS,),
    )
    output, _, code = _run("--set", "readiness", "--json")
    assert code == 1
    payload = json.loads(output)
    entry = payload["checks"]["crit"]
    assert entry["code"] == "x.broke"  # machine code present in CLI (trusted/full)
    assert entry["context"] == {"k": "v"}
    assert payload["status"] == "unhealthy"
    assert payload["selection"] == "readiness"  # the verdict names the question it answers


@pytest.mark.spec("req-tap-health-selection-4")
def test_missing_set_is_a_usage_error_listing_the_options(isolated_probe_registry):
    # Exit 2, not 1: a forgotten flag must be distinguishable from a sick instance,
    # or a caller chases a phantom outage.
    register_health_probe("a", ProbeResult.healthy, critical=True, sets=(READINESS,))
    stdout, stderr, code = _run()
    assert code == 2
    assert "--set is required" in stderr
    # The refusal teaches the vocabulary rather than leaving the caller to guess.
    for name in ("liveness", "readiness", "all"):
        assert name in stderr
    assert stdout == ""


@pytest.mark.spec("req-tap-health-selection-4")
def test_unknown_set_is_a_usage_error(isolated_probe_registry):
    # Same exit code and message shape as a missing flag. Validated in the command
    # rather than by argparse `choices=`, because Django's CommandParser raises
    # CommandError (exit 1) instead of exiting 2 under call_command — which would
    # make the exit code depend on how the command was invoked.
    stdout, stderr, code = _run("--set", "nonsense")
    assert code == 2
    assert "Unknown selection 'nonsense'" in stderr
    for name in ("liveness", "readiness", "all"):
        assert name in stderr
    assert stdout == ""


@pytest.mark.spec("req-tap-health-selection-5")
def test_list_sets_json_describes_the_vocabulary(isolated_probe_registry):
    register_health_probe("ready-only", ProbeResult.healthy, critical=True, sets=(READINESS,))
    register_health_probe("both", ProbeResult.healthy, sets=(READINESS, LIVENESS))
    output, _, code = _run("--list-sets", "--json")
    assert code == 0
    payload = {entry["name"]: entry for entry in json.loads(output)}
    assert set(payload) == {"liveness", "readiness", "all"}
    assert {p["name"] for p in payload["readiness"]["probes"]} == {"ready-only", "both"}
    assert {p["name"] for p in payload["liveness"]["probes"]} == {"both"}
    assert {p["name"] for p in payload["all"]["probes"]} == {"ready-only", "both"}
    # Criticality travels with membership so a consumer can see which probes bite.
    assert [p["critical"] for p in payload["readiness"]["probes"] if p["name"] == "ready-only"] == [True]
    assert payload["liveness"]["description"]


@pytest.mark.spec("req-tap-health-selection-5")
def test_list_sets_human_readable(isolated_probe_registry):
    register_health_probe("a", ProbeResult.healthy, sets=(READINESS,))
    output, _, code = _run("--list-sets")
    assert code == 0
    assert "readiness" in output
    assert "a" in output
    # liveness is empty by design and says so rather than looking populated.
    assert "(no probes)" in output
