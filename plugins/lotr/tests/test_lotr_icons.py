"""Integration tests for LOTR plugin icon assets.

Verifies that each entity type with a declared icon key has a corresponding
SVG file that resolves via staticfiles finders.
"""

import pytest
from django.apps import apps
from django.contrib.staticfiles import finders

from tap_grid.icon import resolve_icon_path
from tap_grid.models import EntityType


@pytest.fixture(autouse=True)
def register_lotr_types(db):
    """Seed LOTR EntityType records into the test DB.

    Uses the plugin manifest and model class attributes to register entity types,
    avoiding re-registration of edge constraints already in memory from app startup.
    """
    from django.utils.module_loading import import_string

    app_config = apps.get_app_config("lotr")
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

# Entity types that declare icons in plugins/lotr/apps.py
LOTR_ICON_SLUGS = ["character", "location", "artifact", "race"]

# Entity types that intentionally have no icon
LOTR_NO_ICON_SLUGS = ["faction", "sentinel", "citadel", "wanderer"]


@pytest.mark.django_db
class TestLotrIconAssets:
    @pytest.mark.parametrize("slug", LOTR_ICON_SLUGS)
    def test_icon_key_declared(self, slug: str) -> None:
        """Each iconised LOTR type has a non-empty icon key."""
        et = EntityType.objects.get(slug=slug)
        assert et.icon != "", f"{slug} should have an icon key"

    @pytest.mark.parametrize("slug", LOTR_ICON_SLUGS)
    def test_icon_resolves_to_path(self, slug: str) -> None:
        """Each iconised LOTR type resolves to a static path."""
        et = EntityType.objects.get(slug=slug)
        path = resolve_icon_path(et)
        assert path is not None, f"{slug} icon should resolve"
        assert path == f"lotr/icons/{et.icon}.svg"

    @pytest.mark.parametrize("slug", LOTR_ICON_SLUGS)
    def test_svg_file_exists_on_disk(self, slug: str) -> None:
        """Each declared icon has a real SVG file findable by staticfiles."""
        et = EntityType.objects.get(slug=slug)
        static_path = f"lotr/icons/{et.icon}.svg"
        found = finders.find(static_path)
        assert found is not None, f"SVG not found for {slug}: {static_path}"

    @pytest.mark.parametrize("slug", LOTR_ICON_SLUGS)
    def test_svg_file_is_svg(self, slug: str) -> None:
        """Each icon file is a valid SVG document."""
        et = EntityType.objects.get(slug=slug)
        static_path = f"lotr/icons/{et.icon}.svg"
        found = finders.find(static_path)
        assert found is not None
        content = open(found).read()
        assert "<svg" in content, f"{slug} icon is not a valid SVG"

    @pytest.mark.parametrize("slug", LOTR_NO_ICON_SLUGS)
    def test_no_icon_types_have_empty_key(self, slug: str) -> None:
        """Entity types without icons have an empty icon field."""
        et = EntityType.objects.get(slug=slug)
        assert et.icon == "", f"{slug} should not have an icon key"
