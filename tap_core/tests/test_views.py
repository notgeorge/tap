"""Tests for secure icon serving views."""

import tempfile
from pathlib import Path

import pytest

from django.contrib.auth import get_user_model
from django.test import Client, override_settings

User = get_user_model()


@pytest.mark.django_db
class TestServeIcon:
    """Tests for the serve_icon view."""

    @pytest.fixture
    def user(self):
        """Create a test user."""
        return User.objects.create_user(username="testuser", password="testpass")

    @pytest.fixture
    def client_logged_in(self, user):
        """Create a logged-in client."""
        client = Client()
        client.login(username="testuser", password="testpass")
        return client

    @pytest.fixture
    def temp_media_root(self, tmp_path):
        """Create a temporary media root with test icon."""
        icon_dir = tmp_path / "icons"
        icon_dir.mkdir()

        # Create a test icon file
        test_icon = icon_dir / "test.svg"
        test_icon.write_text('<svg><circle r="10"/></svg>')

        # Create a subdirectory with another icon
        subdir = icon_dir / "subdir"
        subdir.mkdir()
        nested_icon = subdir / "nested.svg"
        nested_icon.write_text('<svg><rect width="10" height="10"/></svg>')

        return tmp_path

    def test_serve_icon_requires_authentication(self, client):
        """Test that unauthenticated users cannot access icons."""
        response = client.get("/media/icons/test.svg")
        # Should redirect to login or return 403/401
        assert response.status_code in [302, 401, 403]

    @override_settings(MEDIA_ROOT=None)
    def test_serve_icon_authenticated_user(self, client_logged_in, temp_media_root):
        """Test that authenticated users can access icons."""
        with override_settings(MEDIA_ROOT=str(temp_media_root)):
            response = client_logged_in.get("/media/icons/test.svg")
            assert response.status_code == 200
            assert b"<svg>" in response.content

    @override_settings(MEDIA_ROOT=None)
    def test_serve_icon_nested_path(self, client_logged_in, temp_media_root):
        """Test serving icons from subdirectories."""
        with override_settings(MEDIA_ROOT=str(temp_media_root)):
            response = client_logged_in.get("/media/icons/subdir/nested.svg")
            assert response.status_code == 200
            assert b"<rect" in response.content

    @override_settings(MEDIA_ROOT=None)
    def test_serve_icon_path_traversal_blocked(self, client_logged_in, temp_media_root):
        """Test that path traversal attempts are blocked."""
        with override_settings(MEDIA_ROOT=str(temp_media_root)):
            # Try to access a file outside the icons directory
            response = client_logged_in.get("/media/icons/../settings.py")
            assert response.status_code == 404

            response = client_logged_in.get("/media/icons/../../etc/passwd")
            assert response.status_code == 404

    @override_settings(MEDIA_ROOT=None)
    def test_serve_icon_nonexistent_file(self, client_logged_in, temp_media_root):
        """Test that requesting a nonexistent icon returns 404."""
        with override_settings(MEDIA_ROOT=str(temp_media_root)):
            response = client_logged_in.get("/media/icons/nonexistent.svg")
            assert response.status_code == 404

    @override_settings(MEDIA_ROOT=None)
    def test_serve_icon_content_type(self, client_logged_in, temp_media_root):
        """Test that correct content type is set for SVG files."""
        with override_settings(MEDIA_ROOT=str(temp_media_root)):
            response = client_logged_in.get("/media/icons/test.svg")
            assert response.status_code == 200
            # Content type should be image/svg+xml or similar
            assert "svg" in response["Content-Type"].lower()

    @override_settings(MEDIA_ROOT=None)
    def test_serve_icon_directory_blocked(self, client_logged_in, temp_media_root):
        """Test that requesting a directory returns 404."""
        with override_settings(MEDIA_ROOT=str(temp_media_root)):
            response = client_logged_in.get("/media/icons/subdir/")
            assert response.status_code == 404
