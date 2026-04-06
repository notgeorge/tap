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
def register_lotr_types(db):
    """Seed LOTR EntityType records into the test DB.

    Calls the DB-only portion of registration directly to avoid re-registering
    edge constraints that are already in memory from app startup.
    """
    app_config = apps.get_app_config("lotr")
    for et in app_config.entity_types:
        EntityType.objects.update_or_create(
            slug=et["slug"],
            defaults={
                "name": et.get("name", et["slug"]),
                "icon": et.get("icon", ""),
                "description": et.get("description", ""),
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
    def test_character_resolves(self) -> None:
        """LOTR character has an icon key and the SVG file exists."""
        et = EntityType.objects.get(slug="character")
        path = resolve_icon_path(et)
        assert path == "lotr/icons/character.svg"

    def test_location_resolves(self) -> None:
        et = EntityType.objects.get(slug="location")
        assert resolve_icon_path(et) == "lotr/icons/location.svg"

    def test_artifact_resolves(self) -> None:
        et = EntityType.objects.get(slug="artifact")
        assert resolve_icon_path(et) == "lotr/icons/artifact.svg"

    def test_race_resolves(self) -> None:
        et = EntityType.objects.get(slug="race")
        assert resolve_icon_path(et) == "lotr/icons/race.svg"

    def test_no_icon_returns_none(self) -> None:
        """Entity types without an icon key return None."""
        et = EntityType.objects.get(slug="faction")
        assert et.icon == ""
        assert resolve_icon_path(et) is None

    def test_invalid_key_returns_none(self) -> None:
        """An invalid icon key (fails validation) returns None."""
        et = EntityType.objects.get(slug="character")
        et.icon = "Bad_Key"
        assert resolve_icon_path(et) is None

    def test_missing_file_returns_none(self) -> None:
        """A valid key with no backing file on disk returns None."""
        et = EntityType.objects.get(slug="character")
        et.icon = "does-not-exist"
        assert resolve_icon_path(et) is None

    def test_unknown_plugin_name_returns_none(self) -> None:
        """If plugin_name doesn't match any AppConfig, returns None."""
        et = EntityType.objects.get(slug="character")
        et.plugin_name = "nonexistent.plugin"
        assert resolve_icon_path(et) is None


# ---------------------------------------------------------------------------
# resolve_icon_url
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestResolveIconUrl:
    def test_character_returns_url(self) -> None:
        et = EntityType.objects.get(slug="character")
        url = resolve_icon_url(et)
        assert url is not None
        assert url.endswith("lotr/icons/character.svg")

    def test_no_icon_returns_none(self) -> None:
        et = EntityType.objects.get(slug="faction")
        assert resolve_icon_url(et) is None
