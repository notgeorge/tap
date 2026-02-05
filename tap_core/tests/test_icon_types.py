"""Tests for icon types and icon reference system."""

import pytest

from tap_core.icon_types import IconReference, IconType


class TestIconReference:
    """Tests for IconReference dataclass and serialization."""

    def test_named_icon_creation(self):
        """Test creating a named icon reference."""
        icon = IconReference.named("fa-server")
        assert icon.icon_type == IconType.NAMED
        assert icon.value == "fa-server"
        assert icon.metadata is None

    def test_static_icon_creation(self):
        """Test creating a static icon reference."""
        icon = IconReference.static("my_plugin/icons/custom.svg", plugin_name="my_plugin")
        assert icon.icon_type == IconType.STATIC
        assert icon.value == "my_plugin/icons/custom.svg"
        assert icon.metadata == {"plugin": "my_plugin"}

    def test_uploaded_icon_creation(self):
        """Test creating an uploaded icon reference."""
        icon = IconReference.uploaded("user_uploads/icon.svg", uploader_id=123)
        assert icon.icon_type == IconType.UPLOADED
        assert icon.value == "user_uploads/icon.svg"
        assert icon.metadata == {"uploader_id": 123}

    def test_to_dict_serialization(self):
        """Test serializing IconReference to dict."""
        icon = IconReference.static("path/to/icon.svg", plugin_name="test")
        data = icon.to_dict()
        assert data == {
            "type": "static",
            "value": "path/to/icon.svg",
            "metadata": {"plugin": "test"},
        }

    def test_from_dict_deserialization(self):
        """Test deserializing IconReference from dict."""
        data = {
            "type": "named",
            "value": "fa-database",
            "metadata": {},
        }
        icon = IconReference.from_dict(data)
        assert icon.icon_type == IconType.NAMED
        assert icon.value == "fa-database"
        assert icon.metadata == {}

    def test_to_string_serialization(self):
        """Test serializing IconReference to string."""
        icon = IconReference.named("fa-server")
        assert icon.to_string() == "named:fa-server"

        icon = IconReference.static("plugin/icon.svg")
        assert icon.to_string() == "static:plugin/icon.svg"

    def test_from_string_deserialization(self):
        """Test deserializing IconReference from string."""
        icon = IconReference.from_string("named:fa-server")
        assert icon.icon_type == IconType.NAMED
        assert icon.value == "fa-server"

        icon = IconReference.from_string("static:plugin/icon.svg")
        assert icon.icon_type == IconType.STATIC
        assert icon.value == "plugin/icon.svg"

    def test_from_string_backward_compatibility(self):
        """Test that plain strings without type prefix default to named icons."""
        icon = IconReference.from_string("fa-server")
        assert icon.icon_type == IconType.NAMED
        assert icon.value == "fa-server"

    def test_from_string_invalid_type(self):
        """Test that invalid type prefix falls back to named icon."""
        icon = IconReference.from_string("invalid:fa-server")
        assert icon.icon_type == IconType.NAMED
        assert icon.value == "invalid:fa-server"

    def test_get_url_named_icon(self):
        """Test URL generation for named icons."""
        icon = IconReference.named("fa-server")
        assert icon.get_url() == "fa-server"

    def test_get_url_static_icon(self):
        """Test URL generation for static icons."""
        icon = IconReference.static("plugin/icon.svg")
        assert icon.get_url() == "/static/plugin/icon.svg"

    def test_get_url_uploaded_icon(self):
        """Test URL generation for uploaded icons."""
        icon = IconReference.uploaded("user/icon.svg")
        assert icon.get_url() == "/media/icons/user/icon.svg"

    def test_str_representation(self):
        """Test string representation of IconReference."""
        icon = IconReference.named("fa-server")
        assert str(icon) == "named:fa-server"

    def test_round_trip_dict_serialization(self):
        """Test that dict serialization is reversible."""
        original = IconReference.static("test/icon.svg", plugin_name="test")
        data = original.to_dict()
        restored = IconReference.from_dict(data)
        assert restored.icon_type == original.icon_type
        assert restored.value == original.value
        assert restored.metadata == original.metadata

    def test_round_trip_string_serialization(self):
        """Test that string serialization is reversible."""
        original = IconReference.named("fa-database")
        string = original.to_string()
        restored = IconReference.from_string(string)
        assert restored.icon_type == original.icon_type
        assert restored.value == original.value
