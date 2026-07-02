"""Administrivia plugin — TAP administrative pages, panels, and infrastructure."""

from tap_plugins.base import TapPluginConfig


class AdministriviaConfig(TapPluginConfig):
    def ready(self) -> None:
        super().ready()

        # CARES Administrivia panels (req-tap-cares-administrivia-* in
        # tap_cares/specs/spec-tap-cares-administrivia.md).
        from tap_plugin.administrivia.tap_cares.panels.collector_detail import (
            CollectorDetailPanelType,
        )
        from tap_plugin.administrivia.tap_cares.panels.collector_table import (
            CollectorTablePanelType,
        )
        from tap_plugin.administrivia.tap_cares.panels.run_detail import (
            RunDetailPanelType,
        )
        from tap_plugin.administrivia.tap_cares.panels.schedule_detail import (
            ScheduleDetailPanelType,
        )
        from tap_plugin.administrivia.tap_cares.panels.schedule_table import (
            ScheduleTablePanelType,
        )
        from tap_web.registry import panel_type_registry

        panel_type_registry.register(
            "cares_collector_table", CollectorTablePanelType
        )
        panel_type_registry.register(
            "cares_collector_detail", CollectorDetailPanelType
        )
        panel_type_registry.register(
            "cares_run_detail", RunDetailPanelType
        )
        panel_type_registry.register(
            "cares_schedule_table", ScheduleTablePanelType
        )
        panel_type_registry.register(
            "cares_schedule_detail", ScheduleDetailPanelType
        )
