"""TAP GitHub Core plugin AppConfig."""

from tap_plugins.base import TapPluginConfig


class GithubCoreConfig(TapPluginConfig):
    def ready(self) -> None:
        # Base ready() loads tap-plugin.toml and registers the plugin's
        # edges/types/searches.
        super().ready()

        # Register the GitHub collector with tap_cares' dual-existence
        # registry. Imported here, not at module top, so the apps loading
        # graph stays light (jsonschema + yaml + the API client only pull
        # in once a collector run is actually requested).
        from plugins.github_core.collectors.github_collector.collector import GithubCollector
        from tap_cares.registry import register_collector

        register_collector(
            key="github_core",
            cls=GithubCollector,
            name="GitHub Core Collector",
            description=(
                "Collects GitHub Actions deployment plumbing for the "
                "configured repos via a PAT (github_pat secret). Two-phase "
                "run: collection (account/repo/workflows/runs/jobs/runners + "
                "workflow YAML) followed by enrichment (REFERENCES_RESOURCE "
                "edges from the grid-link manifest)."
            ),
        )
