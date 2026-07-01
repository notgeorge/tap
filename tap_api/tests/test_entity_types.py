"""Tests for EntityType API endpoint."""

import pytest

from tap_grid.models import EntityType


@pytest.mark.django_db
class TestListEntityTypes:
    def test_returns_types(self, logged_in_client):
        EntityType.objects.create(slug="server", name="Server", plugin_name="infra")
        data = logged_in_client.get("/api/v1/entity-types/").json()
        assert len(data) >= 1
        slugs = [t["slug"] for t in data]
        assert "server" in slugs

    def test_empty(self, logged_in_client):
        EntityType.objects.all().delete()
        assert logged_in_client.get("/api/v1/entity-types/").json() == []

    def test_no_cap_denied_403(self, no_cap_client):
        """An authenticated caller without grid.read is denied the type catalog
        (finding cs-tap-api-typecat-003) — the catalog is graph metadata, so it is
        a graph read like /api/v1/entities/. Authorization runs before the query."""
        EntityType.objects.create(slug="server", name="Server", plugin_name="infra")
        response = no_cap_client.get("/api/v1/entity-types/")
        assert response.status_code == 403
        assert response.json()["reason"] == "capability_denied"
