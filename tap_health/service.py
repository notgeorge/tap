"""The health service entrypoint — `run_health()`.

req-tap-health-service (spec-tap-health-v0.md).

`run_health()` is a **pure producer**: it takes no caller and no actor, runs
every registered probe, and returns a `HealthReport`. The v0 probes resolve no
actor, so the liveness path stays runnable when auth/DB/grid is broken
(req-tap-health-probe-actor). Projection and any caller authorization are a
*surface* concern (the CLI / a future API), never parameters here.

Per-probe execution is isolated: a probe that raises is reported as an
`unhealthy` outcome with a generic code, never propagated — one probe can
neither crash the run nor stop the others (req-tap-health-probe-registry-6).
"""

from __future__ import annotations

import logging

from tap_health.registry import HealthProbe, health_probe_registry
from tap_health.results import HealthReport, ProbeOutcome, ProbeResult

logger = logging.getLogger(__name__)

PROBE_RAISED_CODE = "probe.raised"


def _run_one(entry: HealthProbe) -> ProbeOutcome:
    try:
        result = entry.probe()
    except Exception as exc:  # noqa: BLE001 — the runner reports, never propagates.
        logger.warning("[6880] health: probe %s raised: %s", entry.name, exc)
        result = ProbeResult.unhealthy(PROBE_RAISED_CODE, detail=f"probe raised: {exc}")
    return ProbeOutcome(name=entry.name, group=entry.group, critical=entry.critical, result=result)


def run_health(*, selection: object = None) -> HealthReport:
    """Run every registered probe and return a `HealthReport`.

    Args:
        selection: Reserved future hook for running a subset (a group / a
            liveness-vs-readiness set). Ignored in v0 — all probes run.

    Returns:
        A `HealthReport`. Project it with `.full()` (trusted) or `.scorecard()`
        (coarse) at the consuming surface.
    """
    del selection  # v0 runs all probes; selection is a named future hook.
    # Report in deterministic (group, name) order so a group's probes cluster
    # (req-tap-health-probe-registry-8). The registry keys() sorts by name only.
    probes = sorted(
        (health_probe_registry.get(name) for name in health_probe_registry.keys()),
        key=lambda p: (p.group, p.name),
    )
    outcomes = tuple(_run_one(p) for p in probes)
    report = HealthReport(outcomes=outcomes)
    logger.info("[af5e] health: ran %d probe(s); overall=%s", len(outcomes), report.status.value)
    return report


__all__ = ["run_health", "PROBE_RAISED_CODE"]
