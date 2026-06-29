"""Projection leak-test — the load-bearing security boundary.

req-tap-health-exposure-3 / req-tap-health-service-4 (spec-tap-health-v0.md).

The whole "collect rich context, project per caller" design rests on the coarse
projection actually stripping the rich fields. These tests prove it: a probe
result loaded with secret-adjacent `detail` / `reasoning` / `context` / `code`
must appear in `full()` and must NOT appear anywhere in `scorecard()`.
"""

from __future__ import annotations

import json

import pytest

from tap_health.results import HealthReport, ProbeOutcome, ProbeResult

_SENSITIVE = "/run/tap-secrets/aws/sam.secret.json"


def _report_with_rich_context() -> HealthReport:
    result = ProbeResult.unhealthy(
        "secrets.required_for_boot_failed",
        detail="1 required-for-boot secret failed to load",
        reasoning=f"basename mismatch on {_SENSITIVE}",
        context={"failed": ["aws:boto_collector"], "path": _SENSITIVE},
    )
    return HealthReport(outcomes=(ProbeOutcome("secrets", "tap_cares", True, result),))


@pytest.mark.spec("req-tap-health-service-3")
def test_full_carries_rich_fields():
    full = _report_with_rich_context().full()
    entry = full["checks"]["secrets"]
    assert entry["status"] == "unhealthy"
    assert entry["critical"] is True
    assert entry["group"] == "tap_cares"
    assert entry["code"] == "secrets.required_for_boot_failed"
    assert entry["detail"]
    assert entry["reasoning"]
    assert entry["context"]["path"] == _SENSITIVE


@pytest.mark.spec("req-tap-health-exposure-3")
def test_scorecard_strips_all_rich_fields():
    report = _report_with_rich_context()
    card = report.scorecard()
    entry = card["checks"]["secrets"]
    # Only status survives — per probe.
    assert entry == {"status": "unhealthy"}
    assert card["status"] == "unhealthy"  # overall verdict preserved
    # The sensitive token must not appear ANYWHERE in the serialized scorecard.
    assert _SENSITIVE not in json.dumps(card)
    for banned in ("detail", "reasoning", "context", "code", "critical", "group"):
        assert banned not in json.dumps(card)


@pytest.mark.spec("req-tap-health-probes-3")
def test_unknown_status_is_present_in_both_projections():
    result = ProbeResult.unknown("queue.tables_missing", detail="steady_queue tables not found")
    report = HealthReport(outcomes=(ProbeOutcome("queue", "core", False, result),))
    assert report.full()["checks"]["queue"]["status"] == "unknown"
    assert report.scorecard()["checks"]["queue"]["status"] == "unknown"


@pytest.mark.spec("req-tap-health-service-3")
def test_non_healthy_result_requires_a_code():
    from tap_health.results import ProbeStatus

    # The machine `code` is the contract for any non-healthy result (Law 4) —
    # constructing one without it is rejected at the source.
    for bad in (ProbeStatus.DEGRADED, ProbeStatus.UNHEALTHY, ProbeStatus.UNKNOWN):
        with pytest.raises(ValueError, match="requires a stable `code`"):
            ProbeResult(status=bad)
    # A healthy result needs no code.
    assert ProbeResult(status=ProbeStatus.HEALTHY).code is None
