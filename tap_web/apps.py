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
            "name": "Uses Panel",
            "description": "Page embeds a panel.",
            "sources": [{"type": "page"}],
            "targets": [{"type": "panel"}],
            "default_dimensions": {"tap.graph": "web"},
            # Hotlink participation data (req-grid-hotlink-edge-data).
            # The 'hotlink' object is required; variable_map is optional.
            "property_schema": {
                "type": "object",
                "required": ["hotlink"],
                "properties": {
                    "hotlink": {
                        "type": "object",
                        "required": ["model", "spec", "value"],
                        "properties": {
                            "model": {"type": "string"},
                            "spec": {"type": "string"},
                            "value": {
                                "type": "string",
                                "pattern": "^[a-z][a-z0-9-]*$",
                            },
                        },
                        "additionalProperties": False,
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
            "name": "Uses Search",
            "description": "Panel references a Search object as its data source (req-web-stdpanel-table-search).",
            "sources": [{"type": "panel"}],
            "targets": [{"type": "search"}],
            "default_dimensions": {"tap.graph": "web"},
        },
        {
            "slug": "USES_LANDING_PAGE",
            "name": "Uses Landing Page",
            "description": "Landing page designates a target page for the root URL.",
            "sources": [{"type": "landing_page"}],
            "targets": [{"type": "page"}],
            "default_dimensions": {"tap.graph": "web"},
        },
    ]

    def ready(self) -> None:
        from tap_plugins.base import register_edge_types_from_list
        from tap_web.editor import EditorDescriptor
        from tap_web.panels.chart import ChartPanelType
        from tap_web.panels.flip_panel import FlipPanelType
        from tap_web.panels.table_panel import TablePanelType
        from tap_web.panels.text_panel import TextPanelType
        from tap_web.registry import panel_type_registry, register_editor

        register_edge_types_from_list(self.edge_types)
        from tap_web.panels.batch_viewer import BatchViewerPanelType
        from tap_web.panels.editor_panel import EditorPanelType
        from tap_web.panels.sequence_nav import SequenceNavPanelType
        from tap_web.panels.viewer_panel import ViewerPanelType

        panel_type_registry.register("text", TextPanelType)
        panel_type_registry.register("table", TablePanelType)
        panel_type_registry.register("flip", FlipPanelType)
        panel_type_registry.register("viewer", ViewerPanelType)
        panel_type_registry.register("editor", EditorPanelType)
        panel_type_registry.register("chart", ChartPanelType)
        panel_type_registry.register("sequence-nav", SequenceNavPanelType)
        panel_type_registry.register("batch-viewer", BatchViewerPanelType)

        class _PanelEditorDescriptor(EditorDescriptor):
            """Redirects /object/panel/.../edit/ to the panel-specific editor."""

            entity_type = "panel"

            def get_editor_initial(self, obj: Any) -> dict[str, Any]:
                return {}

            def handle_save(self, form: Any, obj: Any, request: Any) -> Any:
                raise NotImplementedError

            def get_form_class(self, obj: Any) -> None:
                return None

            def get_extra_context(self, obj: Any) -> dict[str, Any]:
                return {"edit_url_override": f"/panel/{obj.slug}--{obj.entity_id}/edit/"}

        register_editor(_PanelEditorDescriptor())
