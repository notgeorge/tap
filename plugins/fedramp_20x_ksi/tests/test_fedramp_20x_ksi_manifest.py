"""Validation tests for the FedRAMP 20x KSI plugin.

Structure-level tests only in v0 — the plugin is not yet registered in
INSTALLED_APPS, so loads/runs-level validation is deferred until integration.
"""

from pathlib import Path

from tap_plugins.validate.service import validate_plugin

PLUGIN_ROOT = Path(__file__).resolve().parent.parent


class TestFedramp20xKsiStructure:
    def test_structure_passes(self):
        result = validate_plugin(PLUGIN_ROOT, level="structure")
        assert result.ok, result.to_human()

    def test_strict_structure_passes(self):
        result = validate_plugin(PLUGIN_ROOT, level="structure", strict=True)
        assert result.ok, result.to_human()
