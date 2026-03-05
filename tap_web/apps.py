"""TAP Web application configuration."""

from typing import Any

from django.apps import AppConfig


class TapWebConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tap_web"
    verbose_name = "TAP Web"

    # Same format as TapPluginConfig.edge_types.
    # Processed by register_edge_types_from_list() on startup.
    edge_types: list[dict[str, Any]] = [
        {
            "slug": "USES_PANEL",
            "display_name": "Uses Panel",
            "description": "Page embeds a panel.",
            "sources": [{"type": "page"}],
            "targets": [{"type": "panel"}],
            "default_dimensions": {"tap.graph": "web"},
        },
        {
            "slug": "USES_LANDING_PAGE",
            "display_name": "Uses Landing Page",
            "description": "Landing page designates a target page for the root URL.",
            "sources": [{"type": "landing_page"}],
            "targets": [{"type": "page"}],
            "default_dimensions": {"tap.graph": "web"},
        },
    ]

    def ready(self) -> None:
        from tap_plugins.base import register_edge_types_from_list

        register_edge_types_from_list(self.edge_types)
