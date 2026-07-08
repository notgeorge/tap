"""Validation tests for the AWS Core plugin.

Uses the centralized plugin validation system at all three levels.
Plugin-specific domain tests (defaults, config round-trips) are separate.
"""

import tomllib
from pathlib import Path

import pytest

from tap.plugin_testing import find_plugin_source_root
from tap_plugins.validate.service import validate_plugin

PLUGIN_ROOT = find_plugin_source_root(__file__)

pytestmark = pytest.mark.skipif(
    PLUGIN_ROOT is None,
    reason="source-layout validation needs the plugin source tree; installed as a wheel here (delegated to the plugin repo's own build).",
)


def _manifest_path() -> Path:
    """Locate tap-plugin.toml across legacy and package-mode layouts.

    Package-mode moves the manifest into the namespace package
    (tap_plugin/<slug>/tap-plugin.toml); legacy kept it at the plugin root.
    """
    legacy = PLUGIN_ROOT / "tap-plugin.toml"
    if legacy.is_file():
        return legacy
    return next((PLUGIN_ROOT / "tap_plugin").glob("*/tap-plugin.toml"))


def _declared_model_count() -> int:
    """Number of models declared in the plugin manifest.

    Derived from tap-plugin.toml so adding a model never breaks this test on
    a hardcoded count — the invariant is "every declared model loads/creates",
    not a magic number.
    """
    manifest = tomllib.loads(_manifest_path().read_text())
    return len(manifest.get("models", {}))


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

    def test_all_declared_models_load(self):
        result = validate_plugin(PLUGIN_ROOT, level="loads")
        model_check = next(c for c in result.checks if c.id == "model-classes")
        info_msgs = [m for m in model_check.messages if m.severity == "info"]
        assert len(info_msgs) == _declared_model_count()


@pytest.mark.django_db
class TestAwsCoreRuns:
    def test_runs_passes(self):
        result = validate_plugin(PLUGIN_ROOT, level="runs")
        assert result.ok, result.to_human()

    def test_all_declared_models_create(self):
        result = validate_plugin(PLUGIN_ROOT, level="runs")
        node_check = next(c for c in result.checks if c.id == "create-nodes")
        ok_msgs = [m for m in node_check.messages if "OK" in m.text]
        assert len(ok_msgs) == _declared_model_count()

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
