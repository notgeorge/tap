"""Tests for tap_web views."""

import pytest
from django.test import Client


@pytest.mark.django_db
class TestHomeView:
    def test_home_returns_200(self):
        client = Client()
        response = client.get("/")
        assert response.status_code == 200

    def test_home_uses_correct_template(self):
        client = Client()
        response = client.get("/")
        assert "tap_web/home.html" in [t.name for t in response.templates]

    def test_home_contains_tap_title(self):
        client = Client()
        response = client.get("/")
        assert b"The Analogy Platform" in response.content

    def test_home_contains_cytoscape_container(self):
        client = Client()
        response = client.get("/")
        assert b'id="cy"' in response.content
