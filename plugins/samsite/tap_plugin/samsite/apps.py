"""Samsite plugin AppConfig."""

from tap_plugins.base import TapPluginConfig


class SamsiteConfig(TapPluginConfig):
    def ready(self) -> None:
        # Base ready() loads tap-plugin.toml and registers the plugin's
        # edges/types/searches. It MUST run first.
        super().ready()

        # Dual-existence registration: registers the runner and upserts the
        # on-grid Collector node. Imported here, not at module top, so apps
        # loading does not eagerly pull the collector's fetch/verify stack.
        from tap_plugin.samsite.collectors.compliance_collector.collector import (
            SamsiteComplianceCollector,
        )
        from tap_cares.registry import register_collector

        register_collector(
            key="samsite-compliance",
            # Stable scope (plugin slug) so the derived entity id survives module
            # renames — see the fuller note in fedramp_20x_ksi/apps.py and
            # req-tap-cares-collector-model-10.
            scope="samsite",
            cls=SamsiteComplianceCollector,
            name="Samsite Compliance Collector",
            description=(
                "Fetches samsite's signed /.well-known/ compliance artifacts "
                "(KSI signal, VDR report, OSCAL SSP/POA&M, IIW) over HTTPS, "
                "verifies their Sigstore signatures, and decomposes them into "
                "the fedramp_20x_ksi compliance-artifact graph."
            ),
        )

        # KSI Scoreboard — synthesizes per-indicator pass/in-progress/accepted/gap
        # status by joining the on-grid KSI catalog against the latest SSP +
        # POA&M emissions. Samsite-specific because the catalog + artifacts are
        # samsite's; the panel can be lifted to fedramp_20x_ksi later if a
        # second consumer appears.
        from tap_plugin.samsite.panels.ksi_scoreboard import KsiScoreboardPanelType
        from tap_web.registry import panel_type_registry

        panel_type_registry.register("samsite-ksi-scoreboard", KsiScoreboardPanelType)

        # VDR Ingestion Health — consumer-side complement to the upstream
        # disclose-shortcut flags (kev_catalog_loaded, dependabot_alerts_loaded).
        # Surfaces the latest vdr_report.summary's evaluation-actually-ran flags
        # as a pill row on the compliance landing, so a silent upstream
        # regression of either ingestion path is visible in the UI rather than
        # buried in JSON.
        from tap_plugin.samsite.panels.vdr_ingestion_health import (
            VdrIngestionHealthPanelType,
        )

        panel_type_registry.register("samsite-vdr-ingestion-health", VdrIngestionHealthPanelType)

        # Classy per-artifact viewers (rollout: KSI signal first), modeled on
        # the roscale OSCAL workbench — resolve one decomposed artifact and
        # recompose it from the grid into a workbench view.
        from tap_plugin.samsite.panels.iiw_workbench import IiwWorkbenchPanelType
        from tap_plugin.samsite.panels.ksi_signal_workbench import (
            KsiSignalWorkbenchPanelType,
        )
        from tap_plugin.samsite.panels.vdr_report_workbench import (
            VdrReportWorkbenchPanelType,
        )

        panel_type_registry.register("samsite-ksi-signal-workbench", KsiSignalWorkbenchPanelType)
        panel_type_registry.register("samsite-vdr-report-workbench", VdrReportWorkbenchPanelType)
        panel_type_registry.register("samsite-iiw-workbench", IiwWorkbenchPanelType)
