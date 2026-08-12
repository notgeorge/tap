"""tap_cares application configuration."""

from django.apps import AppConfig


class TapCaresConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tap_cares"
    verbose_name = "TAP Cares"

    def ready(self) -> None:
        # Load runtime secrets from the configured mount root into
        # secret_registry. No-op when the root is missing or empty; fails
        # loud on malformed files or duplicate `scope:key` so an operator
        # notices before any capability runs.
        # See tap_cares/specs/spec-tap-cares-secrets.md.
        from django.conf import settings

        from tap_cares.secrets.loader import load_secrets

        load_secrets(settings.TAP_SECRETS_ROOT)

        # Register the secret-load system check. Importing only registers the
        # check function; it reads secret_load_report (populated just above)
        # when it runs under `manage.py check` / `runserver` — no DB access
        # here, so this is ready()-safe. See tap_cares/checks.py.
        from tap_cares import checks  # noqa: F401
        from tap_cares.health import probe_secrets

        # Register the secrets health probe from tap_cares's own boundary so the
        # dependency runs tap_cares -> tap_health (not core importing up into
        # tap_cares). See tap_cares/health.py and spec-tap-health-v0.md.
        from tap_health.registry import register_health_probe

        register_health_probe("secrets", probe_secrets, group="tap_cares", critical=True)

        # Register tap_cares-owned edge types. Plugins use the manifest path
        # (tap-plugin.toml + edges/*.edge.json); first-party apps register
        # programmatically through the same constraints registry.
        from tap_grid.constraints import register_edge_type_constraints

        register_edge_type_constraints(
            "HAS_COLLECTION_JOB",
            sources=[{"type": "collector"}],
            targets=[{"type": "collection_job"}],
        )
        # Scheduler edges — req-tap-cares-scheduler-edges.
        register_edge_type_constraints(
            "SCHEDULED_TARGET",
            sources=[{"type": "schedule"}],
            targets=[{"type": "collector"}],
        )
        register_edge_type_constraints(
            "HAS_FIRED",
            sources=[{"type": "schedule"}],
            targets=[{"type": "schedule_fire"}],
        )
        register_edge_type_constraints(
            "TRIGGERED_JOB",
            sources=[{"type": "schedule_fire"}],
            targets=[{"type": "collection_job"}],
        )

        # Import the Steady Queue task module so its @recurring scheduler
        # tick is registered with steady_queue at startup. Steady Queue's
        # Configuration.RecurringTask.discover() picks up @recurring
        # callsites from imported modules; importing here makes the
        # scheduler tick discoverable in every process (web and supervisor).
        #
        # Guarded on backend: under tests we configure ImmediateBackend
        # (tap/test_settings.py), where @task() returns a plain Django Task
        # that lacks the .serialize() method steady_queue's @recurring
        # wrapper expects. Skipping the import there avoids an import-time
        # AttributeError and is correct anyway — tests don't run the
        # steady_queue supervisor, so a recurring task registration would
        # have no effect.
        from django.conf import settings

        backend_path = settings.TASKS.get("default", {}).get("BACKEND", "")
        if backend_path == "steady_queue.backend.SteadyQueueBackend":
            from tap_cares import task_backend  # noqa: F401
