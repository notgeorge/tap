"""Tests for the probe selection layer (req-tap-health-selection).

Selection is what makes membership — not criticality — decide whether a probe
can sink a given gate, so these tests pin the two behaviours that carry that
weight: a non-selected probe does not *execute*, and an empty selection reports
`unknown` rather than a green light earned by checking nothing.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ImproperlyConfigured

from tap_health.registry import register_health_probe
from tap_health.results import ProbeResult, ProbeStatus
from tap_health.selection import ALL, LIVENESS, READINESS, resolve_selection, selects
from tap_health.service import run_health


@pytest.mark.spec("req-tap-health-selection-1")
def test_sets_declaration_is_mandatory(isolated_probe_registry):
    with pytest.raises(ImproperlyConfigured, match="declared no selection sets"):
        register_health_probe("undeclared", ProbeResult.healthy, sets=())


@pytest.mark.spec("req-tap-health-selection-1")
def test_unknown_set_is_rejected_at_registration(isolated_probe_registry):
    # Closed vocabulary: plugin-defined sets are backlogged, so an unrecognised
    # tag is a loud startup error, never a silently-ignored string.
    with pytest.raises(ImproperlyConfigured, match="unknown selection set"):
        register_health_probe("typo", ProbeResult.healthy, sets=("readyness",))


@pytest.mark.spec("req-tap-health-selection-1")
def test_reserved_all_cannot_be_declared(isolated_probe_registry):
    with pytest.raises(ImproperlyConfigured, match="reserved set"):
        register_health_probe("greedy", ProbeResult.healthy, sets=(ALL,))


@pytest.mark.spec("req-tap-health-selection-2")
def test_non_selected_probe_does_not_execute(isolated_probe_registry):
    """The load-bearing property: liveness must not run dependency probes.

    Filtering happens *before* execution, so a readiness-only probe cannot touch
    the database during a liveness run — the mechanism that stops a DB outage
    from being reported as a reason to restart the process.
    """
    calls: list[str] = []

    def readiness_only() -> ProbeResult:
        calls.append("readiness_only")
        return ProbeResult.healthy()

    def in_both() -> ProbeResult:
        calls.append("in_both")
        return ProbeResult.healthy()

    register_health_probe("readiness-only", readiness_only, sets=(READINESS,), critical=True)
    register_health_probe("in-both", in_both, sets=(READINESS, LIVENESS))

    run_health(selection=LIVENESS)
    assert calls == ["in_both"]


@pytest.mark.spec("req-tap-health-selection-2")
def test_critical_failure_outside_the_selection_does_not_sink_the_verdict(isolated_probe_registry):
    register_health_probe(
        "broken-dependency",
        lambda: ProbeResult.unhealthy("db.query_failed"),
        sets=(READINESS,),
        critical=True,
    )
    register_health_probe("alive", ProbeResult.healthy, sets=(LIVENESS,))

    assert run_health(selection=READINESS).status is ProbeStatus.UNHEALTHY
    liveness = run_health(selection=LIVENESS)
    assert liveness.status is ProbeStatus.HEALTHY
    assert liveness.ok is True


@pytest.mark.spec("req-tap-health-selection-2")
def test_all_runs_every_probe_regardless_of_declaration(isolated_probe_registry):
    register_health_probe("r", ProbeResult.healthy, sets=(READINESS,))
    register_health_probe("l", ProbeResult.healthy, sets=(LIVENESS,))
    report = run_health(selection=ALL)
    assert {o.name for o in report.outcomes} == {"r", "l"}


@pytest.mark.spec("req-tap-health-selection-3")
def test_empty_selection_is_unknown_not_healthy(isolated_probe_registry):
    # Nothing answered the question. Reporting `healthy` would be a claim no probe
    # supports (Law 1); `ok` stays True so an orchestrator does not act on it.
    register_health_probe("r", ProbeResult.healthy, sets=(READINESS,))
    report = run_health(selection=LIVENESS)
    assert report.outcomes == ()
    assert report.status is ProbeStatus.UNKNOWN
    assert report.ok is True


@pytest.mark.spec("req-tap-health-selection-2")
def test_report_carries_the_selection_it_answered(isolated_probe_registry):
    register_health_probe("r", ProbeResult.healthy, sets=(READINESS,))
    assert run_health(selection=READINESS).full()["selection"] == "readiness"


@pytest.mark.spec("req-tap-health-selection-4")
def test_unknown_selection_names_the_valid_options():
    with pytest.raises(ValueError, match="liveness, readiness, all"):
        resolve_selection("prod")


@pytest.mark.spec("req-tap-health-selection-2")
def test_selects_predicate():
    assert selects((READINESS,), READINESS) is True
    assert selects((READINESS,), LIVENESS) is False
    # `all` is implicit membership — every probe is in it without declaring it.
    assert selects((READINESS,), ALL) is True
    assert selects((), ALL) is True
