"""tap_viz Django app configuration."""

from django.apps import AppConfig


class TapVizConfig(AppConfig):
    """Configuration for the tap_viz visualization app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "tap_viz"
    verbose_name = "TAP Visualization"

    def ready(self) -> None:
        """Register built-in panel types and search runners."""
        from tap_grid.registry import register_search_runner
        from tap_viz.panels.graph_panel import GraphPanelType, hub_and_spoke_runner
        from tap_web.registry import panel_type_registry

        panel_type_registry.register("graph", GraphPanelType)
        register_search_runner("hub-and-spoke", hub_and_spoke_runner)
