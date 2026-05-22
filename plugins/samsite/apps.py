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
