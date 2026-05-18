"""TAP AWS Core plugin AppConfig."""

from tap_plugins.base import TapPluginConfig


class AwsCoreConfig(TapPluginConfig):
    def ready(self) -> None:
        # Base ready() loads tap-plugin.toml and registers the plugin's
        # edges/types/editors/searches. It MUST run — without it the manifest
        # is never loaded and `import_plugin_grift` skips this plugin.
        super().ready()

        # No collector registered. The steampipe collector was excised on
        # 2026-05-17 (parked at git tag ``park/steampipe-tooling``); the
        # boto3 collector is built from scratch starting 2026-05-18 and
        # will register here. The plugin's models/edges/catalog remain
        # live and collector-agnostic.
