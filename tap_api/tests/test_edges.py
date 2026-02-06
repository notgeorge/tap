"""Tests for Edge API endpoints."""

import json
import uuid

import pytest

from tap_core.models import Edge
from tap_core.services import create_edge, create_entity


@pytest.fixture
def two_entities():
    a = create_entity("concept", display_name="A")
    b = create_entity("precept", display_name="B")
    return a, b


@pytest.mark.django_db
class TestListEdges:
    def test_returns_200(self, logged_in_client):
        response = logged_in_client.get("/api/v1/edges/")
        assert response.status_code == 200

    def test_returns_created_edge(self, logged_in_client, two_entities):
        a, b = two_entities
        edge = create_edge(a, b, "depends_on")
        data = logged_in_client.get("/api/v1/edges/").json()
        found = [e for e in data if e["entity_id"] == str(edge.entity_id)]
        assert len(found) == 1
        assert found[0]["edge_type"] == "depends_on"

    def test_filter_by_from(self, logged_in_client, two_entities):
        a, b = two_entities
        edge = create_edge(a, b, "depends_on")
        data = logged_in_client.get(f"/api/v1/edges/?from_entity_id={a.pk}").json()
        found = [e for e in data if e["entity_id"] == str(edge.entity_id)]
        assert len(found) == 1

    def test_filter_by_type(self, logged_in_client, two_entities):
        a, b = two_entities
        edge = create_edge(a, b, "depends_on")
        create_edge(b, a, "applies_to")
        data = logged_in_client.get("/api/v1/edges/?edge_type=depends_on").json()
        found = [e for e in data if e["entity_id"] == str(edge.entity_id)]
        assert len(found) == 1


@pytest.mark.django_db
class TestGetEdge:
    def test_found(self, logged_in_client, two_entities):
        a, b = two_entities
        edge = create_edge(a, b, "applies_to")
        data = logged_in_client.get(f"/api/v1/edges/{edge.pk}/").json()
        assert data["edge_type"] == "applies_to"
        assert data["entity_id"] == str(edge.entity_id)

    def test_not_found(self, logged_in_client):
        response = logged_in_client.get("/api/v1/edges/99999/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestCreateEdge:
    def test_create(self, logged_in_client, two_entities):
        a, b = two_entities
        response = logged_in_client.post(
            "/api/v1/edges/",
            data=json.dumps(
                {
                    "from_entity_id": str(a.pk),
                    "to_entity_id": str(b.pk),
                    "edge_type": "applies_to",
                    "properties": {"weight": 0.9},
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == 201
        data = response.json()
        assert data["edge_type"] == "applies_to"
        assert data["properties"] == {"weight": 0.9}

    def test_invalid_entity_404(self, logged_in_client):
        response = logged_in_client.post(
            "/api/v1/edges/",
            data=json.dumps(
                {
                    "from_entity_id": str(uuid.uuid4()),
                    "to_entity_id": str(uuid.uuid4()),
                    "edge_type": "applies_to",
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestDeleteEdge:
    def test_delete(self, logged_in_client, two_entities):
        a, b = two_entities
        edge = create_edge(a, b, "applies_to")
        response = logged_in_client.delete(f"/api/v1/edges/{edge.pk}/")
        assert response.status_code == 204
        assert not Edge.objects.filter(pk=edge.pk).exists()

    def test_not_found(self, logged_in_client):
        response = logged_in_client.delete("/api/v1/edges/99999/")
        assert response.status_code == 404
