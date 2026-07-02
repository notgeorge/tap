"""Tests for tap_grid.icon.

Covers validate_icon_key, resolve_icon_path, and resolve_icon_url.
Icon file existence checks use Django's staticfiles finders so they
work correctly with app static directories in tests.
"""

import pytest
from django.apps import apps

from tap_grid.icon import resolve_icon_path, resolve_icon_url, validate_icon_key
from tap_grid.models import EntityType


@pytest.fixture(autouse=True)
def register_fixture_types(db):
    """Seed grid_fixtures EntityType records into the test DB.

    Uses the plugin manifest and model class attributes to register entity types,
    avoiding re-registration of edge constraints already in memory from app startup.
    """
    from django.utils.module_loading import import_string

    app_config = apps.get_app_config("grid_fixtures")
    manifest = app_config.manifest

    for entry in manifest.models:
        cls = import_string(entry.class_path)
        EntityType.objects.update_or_create(
            slug=entry.slug,
            defaults={
                "name": getattr(cls, "ENTITY_NAME", entry.slug),
                "icon": getattr(cls, "ENTITY_ICON", ""),
                "description": getattr(cls, "ENTITY_DESCRIPTION", ""),
                "plugin_name": app_config.name,
            },
        )


# ---------------------------------------------------------------------------
# validate_icon_key
# ---------------------------------------------------------------------------


class TestValidateIconKey:
    def test_simple_key(self) -> None:
        assert validate_icon_key("character") is True

    def test_kebab_key(self) -> None:
        assert validate_icon_key("map-pin") is True

    def test_key_with_digits(self) -> None:
        assert validate_icon_key("type1") is True

    def test_multi_segment_key(self) -> None:
        assert validate_icon_key("my-icon-key") is True

    def test_empty_string(self) -> None:
        assert validate_icon_key("") is False

    def test_uppercase_rejected(self) -> None:
        assert validate_icon_key("Character") is False

    def test_underscore_rejected(self) -> None:
        assert validate_icon_key("my_icon") is False

    def test_leading_hyphen_rejected(self) -> None:
        assert validate_icon_key("-icon") is False

    def test_trailing_hyphen_rejected(self) -> None:
        assert validate_icon_key("icon-") is False

    def test_path_traversal_rejected(self) -> None:
        assert validate_icon_key("../secrets") is False

    def test_slash_rejected(self) -> None:
        assert validate_icon_key("icons/character") is False

    def test_spaces_rejected(self) -> None:
        assert validate_icon_key("my icon") is False


# ---------------------------------------------------------------------------
# resolve_icon_path — uses real EntityType records and staticfiles finders
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestResolveIconPath:
    def test_constrained_source_resolves(self) -> None:
        """A fixture type with an icon key resolves to its existing SVG file."""
        et = EntityType.objects.get(slug="grid_fixtures__constrained_source")
        path = resolve_icon_path(et)
        assert path == "grid_fixtures/icons/constrained-source.svg"

    def test_constrained_target_resolves(self) -> None:
        et = EntityType.objects.get(slug="grid_fixtures__constrained_target")
        assert resolve_icon_path(et) == "grid_fixtures/icons/constrained-target.svg"

    def test_dual_endpoint_resolves(self) -> None:
        et = EntityType.objects.get(slug="grid_fixtures__dual_endpoint")
        assert resolve_icon_path(et) == "grid_fixtures/icons/dual-endpoint.svg"

    def test_outbound_blocked_resolves(self) -> None:
        et = EntityType.objects.get(slug="grid_fixtures__outbound_blocked")
        assert resolve_icon_path(et) == "grid_fixtures/icons/outbound-blocked.svg"

    def test_no_icon_returns_none(self) -> None:
        """Entity types without an icon key return None."""
        et = EntityType.objects.get(slug="grid_fixtures__peer_group")
        assert et.icon == ""
        assert resolve_icon_path(et) is None

    def test_invalid_key_returns_none(self) -> None:
        """An invalid icon key (fails validation) returns None."""
        et = EntityType.objects.get(slug="grid_fixtures__constrained_source")
        et.icon = "Bad_Key"
        assert resolve_icon_path(et) is None

    def test_missing_file_returns_none(self) -> None:
        """A valid key with no backing file on disk returns None."""
        et = EntityType.objects.get(slug="grid_fixtures__constrained_source")
        et.icon = "does-not-exist"
        assert resolve_icon_path(et) is None

    def test_unknown_plugin_name_returns_none(self) -> None:
        """If plugin_name doesn't match any AppConfig, returns None."""
        et = EntityType.objects.get(slug="grid_fixtures__constrained_source")
        et.plugin_name = "nonexistent.plugin"
        assert resolve_icon_path(et) is None


# ---------------------------------------------------------------------------
# resolve_icon_url
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestResolveIconUrl:
    def test_constrained_source_returns_url(self) -> None:
        et = EntityType.objects.get(slug="grid_fixtures__constrained_source")
        url = resolve_icon_url(et)
        assert url is not None
        assert url.endswith("grid_fixtures/icons/constrained-source.svg")

    def test_no_icon_returns_none(self) -> None:
        et = EntityType.objects.get(slug="grid_fixtures__peer_group")
        assert resolve_icon_url(et) is None
