"""TAP FedRAMP 20x KSI plugin AppConfig."""

from tap_plugins.base import TapPluginConfig


class Fedramp20xKsiConfig(TapPluginConfig):
    def ready(self) -> None:
        super().ready()
        from plugins.fedramp_20x_ksi.panels.compliance_view import (
            KsiCompliancePanelType,
        )
        from plugins.fedramp_20x_ksi.panels.finding_profile import (
            KsiFindingProfilePanelType,
        )
        from plugins.fedramp_20x_ksi.panels.finding_strip import (
            FindingStripPanelType,
        )
        from plugins.fedramp_20x_ksi.panels.findings_by_ksi import (
            FindingsByKsiPanelType,
        )
        from plugins.fedramp_20x_ksi.panels.findings_by_system import (
            FindingsBySystemPanelType,
        )
        from plugins.fedramp_20x_ksi.panels.indicator_profile import (
            KsiIndicatorProfilePanelType,
        )
        from plugins.fedramp_20x_ksi.panels.instance_findings import (
            KsiInstanceFindingsPanelType,
        )
        from tap_web.registry import panel_type_registry

        panel_type_registry.register("fedramp-20x-ksi-compliance", KsiCompliancePanelType)
        panel_type_registry.register("fedramp-20x-ksi-indicator-profile", KsiIndicatorProfilePanelType)
        panel_type_registry.register("fedramp-20x-ksi-finding-profile", KsiFindingProfilePanelType)
        panel_type_registry.register("finding_strip", FindingStripPanelType)
        panel_type_registry.register("findings_by_system", FindingsBySystemPanelType)
        panel_type_registry.register("findings_by_ksi", FindingsByKsiPanelType)
        panel_type_registry.register("fedramp-20x-ksi-instance-findings", KsiInstanceFindingsPanelType)

        # Register the KSI catalog collector with tap_cares. Per the
        # dual-existence pattern (tap_grid/specs/spec-grid-dual-existence.md)
        # this single call both registers the runner class AND upserts the
        # on-grid Collector node. Spec:
        # plugins/fedramp_20x_ksi/specs/spec-fedramp-20x-ksi-collector.md
        # req-fedramp-20x-ksi-collector-class-2.
        from plugins.fedramp_20x_ksi.collectors import KSICollector
        from tap_cares.registry import register_collector

        register_collector(
            key="ksi-catalog",
            cls=KSICollector,
            name="FedRAMP 20x KSI Catalog",
            description=(
                "Fetches the FedRAMP 20x Key Security Indicators catalog from the "
                "upstream rules repo, validates against pinned safety rules, diffs "
                "against the local grid, and imports changes as a GRIFT batch."
            ),
        )
