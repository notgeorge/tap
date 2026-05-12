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
