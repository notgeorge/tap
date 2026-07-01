"""Genericom plugin AppConfig."""

from tap_plugins.base import TapPluginConfig


class GenericomConfig(TapPluginConfig):
    def ready(self) -> None:
        super().ready()
        from tap_plugin.genericom.panels.instance_hero import (
            GenericomInstanceHeroPanelType,
        )
        from tap_plugin.genericom.panels.open_alerts import (
            GenericomOpenAlertsPanelType,
        )
        from tap_web.registry import panel_type_registry

        panel_type_registry.register(
            "genericom-open-alerts", GenericomOpenAlertsPanelType
        )
        panel_type_registry.register(
            "genericom-ec2-instance-hero", GenericomInstanceHeroPanelType
        )
