"""Tests for EntityType API endpoint."""

import pytest

from tap_core.models import EntityType


@pytest.mark.django_db
class TestListEntityTypes:
    def test_returns_types(self, logged_in_client):
        EntityType.objects.create(slug="server", display_name="Server", plugin_name="infra")
        data = logged_in_client.get("/api/v1/entity-types/").json()
        assert len(data) >= 1
        slugs = [t["slug"] for t in data]
        assert "server" in slugs

    def test_empty(self, logged_in_client):
        EntityType.objects.all().delete()
        assert logged_in_client.get("/api/v1/entity-types/").json() == []
