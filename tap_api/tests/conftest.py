"""Shared fixtures for tap_api tests."""

import pytest

from tap_core.models import User


@pytest.fixture
def logged_in_client(client):
    """Django test client with an authenticated session."""
    user = User.objects.create_user(username="testuser", password="testpass")
    client.force_login(user)
    return client
