"""Tests for tap_viz panel rendering via the tap_web panel endpoint."""

import pytest
from django.test import Client

from tap_grid.models import Edge, Entity, Search
from tap_viz.models import Layout
from tap_viz.panels.graph_panel import GraphPanelType
from tap_web.models import Panel


@pytest.mark.django_db
class TestGraphPanelView:
    def _make_panel_with_layout_and_search(self) -> tuple[Panel, str]:
        """Create a wired graph panel and return (panel, panel_url_id)."""
        search = Search.objects.create(
            name="Test Nodes",
            search_type="orm",
            root="node",
            definition={"filters": {}, "order_by": ["name"]},
        )
        layout_entity = Entity.objects.create(entity_type="layout", name="Test Layout")
        layout = Layout.objects.create(entity=layout_entity, name="Test Layout")

        edge_entity = Entity.objects.create(entity_type="edge", name="USES_SEARCH")
        Edge.objects.create(
            entity=edge_entity,
            from_entity=layout.entity,
            to_entity=search.entity,
            edge_type="USES_SEARCH",
            properties={"search-id": "main"},
        )

        panel = Panel.objects.create(
            slug="test-graph",
            name="Test Graph",
            view=GraphPanelType.view,
            js=GraphPanelType.js,
            css=GraphPanelType.css,
        )
        edge_entity2 = Entity.objects.create(entity_type="edge", name="USES_LAYOUT")
        Edge.objects.create(
            entity=edge_entity2,
            from_entity=panel.entity,
            to_entity=layout.entity,
            edge_type="USES_LAYOUT",
            properties={"layout-id": "default"},
        )

        panel_url_id = f"test-graph--{panel.entity_id}"
        return panel, panel_url_id

    def test_graph_panel_renders_200(self, client: Client):
        _, panel_url_id = self._make_panel_with_layout_and_search()
        response = client.get(f"/panel/{panel_url_id}/")
        assert response.status_code == 200

    def test_graph_panel_uses_correct_template(self, client: Client):
        _, panel_url_id = self._make_panel_with_layout_and_search()
        response = client.get(f"/panel/{panel_url_id}/")
        assert "tap_viz/panels/graph_panel.html" in [t.name for t in response.templates]

    def test_graph_panel_no_layout_shows_error(self, client: Client):
        panel = Panel.objects.create(
            slug="orphan-graph",
            name="Orphan Graph",
            view=GraphPanelType.view,
        )
        panel_url_id = f"orphan-graph--{panel.entity_id}"
        response = client.get(f"/panel/{panel_url_id}/")
        assert response.status_code == 200
        assert b"No projection or layout linked" in response.content
