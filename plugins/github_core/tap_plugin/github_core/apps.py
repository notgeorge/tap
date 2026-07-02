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
        from tap_plugin.github_core.collectors.github_collector.collector import GithubCollector
        from tap_cares.registry import register_collector

        register_collector(
            key="github_core",
            # Stable scope (plugin slug) so the derived entity id survives module
            # renames — see the fuller note in fedramp_20x_ksi/apps.py and
            # req-tap-cares-collector-model-10.
            scope="github_core",
            cls=GithubCollector,
            name="GitHub Core Collector",
            description=(
                "Collects GitHub Actions deployment plumbing for the "
                "configured repos via a PAT (github_pat secret). Two-phase "
                "run: collection (platform/account/repo/workflows/runs/jobs/"
                "runners + workflow YAML) followed by enrichment "
                "(REFERENCES_RESOURCE + FEDERATES_VIA edges from the "
                "grid-link manifest)."
            ),
        )

        # Landing-page panel types — see spec-github-core-repo-landing-page-v0.md.
        from tap_plugin.github_core.panels.cross_grid_references import (
            CrossGridReferencesPanelType,
        )
        from tap_plugin.github_core.panels.deploy_health import DeployHealthPanelType
        from tap_plugin.github_core.panels.history_strip import HistoryStripPanelType
        from tap_plugin.github_core.panels.recent_activity import RecentActivityPanelType
        from tap_plugin.github_core.panels.repo_hero import RepoHeroPanelType
        from tap_plugin.github_core.panels.workflow_catalog import WorkflowCatalogPanelType
        from tap_web.registry import panel_type_registry

        panel_type_registry.register("github-repo-hero", RepoHeroPanelType)
        panel_type_registry.register("github-recent-activity", RecentActivityPanelType)
        panel_type_registry.register("github-deploy-health", DeployHealthPanelType)
        panel_type_registry.register("github-workflow-catalog", WorkflowCatalogPanelType)
        panel_type_registry.register("github-cross-grid-references", CrossGridReferencesPanelType)
        panel_type_registry.register("github-history-strip", HistoryStripPanelType)
