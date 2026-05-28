"""Plugin validation system tests for sigstore_core.

Structure-level validation runs standalone (no Django, no INSTALLED_APPS).
Loads/runs levels require the plugin to be in INSTALLED_APPS and the
workspace machinery to be in place.
"""

from pathlib import Path

from tap_plugins.validate.service import validate_plugin

PLUGIN_ROOT = Path(__file__).resolve().parent.parent


class TestStructure:
    def test_structure_passes(self) -> None:
        result = validate_plugin(PLUGIN_ROOT, level="structure")
        assert result.ok, result.to_human()

    def test_strict_passes(self) -> None:
        result = validate_plugin(PLUGIN_ROOT, level="structure", strict=True)
        assert result.ok, result.to_human()
