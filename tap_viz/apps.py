"""tap_viz Django app configuration."""

from django.apps import AppConfig


class TapVizConfig(AppConfig):
    """Configuration for the tap_viz visualization app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "tap_viz"
    verbose_name = "TAP Visualization"

    # Top-level URL prefix this app mounts (tap/urls.py), reserved against Page
    # slugs. Collected by tap_web.reserved.get_reserved_url_prefixes().
    reserved_url_prefixes: list[str] = ["/viz"]

    def ready(self) -> None:
        """Register built-in panel types."""
        from tap_viz.panels.graph_panel import GraphPanelType
        from tap_web.registry import panel_type_registry

        panel_type_registry.register("graph", GraphPanelType)
