"""Shared fixtures for tap_api tests."""

import pytest
from django.contrib.auth import get_user_model


@pytest.fixture
def logged_in_client(client):
    """Django test client with an authenticated session."""
    user = get_user_model().objects.create_user(username="testuser", password="testpass")
    client.force_login(user)
    return client
