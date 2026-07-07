"""Validation tests for the FedRAMP 20x KSI plugin.

Structure-level tests only in v0 — the plugin is not yet registered in
INSTALLED_APPS, so loads/runs-level validation is deferred until integration.
"""

import pytest

from tap.plugin_testing import find_plugin_source_root
from tap_plugins.validate.service import validate_plugin

PLUGIN_ROOT = find_plugin_source_root(__file__)

pytestmark = pytest.mark.skipif(
    PLUGIN_ROOT is None,
    reason="source-layout validation needs the plugin source tree; installed as a wheel here (delegated to the plugin repo's own build).",
)


class TestFedramp20xKsiStructure:
    def test_structure_passes(self):
        result = validate_plugin(PLUGIN_ROOT, level="structure")
        assert result.ok, result.to_human()

    def test_strict_structure_passes(self):
        result = validate_plugin(PLUGIN_ROOT, level="structure", strict=True)
        assert result.ok, result.to_human()
