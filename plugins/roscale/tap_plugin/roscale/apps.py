"""ROSCALE plugin AppConfig."""

from tap_plugins.base import TapPluginConfig


class RoscaleConfig(TapPluginConfig):
    def ready(self) -> None:
        super().ready()
        from tap_plugin.roscale.panels.oscal_poam_workbench import (
            OscalPoamWorkbenchPanelType,
        )
        from tap_plugin.roscale.panels.oscal_workbench import OscalWorkbenchPanelType
        from tap_web.registry import panel_type_registry

        panel_type_registry.register(
            "roscale-oscal-workbench", OscalWorkbenchPanelType
        )
        panel_type_registry.register(
            "roscale-oscal-poam-workbench", OscalPoamWorkbenchPanelType
        )
