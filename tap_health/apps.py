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
        from tap_health.probes import probe_cache, probe_db, probe_queue
        from tap_health.registry import register_health_probe

        register_health_probe("db", probe_db, group="core", critical=True)
        register_health_probe("cache", probe_cache, group="core", critical=True)
        register_health_probe("queue", probe_queue, group="core", critical=False)

        # Register the boot-time provisioning system check. Importing only
        # registers the check function; the DB access happens later when the
        # check runs under `migrate` / `check --database`. See tap_health/checks.py.
        from tap_health import checks  # noqa: F401
