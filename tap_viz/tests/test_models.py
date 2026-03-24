"""Tests for tap_viz models."""

import pytest

from tap_grid.models import Entity
from tap_viz.models import Layout


@pytest.mark.django_db
class TestLayout:
    def test_layout_requires_entity(self):
        entity = Entity.objects.create(entity_type="layout", name="Test")
        layout = Layout.objects.create(entity=entity, name="Test Layout")
        assert layout.entity == entity
        assert layout.name == "Test Layout"

    def test_layout_str(self):
        entity = Entity.objects.create(entity_type="layout")
        layout = Layout.objects.create(entity=entity, name="My Layout")
        assert str(layout) == "My Layout"

    def test_layout_definition_default(self):
        entity = Entity.objects.create(entity_type="layout")
        layout = Layout.objects.create(entity=entity, name="Empty")
        assert layout.definition == {}

    def test_layout_stores_definition(self):
        entity = Entity.objects.create(entity_type="layout")
        definition = {
            "inputs": [],
            "steps": [{"type": "search", "search-id": "main"}],
            "presentation": {"placement": "cytoscape:cose"},
            "interactions": {},
        }
        layout = Layout.objects.create(
            entity=entity,
            name="With Definition",
            definition=definition,
        )
        layout.refresh_from_db()
        assert layout.definition == definition
