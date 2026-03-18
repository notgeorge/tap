"""Tests for Entity API endpoints."""

import uuid

import pytest

from tap_grid.models import Entity
from tap_grid.services import create_entity


@pytest.mark.django_db
class TestListEntities:
    def test_returns_200(self, logged_in_client):
        response = logged_in_client.get("/api/v1/entities/")
        assert response.status_code == 200

    def test_returns_created_entity(self, logged_in_client):
        entity = create_entity("concept", name="Least Privilege")
        data = logged_in_client.get("/api/v1/entities/").json()
        found = [e for e in data if e["id"] == str(entity.pk)]
        assert len(found) == 1
        assert found[0]["name"] == "Least Privilege"

    def test_filter_by_type(self, logged_in_client):
        entity = create_entity("concept", name="FilterTest")
        create_entity("precept", name="B")
        data = logged_in_client.get("/api/v1/entities/?entity_type=concept").json()
        found = [e for e in data if e["id"] == str(entity.pk)]
        assert len(found) == 1
        assert found[0]["name"] == "FilterTest"

    def test_pagination(self, logged_in_client):
        for i in range(5):
            create_entity("concept", name=f"C{i}")
        data = logged_in_client.get("/api/v1/entities/?limit=2&offset=2").json()
        assert len(data) == 2


@pytest.mark.django_db
class TestGetEntity:
    def test_found(self, logged_in_client):
        entity = create_entity("concept", name="Test")
        data = logged_in_client.get(f"/api/v1/entities/{entity.pk}/").json()
        assert data["id"] == str(entity.pk)
        assert data["name"] == "Test"

    def test_not_found(self, logged_in_client):
        response = logged_in_client.get(f"/api/v1/entities/{uuid.uuid4()}/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestCreateEntity:
    def test_create(self, logged_in_client):
        count_before = Entity.objects.count()
        response = logged_in_client.post(
            "/api/v1/entities/",
            data={"entity_type": "concept", "name": "Defense in Depth"},
            content_type="application/json",
        )
        assert response.status_code == 201
        data = response.json()
        assert data["entity_type"] == "concept"
        assert data["name"] == "Defense in Depth"
        assert Entity.objects.count() == count_before + 1

    def test_missing_type_rejected(self, logged_in_client):
        response = logged_in_client.post(
            "/api/v1/entities/",
            data={"name": "No Type"},
            content_type="application/json",
        )
        assert response.status_code == 422


@pytest.mark.django_db
class TestUpdateEntity:
    def test_patch_name(self, logged_in_client):
        entity = create_entity("concept", name="Old")
        response = logged_in_client.patch(
            f"/api/v1/entities/{entity.pk}/",
            data={"name": "New"},
            content_type="application/json",
        )
        assert response.json()["name"] == "New"

    def test_not_found(self, logged_in_client):
        response = logged_in_client.patch(
            f"/api/v1/entities/{uuid.uuid4()}/",
            data={"name": "X"},
            content_type="application/json",
        )
        assert response.status_code == 404

    def test_no_op_patch(self, logged_in_client):
        entity = create_entity("concept", name="Same")
        response = logged_in_client.patch(
            f"/api/v1/entities/{entity.pk}/",
            data={},
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Same"


@pytest.mark.django_db
class TestDeleteEntity:
    def test_delete(self, logged_in_client):
        entity = create_entity("concept")
        response = logged_in_client.delete(f"/api/v1/entities/{entity.pk}/")
        assert response.status_code == 204
        assert not Entity.objects.filter(pk=entity.pk).exists()

    def test_not_found(self, logged_in_client):
        response = logged_in_client.delete(f"/api/v1/entities/{uuid.uuid4()}/")
        assert response.status_code == 404
