"""grid_fixtures plugin — neutral graph-node vocabulary for grid test fixtures."""

from tap_plugins.base import TapPluginConfig


class GridFixturesConfig(TapPluginConfig):
    def ready(self) -> None:
        super().ready()

        # The offline cold-boot canary: the deterministic, no-network collector the
        # dev-validation gate drives through the real backend (spec-dev-validation.md
        # req-dev-validation-real-backend). Homed here because it emits this plugin's
        # own grid_fixtures__* vocabulary — self-contained, and dev/test-only like the
        # rest of grid_fixtures. Scope is the plugin slug (collector-identity rule).
        from tap_plugin.grid_fixtures.collectors.canary import CanaryCollector

        from tap_cares.registry import register_collector

        register_collector(
            key="canary",
            scope="grid_fixtures",
            cls=CanaryCollector,
            name="Cold-boot canary",
            description=(
                "Deterministic offline canary for the dev-validation cold-boot gate: emits a fixed "
                "two-node/one-edge grid_fixtures batch with no network or credentials."
            ),
        )
