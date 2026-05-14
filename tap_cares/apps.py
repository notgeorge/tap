"""tap_cares application configuration."""

from django.apps import AppConfig


class TapCaresConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tap_cares"
    verbose_name = "TAP Cares"

    def ready(self) -> None:
        # Register tap_cares-owned edge types. Plugins use the manifest path
        # (tap-plugin.toml + edges/*.edge.json); first-party apps register
        # programmatically through the same constraints registry.
        from tap_grid.constraints import register_edge_type_constraints

        register_edge_type_constraints(
            "HAS_JOB",
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
