"""Structural + loads validation tests for the github_core plugin."""

import pytest

from tap.plugin_testing import find_plugin_source_root
from tap_plugins.validate.service import validate_plugin

PLUGIN_ROOT = find_plugin_source_root(__file__)

pytestmark = pytest.mark.skipif(
    PLUGIN_ROOT is None,
    reason="source-layout validation needs the plugin source tree; installed as a wheel here (delegated to the plugin repo's own build).",
)


class TestStructure:
    def test_structure_passes(self) -> None:
        result = validate_plugin(PLUGIN_ROOT, level="structure")
        assert result.ok, result.to_human()

    def test_strict_passes(self) -> None:
        result = validate_plugin(PLUGIN_ROOT, level="structure", strict=True)
        assert result.ok, result.to_human()


class TestLoads:
    def test_loads_passes(self) -> None:
        result = validate_plugin(PLUGIN_ROOT, level="loads", strict=True)
        assert result.ok, result.to_human()
