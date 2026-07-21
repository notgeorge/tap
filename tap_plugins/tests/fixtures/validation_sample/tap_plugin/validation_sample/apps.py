"""validation_sample plugin AppConfig.

Mirrors the grid_fixtures pattern: subclass TapPluginConfig (which reads label /
verbose_name from tap-plugin.toml) and register the plugin's one collector in
ready(). ``name`` is auto-derived from the module path (tap_plugin.validation_sample).
"""

from tap_plugins.base import TapPluginConfig


class ValidationSampleConfig(TapPluginConfig):
    def ready(self) -> None:
        super().ready()

        # Register the plugin's single no-op collector. Scope is the plugin slug
        # (collector-identity rule). validate_plugin's `runs` level never invokes
        # collectors — it only exercises create_node/create_edge/grift_import — so
        # this registration is purely to make the fixture a faithful, complete
        # plugin (one model + one edge + one collector).
        from tap_plugin.validation_sample.collectors.sample import SampleCollector

        from tap_cares.registry import register_collector

        register_collector(
            key="sample",
            scope="validation_sample",
            cls=SampleCollector,
            name="Validation sample collector",
            description=(
                "No-op collector for the validate_plugin fixture. Emits nothing and touches no "
                "grid state; exists only so the fixture declares one collector like a real plugin."
            ),
        )
