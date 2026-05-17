"""TAP AWS Core plugin AppConfig."""

from tap_plugins.base import TapPluginConfig


class AwsCoreConfig(TapPluginConfig):
    def ready(self) -> None:
        # No collector registered. The steampipe collector was excised on
        # 2026-05-17 (parked at git tag ``park/steampipe-tooling``); the
        # boto3 collector is built from scratch starting 2026-05-18 and
        # will register here. The plugin's models/edges/catalog remain
        # live and collector-agnostic.
        return
