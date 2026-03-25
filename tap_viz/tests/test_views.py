"""Tests for tap_viz panel rendering via the tap_web panel endpoint."""

import pytest
from django.test import Client

from tap_grid.models import Edge, Entity, Search
from tap_web.models import Panel
from tap_viz.models import Layout
from tap_viz.panels.graph_panel import GraphPanelType, hub_and_spoke_runner


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
        assert b"USES_LAYOUT" in response.content


@pytest.mark.django_db(databases=["default", "search_readonly"])
class TestHubAndSpokeRunner:
    """hub_and_spoke_runner returns the hub entity plus its one-hop neighborhood."""

    def _make_entities(self) -> tuple[Entity, Entity, Entity, Edge]:
        """Create hub, two neighbors, and edges from hub to each."""
        hub = Entity.objects.create(entity_type="character", name="Gandalf")
        n1 = Entity.objects.create(entity_type="artifact", name="Staff")
        n2 = Entity.objects.create(entity_type="location", name="Minas Tirith")

        edge1 = Edge.objects.create(
            entity=Entity.objects.create(entity_type="edge", name="WIELDS"),
            from_entity=hub, to_entity=n1, edge_type="WIELDS",
        )
        Edge.objects.create(
            entity=Entity.objects.create(entity_type="edge", name="LOCATED_IN"),
            from_entity=hub, to_entity=n2, edge_type="LOCATED_IN",
        )
        return hub, n1, n2, edge1

    def test_returns_hub_and_neighbors(self):
        hub, n1, n2, _ = self._make_entities()
        result = hub_and_spoke_runner(None, {"entity_id": str(hub.pk)})
        node_ids = {n["entity_id"] for n in result["nodes"]}
        assert str(hub.pk) in node_ids
        assert str(n1.pk) in node_ids
        assert str(n2.pk) in node_ids

    def test_returns_outbound_edges(self):
        hub, _, _, edge1 = self._make_entities()
        result = hub_and_spoke_runner(None, {"entity_id": str(hub.pk)})
        edge_types = {e["edge_type"] for e in result["edges"]}
        assert "WIELDS" in edge_types
        assert "LOCATED_IN" in edge_types

    def test_includes_inbound_edges(self):
        hub = Entity.objects.create(entity_type="character", name="Frodo")
        neighbor = Entity.objects.create(entity_type="character", name="Sam")
        Edge.objects.create(
            entity=Entity.objects.create(entity_type="edge", name="MENTORS"),
            from_entity=neighbor,
            to_entity=hub,
            edge_type="MENTORS",
            properties={"discipline": "courage"},
        )
        result = hub_and_spoke_runner(None, {"entity_id": str(hub.pk)})
        edge_types = {e["edge_type"] for e in result["edges"]}
        assert "MENTORS" in edge_types
        assert str(neighbor.pk) in {n["entity_id"] for n in result["nodes"]}

    def test_missing_entity_id_returns_empty(self):
        result = hub_and_spoke_runner(None, {})
        assert result["nodes"] == []
        assert result["edges"] == []
        assert result["warnings"]

    def test_nonexistent_entity_returns_empty(self):
        result = hub_and_spoke_runner(None, {"entity_id": "00000000-0000-0000-0000-000000000000"})
        assert result["nodes"] == []

    def test_isolated_hub_has_no_edges(self):
        hub = Entity.objects.create(entity_type="character", name="Isolated")
        result = hub_and_spoke_runner(None, {"entity_id": str(hub.pk)})
        assert len(result["nodes"]) == 1
        assert result["edges"] == []
