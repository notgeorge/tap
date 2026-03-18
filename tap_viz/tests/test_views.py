"""Tests for tap_viz views."""

import pytest
from django.test import Client

from tap_grid.models import Entity
from tap_viz.models import Layout


@pytest.mark.django_db
class TestGraphView:
    def test_graph_view_returns_200_for_valid_layout(self, client: Client):
        entity = Entity.objects.create(entity_type="layout", name="Test Layout")
        Layout.objects.create(
            entity=entity,
            name="Test Layout",
            cytoscape_config={"elements": []},
        )
        response = client.get(f"/viz/graph/{entity.id}/")
        assert response.status_code == 200

    def test_graph_view_returns_404_for_invalid_layout(self, client: Client):
        response = client.get("/viz/graph/00000000-0000-0000-0000-000000000000/")
        assert response.status_code == 404

    def test_graph_view_uses_correct_template(self, client: Client):
        entity = Entity.objects.create(entity_type="layout", name="Test Layout")
        Layout.objects.create(entity=entity, name="Test Layout")
        response = client.get(f"/viz/graph/{entity.id}/")
        assert "tap_viz/graph.html" in [t.name for t in response.templates]


@pytest.mark.django_db
class TestLayoutMaker:
    def test_layout_maker_returns_200(self, client: Client):
        response = client.get("/viz/layout-maker/")
        assert response.status_code == 200

    def test_layout_maker_uses_correct_template(self, client: Client):
        response = client.get("/viz/layout-maker/")
        assert "tap_viz/layout_maker.html" in [t.name for t in response.templates]
