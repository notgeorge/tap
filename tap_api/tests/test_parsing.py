"""NUL-rejection at the API parse chokepoint (NulForbiddingParser).

PostgreSQL text fields cannot store U+0000, so a NUL riding any request into an
ORM write or filter detonates as a psycopg DataError 500 (authenticated api-fuzz
finding, 2026-08-10). The parser rejects it wholesale — body, query params, and
nested container keys/values — with a 400 before any view runs (ninja wraps all
parse_body exceptions into 400, so 400 is the uniform rejection status).
"""

import json
import uuid

import pytest

NUL = chr(0)  # written via chr() — a literal escape would put a raw NUL byte in this file


@pytest.mark.django_db
class TestNulRejection:
    def test_nul_in_body_string_rejected(self, logged_in_client):
        """The original fuzz repro: entity_type containing U+0000 on create."""
        response = logged_in_client.post(
            "/api/v1/entities/",
            data=json.dumps({"entity_type": NUL + "concept", "name": "x"}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_nul_in_query_param_rejected(self, logged_in_client):
        """%00 in a filter param would ride into a psycopg text bind the same way.
        The querydict path is not wrapped by ninja, so our message survives."""
        response = logged_in_client.get("/api/v1/entities/?entity_type=%00x")
        assert response.status_code == 400
        assert "NUL" in response.json()["detail"]

    def test_nul_nested_in_container_rejected(self, logged_in_client):
        """Recursion proof: a NUL buried in a properties dict (value AND key)."""
        payloads = (
            {"note": f"a{NUL}b"},
            {f"k{NUL}ey": "v"},
            {"deep": ["ok", {"x": NUL}]},
        )
        for properties in payloads:
            response = logged_in_client.post(
                "/api/v1/edges/",
                data=json.dumps(
                    {
                        "from_entity_id": str(uuid.uuid4()),
                        "to_entity_id": str(uuid.uuid4()),
                        "edge_type": "DEPENDS_ON",
                        "properties": properties,
                    }
                ),
                content_type="application/json",
            )
            assert response.status_code == 400

    def test_nul_free_input_unaffected(self, logged_in_client):
        response = logged_in_client.post(
            "/api/v1/entities/",
            data=json.dumps({"entity_type": "concept", "name": "clean"}),
            content_type="application/json",
        )
        assert response.status_code == 201
