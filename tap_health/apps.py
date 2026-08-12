"""tap_health application configuration."""

from __future__ import annotations

from django.apps import AppConfig


class TapHealthConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tap_health"
    verbose_name = "TAP Health"

    def ready(self) -> None:
        # Register the core (platform) probes. Registration only appends a
        # callable to the registry — no DB access — so this is ready()-safe;
        # each probe body runs later, at run_health() time.
        from tap_health.probes import probe_cache, probe_db, probe_migrations, probe_queue
        from tap_health.registry import register_health_probe
        from tap_health.selection import READINESS

        # Every core probe checks a DEPENDENCY, and no dependency failure is fixed
        # by restarting this process — so none of them join `liveness`, which would
        # turn a database outage into a restart loop (req-tap-health-selection).
        register_health_probe("db", probe_db, sets=(READINESS,), group="core", critical=True)
        register_health_probe("cache", probe_cache, sets=(READINESS,), group="core", critical=True)
        # Critical: the DB can be reachable while migrate is mid-flight (createcachetable
        # precedes migrate), so this is what stops a readiness consumer from acting on a
        # half-applied schema — the plugin-loading flake's real root.
        register_health_probe("migrations", probe_migrations, sets=(READINESS,), group="core", critical=True)
        # In readiness but NOT critical: a missing queue table is reported (never
        # hidden) without failing a gate — set membership and criticality are
        # independent axes.
        register_health_probe("queue", probe_queue, sets=(READINESS,), group="core", critical=False)

        # Register the boot-time provisioning system check. Importing only
        # registers the check function; the DB access happens later when the
        # check runs under `migrate` / `check --database`. See tap_health/checks.py.
        from tap_health import checks  # noqa: F401
