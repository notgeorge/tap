"""Plugin structure / manifest validation for the gryphon_playground plugin.

Structure-level validation runs without Django — it confirms the manifest,
edge files, model dotted paths, and directory layout are well-formed.
"""

from pathlib import Path

from tap_plugins.validate.service import validate_plugin

PLUGIN_ROOT = Path(__file__).resolve().parent.parent


class TestStructure:
    def test_structure_passes(self):
        result = validate_plugin(PLUGIN_ROOT, level="structure")
        assert result.ok, result.to_human()

    def test_strict_passes(self):
        result = validate_plugin(PLUGIN_ROOT, level="structure", strict=True)
        assert result.ok, result.to_human()
