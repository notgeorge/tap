"""Tests for tap_viz models."""

import pytest

from tap_core.models import Entity
from tap_viz.models import Layout


@pytest.mark.django_db
class TestLayout:
    def test_layout_requires_entity(self):
        entity = Entity.objects.create(entity_type="layout", display_name="Test")
        layout = Layout.objects.create(entity=entity, name="Test Layout")
        assert layout.entity == entity
        assert layout.name == "Test Layout"

    def test_layout_str(self):
        entity = Entity.objects.create(entity_type="layout")
        layout = Layout.objects.create(entity=entity, name="My Layout")
        assert str(layout) == "My Layout"

    def test_layout_cytoscape_config_default(self):
        entity = Entity.objects.create(entity_type="layout")
        layout = Layout.objects.create(entity=entity, name="Empty")
        assert layout.cytoscape_config == {}

    def test_layout_stores_cytoscape_config(self):
        entity = Entity.objects.create(entity_type="layout")
        config = {
            "elements": [
                {"data": {"id": "a", "label": "Node A"}},
                {"data": {"id": "b", "label": "Node B"}},
                {"data": {"source": "a", "target": "b"}},
            ],
            "layout": {"name": "grid"},
        }
        layout = Layout.objects.create(
            entity=entity,
            name="With Config",
            cytoscape_config=config,
        )
        layout.refresh_from_db()
        assert layout.cytoscape_config == config
