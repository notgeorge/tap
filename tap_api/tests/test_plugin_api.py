"""Tests for plugin router discovery, version endpoint, and auth."""

import pytest

from tap_core.services import create_entity


@pytest.mark.django_db
class TestPluginRouter:
    def test_concepts_endpoint(self, logged_in_client):
        entity = create_entity("concept", display_name="Least Privilege")
        create_entity("precept", display_name="Not a concept")
        response = logged_in_client.get("/api/v1/plugins/core_examples/concepts/")
        assert response.status_code == 200
        data = response.json()
        found = [e for e in data if e["id"] == str(entity.pk)]
        assert len(found) == 1
        assert found[0]["display_name"] == "Least Privilege"


@pytest.mark.django_db
class TestVersionEndpoint:
    def test_version_info(self, client):
        response = client.get("/api/v1/")
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "1"
        assert data["latest"] is True


@pytest.mark.django_db
class TestUnversionedRedirect:
    def test_redirects_to_v1(self, client):
        response = client.get("/api/entities/", follow=False)
        assert response.status_code == 302
        assert response["Location"] == "/api/v1/entities/"


@pytest.mark.django_db
class TestAuthEnforced:
    def test_unauthenticated_rejected(self, client):
        response = client.get("/api/v1/entities/")
        assert response.status_code == 401
