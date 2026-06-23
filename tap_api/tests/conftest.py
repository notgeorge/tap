"""Shared fixtures for tap_api tests."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group


@pytest.fixture
def logged_in_client(client, db):
    """Django test client with an authenticated, TAP-authorized session.

    The user joins `tap_admin` so API calls (which build a CallerContext from
    request.user) are authorized under the on-by-default service-boundary
    enforcement. `tap_admin` is created by the session auth seed (root conftest).
    """
    user = get_user_model().objects.create_user(username="testuser", password="testpass")
    user.groups.add(Group.objects.get(name="tap_admin"))
    client.force_login(user)
    return client
