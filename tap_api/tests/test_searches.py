"""Tests for Search execute API endpoint."""

import uuid

import pytest

from tap_grid.models import Search


def _orm_character_search():
    return Search.objects.create(
        name="All Characters",
        search_type="orm",
        root="node",
        definition={"filters": {"entity_type": "grid_fixtures__constrained_source"}},
    )


@pytest.mark.django_db(transaction=True, databases=["default", "search_readonly"])
class TestExecuteSearch:
    def test_not_found(self, logged_in_client):
        response = logged_in_client.post(
            f"/api/v1/searches/{uuid.uuid4()}/execute",
            data={},
            content_type="application/json",
        )
        assert response.status_code == 404

    def test_negative_pagination_rejected(self, logged_in_client):
        """Same negative-slice 500 class the authenticated api-fuzz pass found on
        the list endpoints, closed at the schema edge before it can ride into
        execute_search. Schema validation runs before the view, so this is 422
        even for a nonexistent search id."""
        response = logged_in_client.post(
            f"/api/v1/searches/{uuid.uuid4()}/execute",
            data={"limit": -1},
            content_type="application/json",
        )
        assert response.status_code == 422
        response = logged_in_client.post(
            f"/api/v1/searches/{uuid.uuid4()}/execute",
            data={"offset": -1},
            content_type="application/json",
        )
        assert response.status_code == 422
        response = logged_in_client.post(
            f"/api/v1/searches/{uuid.uuid4()}/execute",
            data={"offset": 10**33},
            content_type="application/json",
        )
        assert response.status_code == 422

    def test_happy_path_empty(self, logged_in_client):
        search = _orm_character_search()
        response = logged_in_client.post(
            f"/api/v1/searches/{search.entity_id}/execute",
            data={},
            content_type="application/json",
        )
        assert response.status_code == 200
        body = response.json()
        assert "nodes" in body
        assert "edges" in body
        assert "info" in body
        assert body["info"]["search_type"] == "orm"

    def test_happy_path_with_results(self, logged_in_client):
        from tap_plugin.grid_fixtures.models import ConstrainedSource

        ConstrainedSource.objects.create(description="Hobbit")
        search = _orm_character_search()
        response = logged_in_client.post(
            f"/api/v1/searches/{search.entity_id}/execute",
            data={"inputs": {}},
            content_type="application/json",
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["nodes"]) >= 1

    def test_no_cap_existing_search_denied_403(self, no_cap_client):
        """An authenticated caller without `grid.read` is denied on an EXISTING
        search — authorization runs before the Search is loaded."""
        search = _orm_character_search()
        response = no_cap_client.post(
            f"/api/v1/searches/{search.entity_id}/execute",
            data={},
            content_type="application/json",
        )
        assert response.status_code == 403
        assert response.json()["reason"] == "capability_denied"

    def test_no_cap_missing_search_also_403_no_existence_leak(self, no_cap_client):
        """A no-cap caller gets the SAME 403 for a non-existent search id as for
        an existing one — the read gate wins before the lookup, so a denied caller
        cannot distinguish 404 (missing) from 200 (exists). No existence leak
        (req-tap-auth-service-boundary)."""
        response = no_cap_client.post(
            f"/api/v1/searches/{uuid.uuid4()}/execute",
            data={},
            content_type="application/json",
        )
        assert response.status_code == 403
        assert response.json()["reason"] == "capability_denied"

    def test_input_validation_failure(self, logged_in_client):
        search = Search.objects.create(
            name="With Schema",
            search_type="orm",
            root="node",
            definition={"filters": {"entity_type": "grid_fixtures__constrained_source"}},
            input_schema={
                "type": "object",
                "required": ["query"],
                "properties": {"query": {"type": "string"}},
            },
        )
        response = logged_in_client.post(
            f"/api/v1/searches/{search.entity_id}/execute",
            data={"inputs": {}},
            content_type="application/json",
        )
        assert response.status_code == 422
        assert response.json()["error"] == "input_validation_failed"

    def test_anonymous_access_denied(self, client):
        """Graph reads require login (req-tap-auth-service-boundary-3): the search
        execute route is session-authenticated, so an anonymous request is
        rejected at the edge with 401 — superseding the former public-read
        behavior. (An authenticated caller lacking grid.read gets 403, authorized
        before the Search is loaded, so existence is not leaked.)"""
        search = _orm_character_search()
        response = client.post(
            f"/api/v1/searches/{search.entity_id}/execute",
            data={},
            content_type="application/json",
        )
        assert response.status_code == 401
