"""Tests for tap_viz panel rendering via the tap_web panel endpoint."""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from tap_grid.models import Edge, Entity, Search
from tap_viz.models import Layout
from tap_viz.panels.graph_panel import GraphPanelType
from tap_web.models import Panel


@pytest.fixture
def client(db) -> Client:
    """Authenticated test client holding grid.read (tap_viewer). The login wall
    (req-tap-auth-service-boundary) requires a session to reach any tap_web page,
    and the panel endpoint now gates on grid.read (req-tap-auth-policy) with the
    ORM read backstop beneath (req-tap-auth-orm-read-backstop). During an HTTP
    request the middleware binds the request user as the caller context, so the
    browsing user itself must hold grid.read. Overrides pytest-django's anonymous
    `client` fixture for this module."""
    from django.contrib.auth.models import Group

    user = get_user_model().objects.create_user(username="viz-views", password="x")
    user.groups.add(Group.objects.get(name="tap_viewer"))
    c = Client()
    c.force_login(user)
    return c


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
        )

        panel = Panel.objects.create(
            slug="test-graph",
            name="Test Graph",
            view=GraphPanelType.view,
        )
        edge_entity2 = Entity.objects.create(entity_type="edge", name="USES_LAYOUT")
        Edge.objects.create(
            entity=edge_entity2,
            from_entity=panel.entity,
            to_entity=layout.entity,
            edge_type="USES_LAYOUT",
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
