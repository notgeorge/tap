"""Validation tests for the AWS Core plugin.

Uses the centralized plugin validation system at all three levels.
Plugin-specific domain tests (defaults, config round-trips) are separate.
"""

from pathlib import Path

import pytest

from tap_plugins.validate.service import validate_plugin

PLUGIN_ROOT = Path(__file__).resolve().parent.parent


class TestAwsCoreStructure:
    def test_structure_passes(self):
        result = validate_plugin(PLUGIN_ROOT, level="structure")
        assert result.ok, result.to_human()

    def test_strict_structure_passes(self):
        result = validate_plugin(PLUGIN_ROOT, level="structure", strict=True)
        assert result.ok, result.to_human()


class TestAwsCoreLoads:
    def test_loads_passes(self):
        result = validate_plugin(PLUGIN_ROOT, level="loads")
        assert result.ok, result.to_human()

    def test_all_37_models_load(self):
        result = validate_plugin(PLUGIN_ROOT, level="loads")
        model_check = next(c for c in result.checks if c.id == "model-classes")
        info_msgs = [m for m in model_check.messages if m.severity == "info"]
        assert len(info_msgs) == 37


@pytest.mark.django_db
class TestAwsCoreRuns:
    def test_runs_passes(self):
        result = validate_plugin(PLUGIN_ROOT, level="runs")
        assert result.ok, result.to_human()

    def test_all_37_models_create(self):
        result = validate_plugin(PLUGIN_ROOT, level="runs")
        node_check = next(c for c in result.checks if c.id == "create-nodes")
        ok_msgs = [m for m in node_check.messages if "OK" in m.text]
        assert len(ok_msgs) == 37

    def test_edges_create(self):
        result = validate_plugin(PLUGIN_ROOT, level="runs")
        edge_check = next(c for c in result.checks if c.id == "create-edges")
        assert edge_check.status == "pass"

    def test_grift_imports(self):
        result = validate_plugin(PLUGIN_ROOT, level="runs")
        grift_check = next(c for c in result.checks if c.id == "grift-import")
        assert grift_check.status == "pass"

    def test_no_data_persisted(self):
        from tap_grid.models import Entity

        count_before = Entity.objects.count()
        result = validate_plugin(PLUGIN_ROOT, level="runs")
        assert result.ok
        assert Entity.objects.count() == count_before
