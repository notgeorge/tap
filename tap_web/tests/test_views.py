"""Tests for tap_web views."""

import pytest
from django.test import Client


@pytest.mark.django_db
class TestLandingView:
    """Root / uses setup placeholder when no LandingPage is configured."""

    def test_root_returns_200(self):
        client = Client()
        response = client.get("/")
        assert response.status_code == 200

    def test_root_shows_setup_placeholder_without_landing_page(self):
        client = Client()
        response = client.get("/")
        assert "tap_web/setup_placeholder.html" in [t.name for t in response.templates]

    def test_root_placeholder_contains_admin_link(self):
        client = Client()
        response = client.get("/")
        assert b"/admin/" in response.content
