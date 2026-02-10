"""Tests for tap_core models — Entity, Edge, EntityType, BaseModel."""

import pytest
from django.apps import apps

from tap_core.models import EntityType
from tap_core.services import create_entity
from tap_plugins.base import TapPluginConfig
from tap_plugins.core_examples.models import Concept, Precept


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

    def test_types_registered_by_core_examples(self):
        """The core_examples plugin registers concept, precept, APPLIES_TO, DEPENDS_ON."""
        # ready() ran against the real DB; re-register against the test DB
        app_config = apps.get_app_config("core_examples")
        assert isinstance(app_config, TapPluginConfig)
        app_config._register_types()
        slugs = set(EntityType.objects.values_list("slug", flat=True))
        assert {"concept", "precept", "APPLIES_TO", "DEPENDS_ON"}.issubset(slugs)


@pytest.mark.django_db
class TestBaseModel:
    def test_concept_inherits_basemodel_fields(self):
        entity = create_entity("concept", display_name="Least Privilege")
        concept = Concept.objects.create(entity=entity, summary="Minimize access.")
        assert concept.created_at is not None
        assert concept.updated_at is not None
        assert concept.originating_grid_id is not None
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
