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
        from plugins.samsite.collectors.compliance_collector.collector import (
            SamsiteComplianceCollector,
        )
        from tap_cares.registry import register_collector

        register_collector(
            key="samsite-compliance",
            cls=SamsiteComplianceCollector,
            name="Samsite Compliance Collector",
            description=(
                "Fetches samsite's signed /.well-known/ compliance artifacts "
                "(KSI signal, VDR report, OSCAL SSP/POA&M, IIW) over HTTPS, "
                "verifies their Sigstore signatures, and decomposes them into "
                "the fedramp_20x_ksi compliance-artifact graph."
            ),
        )

        # Samsite-side nav-link cards panel — generic static-link renderer used
        # by samsite GRIFT to wire one-click discovery between samsite pages
        # (req-samsite-pages-discovery-1).
        from plugins.samsite.panels.nav_links import NavLinksPanelType
        from tap_web.registry import panel_type_registry

        panel_type_registry.register("samsite-nav-links", NavLinksPanelType)

        # KSI Scoreboard — synthesizes per-indicator pass/in-progress/accepted/gap
        # status by joining the on-grid KSI catalog against the latest SSP +
        # POA&M emissions. Samsite-specific because the catalog + artifacts are
        # samsite's; the panel can be lifted to fedramp_20x_ksi later if a
        # second consumer appears.
        from plugins.samsite.panels.ksi_scoreboard import KsiScoreboardPanelType

        panel_type_registry.register("samsite-ksi-scoreboard", KsiScoreboardPanelType)

        # VDR Ingestion Health — consumer-side complement to the upstream
        # disclose-shortcut flags (kev_catalog_loaded, dependabot_alerts_loaded).
        # Surfaces the latest vdr_report.summary's evaluation-actually-ran flags
        # as a pill row on the compliance landing, so a silent upstream
        # regression of either ingestion path is visible in the UI rather than
        # buried in JSON.
        from plugins.samsite.panels.vdr_ingestion_health import (
            VdrIngestionHealthPanelType,
        )

        panel_type_registry.register(
            "samsite-vdr-ingestion-health", VdrIngestionHealthPanelType
        )
