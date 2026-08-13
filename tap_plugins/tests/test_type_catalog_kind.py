"""The plugin loader stamps the node/edge discriminator (req-grid-entity-type-kind).

The manifest is the only place that knows which is which — it lists `models` and
`edges` separately — so the loader is where `kind` must be set. Nothing
downstream can recover it: the in-code edge registry is populated only when
plugins load, so a later sweep of a bare process would see core edges alone.
"""

from __future__ import annotations

import pytest

from tap_grid.models import EntityType, EntityTypeKind

pytestmark = pytest.mark.django_db


class _Entry:
    def __init__(self, slug: str, class_path: str = "tap_grid.models.Entity") -> None:
        self.slug = slug
        self.class_path = class_path


class _Edge:
    def __init__(self, slug: str) -> None:
        self.slug = slug
        self.name = slug.replace("_", " ").title()
        self.description = ""
        self.sources = None
        self.targets = None
        self.property_schema = None
        self.default_dimensions = None


class _Manifest:
    def __init__(self) -> None:
        self.models = [_Entry("widget")]
        self.edges = [_Edge("RUNS_ON")]


@pytest.mark.spec("req-grid-entity-type-kind")
def test_manifest_models_and_edges_are_stamped_distinctly():
    from tap_plugins.base import TapPluginConfig

    config = TapPluginConfig.__new__(TapPluginConfig)
    config._manifest = _Manifest()
    config.name = "demo_plugin"

    config._register_types_from_manifest()

    assert EntityType.objects.get(slug="widget").kind == EntityTypeKind.NODE
    assert EntityType.objects.get(slug="RUNS_ON").kind == EntityTypeKind.EDGE


@pytest.mark.spec("req-grid-entity-type-kind")
def test_reload_reclassifies_an_unclassified_row():
    # The self-healing path for rows written before the field existed: the loader
    # uses update_or_create, so the next load stamps them.
    EntityType.objects.create(slug="widget", name="Widget", plugin_name="demo_plugin")
    assert EntityType.objects.get(slug="widget").kind == ""

    from tap_plugins.base import TapPluginConfig

    config = TapPluginConfig.__new__(TapPluginConfig)
    config._manifest = _Manifest()
    config.name = "demo_plugin"
    config._register_types_from_manifest()

    assert EntityType.objects.get(slug="widget").kind == EntityTypeKind.NODE
