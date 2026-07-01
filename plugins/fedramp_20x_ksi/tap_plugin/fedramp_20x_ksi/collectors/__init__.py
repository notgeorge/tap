"""FedRAMP 20x KSI catalog collector.

Spec: plugins/fedramp_20x_ksi/specs/spec-fedramp-20x-ksi-collector.md
"""

from tap_plugin.fedramp_20x_ksi.collectors.ksi_catalog import KSICollector

__all__ = ["KSICollector"]
