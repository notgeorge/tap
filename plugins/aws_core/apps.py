"""TAP AWS Core plugin AppConfig."""

from tap_plugins.base import TapPluginConfig


class AwsCoreConfig(TapPluginConfig):
    def ready(self) -> None:
        from plugins.aws_core.collectors import AwsSteampipeInventoryCollector
        from tap_cares.registry import register_collector

        register_collector(
            key="steampipe-inventory",
            cls=AwsSteampipeInventoryCollector,
            name="AWS Steampipe Inventory",
            description=(
                "Collect AWS account inventory through trusted Steampipe query profiles."
            ),
        )
