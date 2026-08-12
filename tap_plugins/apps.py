from django.apps import AppConfig


class TapPluginsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tap_plugins"
    verbose_name = "TAP Plugins"

    def ready(self) -> None:
        # Register the plugins-loaded probe from tap_plugins' own boundary so the
        # dependency runs tap_plugins -> tap_health (req-tap-health-probe-registry-3).
        # Registration only appends a callable — no DB, no env read here; the probe
        # body runs later at run_health() time.
        from tap_health.registry import register_health_probe
        from tap_health.selection import READINESS
        from tap_plugins.health import probe_plugins_loaded

        # Critical: a process running the wrong plugin set can register a type whose
        # table was never migrated — the failure mode behind the plugin-loading race.
        register_health_probe(
            "plugins-loaded",
            probe_plugins_loaded,
            sets=(READINESS,),
            group="tap_plugins",
            critical=True,
        )
