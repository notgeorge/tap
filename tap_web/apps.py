"""TAP Web application configuration."""

from django.apps import AppConfig


class TapWebConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tap_web"
    verbose_name = "TAP Web"

    def ready(self) -> None:
        self._register_web_edge_constraints()

    def _register_web_edge_constraints(self) -> None:
        """Register default dimensions for tap_web edge types.

        Called directly (not via TapPluginConfig) because tap_web is a core
        app, not a third-party plugin. All tap_web edges carry tap.graph=web.
        """
        from tap_grid.constraints import register_edge_default_dimensions

        register_edge_default_dimensions("USES_PANEL", {"tap.graph": "web"})
        register_edge_default_dimensions("USES_LANDING_PAGE", {"tap.graph": "web"})
