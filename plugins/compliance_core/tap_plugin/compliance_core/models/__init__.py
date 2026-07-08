"""Compliance Core plugin models package."""

from tap_plugin.compliance_core.models.compliance_artifact import ComplianceArtifact
from tap_plugin.compliance_core.models.compliance_context import ComplianceContext

__all__ = [
    "ComplianceArtifact",
    "ComplianceContext",
]
