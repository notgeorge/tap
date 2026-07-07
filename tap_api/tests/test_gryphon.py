"""Read-gate proofs for the raw Gryphon execute endpoint (req-tap-auth-service-boundary).

The raw Gryphon path is the second graph-read chokepoint besides stored Searches
(see `execute_gryphon_raw`). These tests prove the endpoint is not a public
back-door around `grid.read`:

  - anonymous           → 401 (rejected at the session-auth edge, never reaches the view)
  - authenticated/no-cap → 403 (passes auth, denied by the service-boundary gate)
  - tap_admin            → 200 (authorized read returns the canonical envelope)
"""

import json

import pytest

_EXECUTE_URL = "/api/v1/gryphon/execute"
# Neutral grid_fixtures label (present in every profile that runs the core suite) — the
# read-gate proofs care about auth outcomes, not the data, so any valid label serves and
# no domain plugin is required. Empty result still returns the canonical nodes/edges envelope.
_QUERY = {"query": "MATCH (n:grid_fixtures__node) RETURN n", "inputs": {}, "layer": "lite"}


@pytest.mark.django_db(transaction=True, databases=["default", "search_readonly"])
class TestGryphonReadGate:
    def test_anonymous_denied_401(self, client):
        """No session → rejected at the edge before the view runs."""
        response = client.post(_EXECUTE_URL, data=json.dumps(_QUERY), content_type="application/json")
        assert response.status_code == 401

    def test_authenticated_without_capability_denied_403(self, no_cap_client):
        """Authenticated but no `grid.read` → the gate denies the read. Passing
        authentication does not imply permission."""
        response = no_cap_client.post(_EXECUTE_URL, data=json.dumps(_QUERY), content_type="application/json")
        assert response.status_code == 403
        assert response.json()["reason"] == "capability_denied"

    def test_admin_authorized_200(self, logged_in_client):
        response = logged_in_client.post(_EXECUTE_URL, data=json.dumps(_QUERY), content_type="application/json")
        assert response.status_code == 200
        body = response.json()
        assert "nodes" in body
        assert "edges" in body
