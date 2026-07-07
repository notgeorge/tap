"""lotr self-validates through validate_plugin — parity with every other plugin.

Like github_core/aws_core/fedramp/roscale/etc., lotr ships a manifest test that
runs validate_plugin against its OWN directory. It is deliberately the richest
such fixture: lotr is the only plugin that declares BOTH editors and searches,
so it is the fixture that exercises validate's editor-classes / search-callables
check paths end-to-end (the generic tap_plugins tool-tests cover the mechanism
with synthetic fixtures; this proves it against a real editor + search + grift).

lotr is retained purely for this self-testing / nostalgia role — nothing outside
plugins/lotr/ is load-bearing on it.
"""

from __future__ import annotations

import pytest

from tap.plugin_testing import find_plugin_source_root
from tap_plugins.validate.service import validate_plugin

PLUGIN_ROOT = find_plugin_source_root(__file__)

pytestmark = pytest.mark.skipif(
    PLUGIN_ROOT is None,
    reason="source-layout validation needs the plugin source tree; installed as a wheel here (delegated to the plugin repo's own build).",
)


class TestLotrManifest:
    def test_structure_passes(self):
        result = validate_plugin(PLUGIN_ROOT)
        assert result.ok, result.to_human()
        assert result.level == "structure"

    def test_structure_strict_passes(self):
        result = validate_plugin(PLUGIN_ROOT, level="structure", strict=True)
        assert result.ok, result.to_human()

    def test_loads_passes_with_editor_and_search_checks(self):
        """loads-level exercises the editor-classes + search-callables paths —
        lotr is the only plugin declaring both, so it is their coverage fixture."""
        result = validate_plugin(PLUGIN_ROOT, level="loads")
        assert result.ok, result.to_human()
        check_ids = {c.id for c in result.checks}
        assert "model-classes" in check_ids
        assert "editor-classes" in check_ids
        assert "search-callables" in check_ids

    @pytest.mark.django_db
    def test_runs_passes_with_create_and_grift_checks(self):
        result = validate_plugin(PLUGIN_ROOT, level="runs")
        assert result.ok, result.to_human()
        check_ids = {c.id for c in result.checks}
        assert "create-nodes" in check_ids
        assert "create-edges" in check_ids
        assert "grift-import" in check_ids
