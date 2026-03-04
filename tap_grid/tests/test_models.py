"""Tests for tap_grid models — Entity, Edge, EntityType, BaseModel."""

import pytest
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured

from tap_grid.models import Edge, Entity, EntityType
from tap_grid.registry import _ENTITY_MODEL_REGISTRY, get_model_class, register_entity_type, resolve_entity
from tap_grid.services import create_edge, create_entity
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
    """Existing tests — verify the explicit-entity path still works (req-grid-entity-base-4)."""

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
class TestBaseModelAutoCreation:
    """req-grid-entity-base: BaseModel.save() auto-creates its Entity (spine-3 / base-1)."""

    def test_concept_auto_creates_entity(self):
        """Saving a Concept without an entity creates one automatically."""
        concept = Concept.objects.create(summary="Auto-created entity test.")
        assert concept.entity_id is not None
        assert concept.entity.entity_type == "concept"

    def test_auto_created_entity_on_spine(self):
        """The auto-created Entity actually exists in the Entity table."""
        concept = Concept.objects.create(summary="Check spine.")
        assert Entity.objects.filter(pk=concept.entity_id).exists()

    def test_precept_auto_creates_entity(self):
        precept = Precept.objects.create(statement="Always verify.")
        assert precept.entity.entity_type == "precept"

    def test_get_display_name_default_is_empty(self):
        """Default get_display_name() produces an empty display_name on the Entity."""
        concept = Concept.objects.create(summary="No display name.")
        assert concept.entity.display_name == ""

    def test_get_display_name_override(self):
        """get_display_name() is called during save; overrides on the instance are respected."""
        concept = Concept(summary="Least Privilege")
        concept.get_display_name = lambda: f"Concept: {concept.summary}"  # type: ignore[method-assign]
        concept.save()
        assert concept.entity.display_name == "Concept: Least Privilege"

    def test_originating_grid_id_propagated_to_entity(self):
        """The auto-created Entity gets the same originating_grid_id as the domain model."""
        concept = Concept.objects.create(summary="Grid propagation check.")
        assert concept.entity.originating_grid_id == concept.originating_grid_id

    def test_edge_auto_creates_entity_with_display_name(self):
        """Edge.get_display_name() generates a label from its endpoints and type."""
        a = create_entity("concept")
        b = create_entity("precept")
        edge = Edge.objects.create(from_entity=a, to_entity=b, edge_type="APPLIES_TO")
        assert edge.entity.entity_type == "edge"
        assert str(a.pk) in edge.entity.display_name
        assert "APPLIES_TO" in edge.entity.display_name


@pytest.mark.django_db
class TestBaseModelEntityConfirmation:
    """req-grid-entity-spine-4: Explicit entity is validated on save."""

    def test_explicit_entity_with_correct_type_is_accepted(self):
        """Passing an entity with the right entity_type saves cleanly."""
        entity = create_entity("concept", display_name="Explicit")
        concept = Concept.objects.create(entity=entity, summary="Explicit entity path.")
        assert concept.entity == entity

    def test_explicit_entity_with_wrong_type_raises(self):
        """Passing an entity whose entity_type doesn't match raises ValueError."""
        wrong_entity = create_entity("precept", display_name="Wrong type")
        with pytest.raises(ValueError, match="entity_type does not match"):
            Concept.objects.create(entity=wrong_entity, summary="Should fail.")

    def test_nonexistent_entity_id_raises(self):
        """Saving with a non-existent entity_id raises ValueError."""
        import uuid

        concept = Concept(summary="Ghost entity.")
        concept.entity_id = uuid.uuid7()  # valid UUID but not in DB
        with pytest.raises(ValueError, match="does not exist on the spine"):
            concept.save()


@pytest.mark.django_db
class TestEntityResolve:
    """req-grid-entity-resolve: Entity.resolve() and resolve_entity()."""

    def test_resolve_returns_concept(self):
        """entity.resolve() returns the Concept for a concept entity."""
        concept = Concept.objects.create(summary="Resolve me.")
        resolved = concept.entity.resolve()
        assert isinstance(resolved, Concept)
        assert resolved.pk == concept.pk

    def test_resolve_returns_precept(self):
        precept = Precept.objects.create(statement="Resolve precept.")
        resolved = precept.entity.resolve()
        assert isinstance(resolved, Precept)
        assert resolved.pk == precept.pk

    def test_resolve_returns_edge(self):
        """entity.resolve() works for edge entities (req-grid-entity-resolve-4)."""
        a = create_entity("concept")
        b = create_entity("precept")
        edge = Edge.objects.create(from_entity=a, to_entity=b, edge_type="APPLIES_TO")
        resolved = edge.entity.resolve()
        assert isinstance(resolved, Edge)
        assert resolved.pk == edge.pk

    def test_resolve_entity_by_id(self):
        """resolve_entity(uuid) resolves from an entity_id alone (req-grid-entity-resolve-2)."""
        concept = Concept.objects.create(summary="Resolve by ID.")
        resolved = resolve_entity(concept.entity_id)
        assert isinstance(resolved, Concept)
        assert resolved.pk == concept.pk

    def test_resolve_unregistered_type_raises(self):
        """Resolving an unknown entity_type raises KeyError (req-grid-entity-resolve-3)."""
        entity = create_entity("unknown_type_xyz")
        with pytest.raises(KeyError, match="unknown_type_xyz"):
            entity.resolve()


class TestModelRegistry:
    """req-grid-entity-type: ENTITY_TYPE registration at class definition time."""

    def test_concept_registered(self):
        assert get_model_class("concept") is Concept

    def test_precept_registered(self):
        assert get_model_class("precept") is Precept

    def test_edge_registered(self):
        assert get_model_class("edge") is Edge

    def test_duplicate_type_raises(self):
        """Registering the same entity_type for a different class raises ImproperlyConfigured."""
        with pytest.raises(ImproperlyConfigured, match="already registered"):
            register_entity_type("concept", Precept)

    def test_same_class_re_registration_is_safe(self):
        """Re-registering the same class for the same type is idempotent."""
        register_entity_type("concept", Concept)  # should not raise


@pytest.mark.django_db
class TestEntityStr:
    def test_with_display_name(self):
        entity = create_entity("concept", display_name="Separation of Concerns")
        assert str(entity) == "Separation of Concerns (concept)"

    def test_without_display_name(self):
        entity = create_entity("concept")
        assert str(entity) == f"concept:{entity.pk}"
