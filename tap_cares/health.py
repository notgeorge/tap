"""tap_cares health probe — the secret-load outcome.

req-tap-cares-secrets-resilient-load, req-tap-health-service-2
(spec-tap-health-v0.md, spec-tap-cares-secrets.md).

Registered from `tap_cares`'s own `ready()` into the `tap_health` registry, so
the dependency runs the right way (tap_cares → tap_health), not core importing
up into tap_cares. The loader is resilient (a bad secret file is recorded, not
raised), and this probe is how that outcome surfaces on a running instance.

It is `critical=True` but chooses its own status: a `required_for_boot` failure
is `unhealthy` (flips the overall verdict), any other load failure is
`degraded` (visible, non-blocking). The failing qualified names ride in the
structured `context`, which the coarse projection strips
(req-tap-health-exposure-3).
"""

from __future__ import annotations

from tap_health.results import ProbeResult


def probe_secrets() -> ProbeResult:
    """Report the startup secret-load outcome from `secret_load_report`."""
    from tap_cares.secrets.registry import secret_load_report

    blocking = secret_load_report.blocking
    degraded = secret_load_report.degraded
    if blocking:
        names = [f.qualified or f.path for f in blocking]
        return ProbeResult.unhealthy(
            "secrets.required_for_boot_failed",
            detail=f"{len(blocking)} required-for-boot secret(s) failed to load",
            context={"failed": names},
        )
    if degraded:
        names = [f.qualified or f.path for f in degraded]
        return ProbeResult.degraded(
            "secrets.load_failed",
            detail=f"{len(degraded)} secret(s) failed to load (non-blocking)",
            context={"failed": names},
        )
    return ProbeResult.healthy()


__all__ = ["probe_secrets"]
