"""Tests for tap_core models — Entity, Edge, EntityType, BaseModel."""

import uuid

import pytest

from django.apps import apps

from tap_core.icon_types import IconReference, IconType
from tap_core.models import Entity, EntityType
from tap_core.services import create_entity
from tap_core.tests.test_plugin.models import Concept, Precept


@pytest.mark.django_db
class TestEntityType:
    def test_registration_is_idempotent(self):
        """TapPluginConfig.ready() uses get_or_create, so duplicates are safe."""
        EntityType.objects.get_or_create(
            slug="concept",
            defaults={"display_name": "Concept", "plugin_name": "test"},
        )
        EntityType.objects.get_or_create(
            slug="concept",
            defaults={"display_name": "Concept Changed", "plugin_name": "test"},
        )
        assert EntityType.objects.filter(slug="concept").count() == 1

    def test_types_registered_by_test_plugin(self):
        """The test plugin registers concept, precept, applies_to, depends_on."""
        # ready() ran against the real DB; re-register against the test DB
        app_config = apps.get_app_config("test_plugin")
        app_config._register_types()
        slugs = set(EntityType.objects.values_list("slug", flat=True))
        assert {"concept", "precept", "applies_to", "depends_on"}.issubset(slugs)

    def test_get_icon_reference_from_icon_data(self):
        """Test get_icon_reference prefers icon_data over icon."""
        entity_type = EntityType.objects.create(
            slug="test_type",
            display_name="Test Type",
            icon="named:fa-old",
            icon_data={"type": "named", "value": "fa-new", "metadata": {}},
        )
        icon_ref = entity_type.get_icon_reference()
        assert icon_ref is not None
        assert icon_ref.icon_type == IconType.NAMED
        assert icon_ref.value == "fa-new"

    def test_get_icon_reference_from_icon_charfield(self):
        """Test get_icon_reference falls back to icon CharField."""
        entity_type = EntityType.objects.create(
            slug="test_type2",
            display_name="Test Type 2",
            icon="static:plugin/icon.svg",
        )
        icon_ref = entity_type.get_icon_reference()
        assert icon_ref is not None
        assert icon_ref.icon_type == IconType.STATIC
        assert icon_ref.value == "plugin/icon.svg"

    def test_get_icon_reference_no_icon(self):
        """Test get_icon_reference returns None when no icon is set."""
        entity_type = EntityType.objects.create(
            slug="test_type3",
            display_name="Test Type 3",
        )
        assert entity_type.get_icon_reference() is None

    def test_set_icon_reference(self):
        """Test set_icon_reference updates both icon_data and icon."""
        entity_type = EntityType.objects.create(
            slug="test_type4",
            display_name="Test Type 4",
        )
        icon_ref = IconReference.named("fa-database")
        entity_type.set_icon_reference(icon_ref)

        assert entity_type.icon_data == {"type": "named", "value": "fa-database", "metadata": {}}
        assert entity_type.icon == "named:fa-database"

    def test_get_icon_url(self):
        """Test get_icon_url returns correct URL for icon."""
        entity_type = EntityType.objects.create(
            slug="test_type5",
            display_name="Test Type 5",
            icon="named:fa-server",
        )
        assert entity_type.get_icon_url() == "fa-server"

    def test_get_icon_url_no_icon(self):
        """Test get_icon_url returns empty string when no icon is set."""
        entity_type = EntityType.objects.create(
            slug="test_type6",
            display_name="Test Type 6",
        )
        assert entity_type.get_icon_url() == ""


@pytest.mark.django_db
class TestBaseModel:
    def test_concept_inherits_basemodel_fields(self):
        entity = create_entity("concept", display_name="Least Privilege")
        # Create concept with explicit originating_grid_id since TAP_GRID_ID may not be set in tests
        test_grid_id = uuid.uuid4()
        concept = Concept.objects.create(entity=entity, summary="Minimize access.", originating_grid_id=test_grid_id)
        assert concept.created_at is not None
        assert concept.updated_at is not None
        assert concept.originating_grid_id == test_grid_id
        assert concept.entity == entity

    def test_reverse_relation(self):
        """entity.concept gives the Concept for that entity."""
        entity = create_entity("concept", display_name="Defense in Depth")
        concept = Concept.objects.create(entity=entity, summary="Layer defenses.")
        assert entity.concept == concept

    def test_precept_works_the_same(self):
        entity = create_entity("precept", display_name="Use MFA")
        precept = Precept.objects.create(entity=entity, statement="Require multi-factor auth.")
        assert entity.precept == precept


@pytest.mark.django_db
class TestEntityStr:
    def test_with_display_name(self):
        entity = create_entity("concept", display_name="Separation of Concerns")
        assert str(entity) == "Separation of Concerns (concept)"

    def test_without_display_name(self):
        entity = create_entity("concept")
        assert str(entity) == f"concept:{entity.pk}"
