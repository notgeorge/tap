"""Tests for Search execute API endpoint."""

import uuid

import pytest

from tap_grid.models import Search


def _orm_character_search():
    return Search.objects.create(
        name="All Characters",
        search_type="orm",
        root="node",
        definition={"filters": {"entity_type": "character"}},
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
        from plugins.lotr.models import Character

        Character.objects.create(bio="Hobbit")
        search = _orm_character_search()
        response = logged_in_client.post(
            f"/api/v1/searches/{search.entity_id}/execute",
            data={"inputs": {}},
            content_type="application/json",
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["nodes"]) >= 1

    def test_input_validation_failure(self, logged_in_client):
        search = Search.objects.create(
            name="With Schema",
            search_type="orm",
            root="node",
            definition={"filters": {"entity_type": "character"}},
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
        """Graph reads require grid.read (req-tap-auth-service-boundary-3): an
        anonymous request resolves to no actor and is denied with a 403. This
        supersedes the former public-read behavior — reads are protected by
        default under the on-by-default enforcement."""
        search = _orm_character_search()
        response = client.post(
            f"/api/v1/searches/{search.entity_id}/execute",
            data={},
            content_type="application/json",
        )
        assert response.status_code == 403
