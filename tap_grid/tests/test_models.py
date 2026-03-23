"""Tests for tap_grid models — Entity, Edge, EntityType, BaseModel."""

import pytest
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured

from tap_grid.constraints import (
    _edge_property_schema_registry,
    register_edge_property_schema,
)
from tap_grid.exceptions import EdgePropertyValidationError
from tap_grid.models import Edge, Entity, EntityType
from tap_grid.registry import get_model_class, register_entity_type, resolve_entity
from tap_grid.services import create_entity
from tap_plugins.base import TapPluginConfig
from plugins.core_examples.models import Concept, Precept


@pytest.mark.django_db
class TestEntityType:
    def test_registration_is_idempotent(self):
        """TapPluginConfig.ready() uses get_or_create, so duplicates are safe."""
        EntityType.objects.get_or_create(
            slug="concept",
            defaults={"name": "Concept", "plugin_name": "test"},
        )
        EntityType.objects.get_or_create(
            slug="concept",
            defaults={"name": "Concept Changed", "plugin_name": "test"},
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
        entity = create_entity("concept", name="Least Privilege")
        concept = Concept.objects.create(entity=entity, summary="Minimize access.")
        assert concept.entity == entity

    def test_reverse_relation(self):
        """entity.concept gives the Concept for that entity."""
        entity = create_entity("concept", name="Defense in Depth")
        concept = Concept.objects.create(entity=entity, summary="Layer defenses.")
        assert entity.concept == concept

    def test_precept_works_the_same(self):
        entity = create_entity("precept", name="Use MFA")
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

    def test_get_name_default_is_empty(self):
        """Default get_name() produces an empty name on the Entity."""
        concept = Concept.objects.create(summary="No display name.")
        assert concept.entity.name == ""

    def test_get_name_override(self):
        """get_name() is called during save; overrides on the instance are respected."""
        concept = Concept(summary="Least Privilege")
        concept.get_name = lambda: f"Concept: {concept.summary}"  # type: ignore[method-assign]
        concept.save()
        assert concept.entity.name == "Concept: Least Privilege"

    def test_entity_gets_originating_grid_id(self):
        """The auto-created Entity gets originating_grid_id from its own default."""
        concept = Concept.objects.create(summary="Grid propagation check.")
        assert concept.entity.originating_grid_id is not None

    def test_edge_auto_creates_entity_with_name(self):
        """Edge.get_name() generates a label from its endpoints and type."""
        a = create_entity("concept")
        b = create_entity("precept")
        edge = Edge.objects.create(from_entity=a, to_entity=b, edge_type="APPLIES_TO")
        assert edge.entity.entity_type == "edge"
        assert str(a.pk) in edge.entity.name
        assert "APPLIES_TO" in edge.entity.name


@pytest.mark.django_db
class TestBaseModelEntityConfirmation:
    """req-grid-entity-spine-4: Explicit entity is validated on save."""

    def test_explicit_entity_with_correct_type_is_accepted(self):
        """Passing an entity with the right entity_type saves cleanly."""
        entity = create_entity("concept", name="Explicit")
        concept = Concept.objects.create(entity=entity, summary="Explicit entity path.")
        assert concept.entity == entity

    def test_explicit_entity_with_wrong_type_raises(self):
        """Passing an entity whose entity_type doesn't match raises ValueError."""
        wrong_entity = create_entity("precept", name="Wrong type")
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
class TestEdgeEndpointValidation:
    """req-grid-edge-endpoints: Edge.save() validates both endpoints before any DB write."""

    def test_missing_from_entity_raises(self):
        """Edge with a non-existent from_entity_id raises ValueError (endpoints-1)."""
        import uuid

        to_entity = create_entity("concept")
        edge = Edge(from_entity_id=uuid.uuid7(), to_entity=to_entity, edge_type="TEST")
        with pytest.raises(ValueError, match="from_entity"):
            edge.save()

    def test_missing_to_entity_raises(self):
        """Edge with a non-existent to_entity_id raises ValueError (endpoints-2)."""
        import uuid

        from_entity = create_entity("concept")
        edge = Edge(from_entity=from_entity, to_entity_id=uuid.uuid7(), edge_type="TEST")
        with pytest.raises(ValueError, match="to_entity"):
            edge.save()

    def test_validation_precedes_write_no_orphan(self):
        """A failed endpoint check leaves no orphaned Entity row on the spine (endpoints-3)."""
        import uuid

        to_entity = create_entity("concept")
        count_before = Entity.objects.count()
        edge = Edge(from_entity_id=uuid.uuid7(), to_entity=to_entity, edge_type="TEST")
        with pytest.raises(ValueError):
            edge.save()
        assert Entity.objects.count() == count_before


@pytest.mark.django_db
class TestEntityStr:
    def test_with_name(self):
        entity = create_entity("concept", name="Separation of Concerns")
        assert str(entity) == "Separation of Concerns (concept)"

    def test_without_name(self):
        entity = create_entity("concept")
        assert str(entity) == f"concept:{entity.pk}"


@pytest.mark.django_db
class TestEdgePropertyValidation:
    """req-grid-edge-properties: Edge.save() enforces property schema on create and update."""

    @pytest.fixture(autouse=True)
    def isolate_registry(self) -> None:
        saved = _edge_property_schema_registry.all()
        _edge_property_schema_registry._reset_for_testing()
        yield
        _edge_property_schema_registry._reset_for_testing(saved)

    def test_valid_properties_on_create_pass(self):
        """Edge creation succeeds when properties match the registered schema (properties-4)."""
        register_edge_property_schema(
            "PROP_EDGE",
            {"type": "object", "required": ["label"], "properties": {"label": {"type": "string"}}},
        )
        a = create_entity("concept")
        b = create_entity("concept")
        edge = Edge(from_entity=a, to_entity=b, edge_type="PROP_EDGE", properties={"label": "ok"})
        edge.save()
        assert edge.pk is not None

    def test_invalid_properties_on_create_raise(self):
        """Edge creation fails when properties violate the registered schema (properties-4, properties-8)."""
        register_edge_property_schema(
            "PROP_EDGE_STRICT",
            {"type": "object", "required": ["count"], "properties": {"count": {"type": "integer"}}},
        )
        a = create_entity("concept")
        b = create_entity("concept")
        edge = Edge(from_entity=a, to_entity=b, edge_type="PROP_EDGE_STRICT", properties={"count": "bad"})
        with pytest.raises(EdgePropertyValidationError):
            edge.save()

    def test_no_orphan_entity_on_invalid_properties(self):
        """A failed property check leaves no orphaned Entity row on the spine."""
        register_edge_property_schema(
            "PROP_EDGE_ORPHAN",
            {"type": "object", "required": ["x"], "properties": {"x": {"type": "integer"}}},
        )
        a = create_entity("concept")
        b = create_entity("concept")
        count_before = Entity.objects.count()
        edge = Edge(from_entity=a, to_entity=b, edge_type="PROP_EDGE_ORPHAN", properties={})
        with pytest.raises(EdgePropertyValidationError):
            edge.save()
        assert Entity.objects.count() == count_before

    def test_valid_properties_on_update_pass(self):
        """Edge.save() on an existing edge accepts valid updated properties (properties-5)."""
        register_edge_property_schema(
            "PROP_EDGE_UPDATE",
            {"type": "object", "properties": {"note": {"type": "string"}}},
        )
        a = create_entity("concept")
        b = create_entity("concept")
        edge = Edge.objects.create(from_entity=a, to_entity=b, edge_type="PROP_EDGE_UPDATE", properties={})
        edge.properties = {"note": "updated"}
        edge.save(update_fields=["properties"])
        edge.refresh_from_db()
        assert edge.properties == {"note": "updated"}

    def test_invalid_properties_on_update_raise(self):
        """Edge.save() on an existing edge rejects invalid updated properties (properties-5, properties-8)."""
        register_edge_property_schema(
            "PROP_EDGE_UPDATE_FAIL",
            {"type": "object", "properties": {"note": {"type": "string"}}},
        )
        a = create_entity("concept")
        b = create_entity("concept")
        edge = Edge.objects.create(
            from_entity=a, to_entity=b, edge_type="PROP_EDGE_UPDATE_FAIL", properties={"note": "ok"}
        )
        edge.properties = {"note": 999}  # wrong type
        with pytest.raises(EdgePropertyValidationError):
            edge.save(update_fields=["properties"])

    def test_no_schema_allows_any_properties(self):
        """When no schema is registered, any properties are accepted (properties-6, properties-7)."""
        a = create_entity("concept")
        b = create_entity("concept")
        edge = Edge(from_entity=a, to_entity=b, edge_type="NO_SCHEMA_EDGE", properties={"anything": [1, None]})
        edge.save()
        assert edge.pk is not None
