"""TAP Web application configuration."""

from typing import Any

from django.apps import AppConfig


class TapWebConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tap_web"
    verbose_name = "TAP Web"

    # Slug prefixes blocked for Page objects (req-web-page-slug-sanitize.sec).
    reserved_slugs: list[str] = ["/admin", "/api", "/panel"]

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
            # req-web-page-plink: panel-id is required; variable_map is optional.
            "property_schema": {
                "type": "object",
                "required": ["panel-id"],
                "properties": {
                    "panel-id": {
                        "type": "string",
                        "pattern": "^[a-z][a-z0-9-]*$",
                    },
                    "variable_map": {
                        "type": "object",
                        "properties": {
                            "tap_page_vars": {
                                "type": "object",
                                "additionalProperties": {"type": "string"},
                            },
                            "tap_page_persistent_vars": {
                                "type": "object",
                                "additionalProperties": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
        {
            "slug": "USES_SEARCH",
            "display_name": "Uses Search",
            "description": "Panel references a Search object as its data source (req-web-stdpanel-table-search).",
            "sources": [{"type": "panel"}],
            "targets": [{"type": "search"}],
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
        from tap_web.panels.table_panel import TablePanelType
        from tap_web.panels.text_panel import TextPanelType
        from tap_web.registry import panel_type_registry

        register_edge_types_from_list(self.edge_types)
        panel_type_registry.register("text", TextPanelType)
        panel_type_registry.register("table", TablePanelType)
