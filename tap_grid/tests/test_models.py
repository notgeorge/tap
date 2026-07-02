"""Tests for tap_grid models — Entity, Edge, EntityType, BaseModel."""

import pytest
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured

from tap_plugin.lotr.models import Character, Location
from tap_grid.constraints import (
    _edge_property_schema_registry,
    register_edge_property_schema,
)
from tap_grid.exceptions import EdgePropertyValidationError
from tap_grid.models import BaseModel, Edge, Entity, EntityType
from tap_grid.registry import get_model_class, register_entity_type, resolve_entity
from tap_grid.services import create_entity
from tap_plugins.base import TapPluginConfig


class TestBaseModelDisplayNameContract:
    def test_name_field_models_override_get_name(self):
        """A model-level name field must be the source for Entity.name sync."""
        missing = []
        for model_cls in apps.get_models():
            if not isinstance(model_cls, type):
                continue
            if not issubclass(model_cls, BaseModel) or model_cls._meta.abstract:
                continue
            field_names = {field.name for field in model_cls._meta.fields}
            if "name" in field_names and "get_name" not in model_cls.__dict__:
                missing.append(f"{model_cls.__module__}.{model_cls.__name__}")

        assert missing == []


@pytest.mark.django_db
class TestEntityType:
    def test_registration_is_idempotent(self):
        """TapPluginConfig.ready() uses get_or_create, so duplicates are safe."""
        EntityType.objects.get_or_create(
            slug="character",
            defaults={"name": "Character", "plugin_name": "test"},
        )
        EntityType.objects.get_or_create(
            slug="character",
            defaults={"name": "Character Changed", "plugin_name": "test"},
        )
        assert EntityType.objects.filter(slug="character").count() == 1

    def test_types_registered_by_lotr(self):
        """The lotr plugin registers character, location, artifact, LOCATED_IN, WIELDS, etc."""
        from tap_grid.registry import get_model_class

        app_config = apps.get_app_config("lotr")
        assert isinstance(app_config, TapPluginConfig)
        # Types are registered in the in-memory model registry by ready()
        for entity_type in ("character", "location", "artifact"):
            assert get_model_class(entity_type) is not None


@pytest.mark.django_db
class TestBaseModel:
    """Existing tests — verify the explicit-entity path still works (req-grid-entity-base-4)."""

    def test_character_inherits_basemodel_fields(self):
        entity = create_entity("character", name="Frodo Baggins")
        character = Character.objects.create(entity=entity, bio="A hobbit from the Shire.")
        assert character.entity == entity

    def test_reverse_relation(self):
        """entity.character gives the Character for that entity."""
        entity = create_entity("character", name="Gandalf")
        character = Character.objects.create(entity=entity, bio="A wizard.")
        assert entity.character == character

    def test_location_works_the_same(self):
        entity = create_entity("location", name="The Shire")
        location = Location.objects.create(entity=entity, description="A peaceful land.")
        assert entity.location == location


@pytest.mark.django_db
class TestBaseModelAutoCreation:
    """req-grid-entity-base: BaseModel.save() auto-creates its Entity (spine-3 / base-1)."""

    def test_character_auto_creates_entity(self):
        """Saving a Character without an entity creates one automatically."""
        character = Character.objects.create(bio="Auto-created entity test.")
        assert character.entity_id is not None
        assert character.entity.entity_type == "character"

    def test_auto_created_entity_on_spine(self):
        """The auto-created Entity actually exists in the Entity table."""
        character = Character.objects.create(bio="Check spine.")
        assert Entity.objects.filter(pk=character.entity_id).exists()

    def test_location_auto_creates_entity(self):
        location = Location.objects.create(description="Always verify.")
        assert location.entity.entity_type == "location"

    def test_get_name_default_is_empty(self):
        """Default get_name() produces an empty name on the Entity."""
        character = Character.objects.create(bio="No display name.")
        assert character.entity.name == ""

    def test_get_name_override(self):
        """get_name() is called during save; overrides on the instance are respected."""
        character = Character(bio="Fellowship")
        character.get_name = lambda: f"Character: {character.bio}"  # type: ignore[method-assign]
        character.save()
        assert character.entity.name == "Character: Fellowship"

    def test_entity_gets_originating_grid_id(self):
        """The auto-created Entity gets originating_grid_id from its own default."""
        character = Character.objects.create(bio="Grid propagation check.")
        assert character.entity.originating_grid_id is not None

    def test_edge_auto_creates_entity_with_name(self):
        """Edge.get_name() generates a label from its endpoints and type."""
        a = create_entity("character")
        b = create_entity("location")
        edge = Edge.objects.create(from_entity=a, to_entity=b, edge_type="LOCATED_IN")
        assert edge.entity.entity_type == "edge"
        assert str(a.pk) in edge.entity.name
        assert "LOCATED_IN" in edge.entity.name


@pytest.mark.django_db
class TestBaseModelEntityConfirmation:
    """req-grid-entity-spine-4: Explicit entity is validated on save."""

    def test_explicit_entity_with_correct_type_is_accepted(self):
        """Passing an entity with the right entity_type saves cleanly."""
        entity = create_entity("character", name="Explicit")
        character = Character.objects.create(entity=entity, bio="Explicit entity path.")
        assert character.entity == entity

    def test_explicit_entity_with_wrong_type_raises(self):
        """Passing an entity whose entity_type doesn't match raises ValueError."""
        wrong_entity = create_entity("location", name="Wrong type")
        with pytest.raises(ValueError, match="entity_type does not match"):
            Character.objects.create(entity=wrong_entity, bio="Should fail.")

    def test_nonexistent_entity_id_raises(self):
        """Saving with a non-existent entity_id raises ValueError."""
        import uuid

        character = Character(bio="Ghost entity.")
        character.entity_id = uuid.uuid7()  # valid UUID but not in DB
        with pytest.raises(ValueError, match="does not exist on the spine"):
            character.save()


@pytest.mark.django_db
class TestEntityResolve:
    """req-grid-entity-resolve: Entity.resolve() and resolve_entity()."""

    def test_resolve_returns_character(self):
        """entity.resolve() returns the Character for a character entity."""
        character = Character.objects.create(bio="Resolve me.")
        resolved = character.entity.resolve()
        assert isinstance(resolved, Character)
        assert resolved.pk == character.pk

    def test_resolve_returns_location(self):
        location = Location.objects.create(description="Resolve location.")
        resolved = location.entity.resolve()
        assert isinstance(resolved, Location)
        assert resolved.pk == location.pk

    def test_resolve_returns_edge(self):
        """entity.resolve() works for edge entities (req-grid-entity-resolve-4)."""
        a = create_entity("character")
        b = create_entity("location")
        edge = Edge.objects.create(from_entity=a, to_entity=b, edge_type="LOCATED_IN")
        resolved = edge.entity.resolve()
        assert isinstance(resolved, Edge)
        assert resolved.pk == edge.pk

    def test_resolve_entity_by_id(self):
        """resolve_entity(uuid) resolves from an entity_id alone (req-grid-entity-resolve-2)."""
        character = Character.objects.create(bio="Resolve by ID.")
        resolved = resolve_entity(character.entity_id)
        assert isinstance(resolved, Character)
        assert resolved.pk == character.pk

    def test_resolve_unregistered_type_raises(self):
        """Resolving an unknown entity_type raises KeyError (req-grid-entity-resolve-3)."""
        entity = create_entity("unknown_type_xyz")
        with pytest.raises(KeyError, match="unknown_type_xyz"):
            entity.resolve()


class TestModelRegistry:
    """req-grid-entity-type: ENTITY_TYPE registration at class definition time."""

    def test_character_registered(self):
        assert get_model_class("character") is Character

    def test_location_registered(self):
        assert get_model_class("location") is Location

    def test_edge_registered(self):
        assert get_model_class("edge") is Edge

    def test_duplicate_type_raises(self):
        """Registering the same entity_type for a different class raises ImproperlyConfigured."""
        with pytest.raises(ImproperlyConfigured, match="already registered"):
            register_entity_type("character", Location)

    def test_same_class_re_registration_is_safe(self):
        """Re-registering the same class for the same type is idempotent."""
        register_entity_type("character", Character)  # should not raise


@pytest.mark.django_db
class TestEdgeEndpointValidation:
    """req-grid-edge-endpoints: Edge.save() validates both endpoints before any DB write."""

    def test_missing_from_entity_raises(self):
        """Edge with a non-existent from_entity_id raises ValueError (endpoints-1)."""
        import uuid

        to_entity = create_entity("character")
        edge = Edge(from_entity_id=uuid.uuid7(), to_entity=to_entity, edge_type="TEST")
        with pytest.raises(ValueError, match="from_entity"):
            edge.save()

    def test_missing_to_entity_raises(self):
        """Edge with a non-existent to_entity_id raises ValueError (endpoints-2)."""
        import uuid

        from_entity = create_entity("character")
        edge = Edge(from_entity=from_entity, to_entity_id=uuid.uuid7(), edge_type="TEST")
        with pytest.raises(ValueError, match="to_entity"):
            edge.save()

    def test_validation_precedes_write_no_orphan(self):
        """A failed endpoint check leaves no orphaned Entity row on the spine (endpoints-3)."""
        import uuid

        to_entity = create_entity("character")
        count_before = Entity.objects.count()
        edge = Edge(from_entity_id=uuid.uuid7(), to_entity=to_entity, edge_type="TEST")
        with pytest.raises(ValueError):
            edge.save()
        assert Entity.objects.count() == count_before


@pytest.mark.django_db
class TestEntityStr:
    def test_with_name(self):
        entity = create_entity("character", name="Frodo Baggins")
        assert str(entity) == "Frodo Baggins (character)"

    def test_without_name(self):
        entity = create_entity("character")
        assert str(entity) == f"character:{entity.pk}"


@pytest.mark.django_db
class TestEdgePropertyValidation:
    """req-grid-edge-properties: Edge.save() enforces property schema on create and update.

    Uses wanderer entities — they have no OUTBOUND_EDGES/INBOUND_EDGES constraints,
    so test-only edge types (PROP_EDGE, etc.) are accepted without constraint errors.
    """

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
        a = create_entity("wanderer")
        b = create_entity("wanderer")
        edge = Edge(from_entity=a, to_entity=b, edge_type="PROP_EDGE", properties={"label": "ok"})
        edge.save()
        assert edge.pk is not None

    def test_invalid_properties_on_create_raise(self):
        """Edge creation fails when properties violate the registered schema (properties-4, properties-8)."""
        register_edge_property_schema(
            "PROP_EDGE_STRICT",
            {"type": "object", "required": ["count"], "properties": {"count": {"type": "integer"}}},
        )
        a = create_entity("wanderer")
        b = create_entity("wanderer")
        edge = Edge(from_entity=a, to_entity=b, edge_type="PROP_EDGE_STRICT", properties={"count": "bad"})
        with pytest.raises(EdgePropertyValidationError):
            edge.save()

    def test_no_orphan_entity_on_invalid_properties(self):
        """A failed property check leaves no orphaned Entity row on the spine."""
        register_edge_property_schema(
            "PROP_EDGE_ORPHAN",
            {"type": "object", "required": ["x"], "properties": {"x": {"type": "integer"}}},
        )
        a = create_entity("wanderer")
        b = create_entity("wanderer")
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
        a = create_entity("wanderer")
        b = create_entity("wanderer")
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
        a = create_entity("wanderer")
        b = create_entity("wanderer")
        edge = Edge.objects.create(
            from_entity=a, to_entity=b, edge_type="PROP_EDGE_UPDATE_FAIL", properties={"note": "ok"}
        )
        edge.properties = {"note": 999}  # wrong type
        with pytest.raises(EdgePropertyValidationError):
            edge.save(update_fields=["properties"])

    def test_no_schema_allows_any_properties(self):
        """When no schema is registered, any properties are accepted (properties-6, properties-7)."""
        a = create_entity("wanderer")
        b = create_entity("wanderer")
        edge = Edge(from_entity=a, to_entity=b, edge_type="NO_SCHEMA_EDGE", properties={"anything": [1, None]})
        edge.save()
        assert edge.pk is not None


# ---------------------------------------------------------------------------
# Tombstone-aware managers: req-grid-entity-tombstone-managers
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEntityTombstoneFilters:
    """`.live()` and `.tombstoned()` on Entity manager + queryset.

    Locks req-grid-entity-tombstone-managers acceptance criteria 2-4: the
    Entity default manager returns both live and tombstoned rows; the
    chainable filters narrow correctly; defaults are unchanged.
    """

    def _tombstone(self, entity):
        """Mark an entity tombstoned via direct ORM update (bypasses the
        service layer; this is a low-level manager test)."""
        from django.utils import timezone

        Entity.objects.filter(pk=entity.pk).update(deleted_at=timezone.now())

    def test_default_manager_returns_both_live_and_tombstoned(self):
        live = create_entity("character", name="Live")
        dead = create_entity("character", name="Dead")
        self._tombstone(dead)
        pks = set(Entity.objects.filter(pk__in=[live.pk, dead.pk]).values_list("pk", flat=True))
        assert pks == {live.pk, dead.pk}

    def test_live_filter_excludes_tombstoned(self):
        live = create_entity("character", name="Live")
        dead = create_entity("character", name="Dead")
        self._tombstone(dead)
        pks = set(Entity.objects.live().filter(pk__in=[live.pk, dead.pk]).values_list("pk", flat=True))
        assert pks == {live.pk}

    def test_tombstoned_filter_excludes_live(self):
        live = create_entity("character", name="Live")
        dead = create_entity("character", name="Dead")
        self._tombstone(dead)
        pks = set(Entity.objects.tombstoned().filter(pk__in=[live.pk, dead.pk]).values_list("pk", flat=True))
        assert pks == {dead.pk}

    def test_filters_chain_with_normal_queryset_operations(self):
        a = create_entity("character", name="Aragorn")
        b = create_entity("character", name="Boromir")
        self._tombstone(b)
        names = set(
            Entity.objects.live()
            .filter(pk__in=[a.pk, b.pk])
            .filter(entity_type="character")
            .values_list("name", flat=True)
        )
        assert names == {"Aragorn"}


@pytest.mark.django_db
class TestBaseModelTombstoneFilters:
    """`.live()` and `.tombstoned()` on BaseModel subclass managers.

    Locks req-grid-entity-tombstone-managers-3 / -4 / -5: both `objects`
    (LiveManager) and `all_objects` expose the chainables; defaults are
    unchanged; LiveManager itself uses `.live()` internally.
    """

    def _tombstone(self, instance):
        from django.utils import timezone

        Entity.objects.filter(pk=instance.entity_id).update(deleted_at=timezone.now())

    def test_default_live_manager_excludes_tombstoned(self):
        from tap_plugin.lotr.models import Character

        a = Character.objects.create(name="Frodo", bio="ringbearer")
        b = Character.objects.create(name="Gollum", bio="precious")
        self._tombstone(b)
        names = set(Character.objects.filter(pk__in=[a.pk, b.pk]).values_list("name", flat=True))
        assert names == {"Frodo"}

    def test_all_objects_returns_both(self):
        from tap_plugin.lotr.models import Character

        a = Character.objects.create(name="Sam", bio="gardener")
        b = Character.objects.create(name="Lobelia", bio="thief")
        self._tombstone(b)
        names = set(Character.all_objects.filter(pk__in=[a.pk, b.pk]).values_list("name", flat=True))
        assert names == {"Sam", "Lobelia"}

    def test_all_objects_live_narrows_to_live(self):
        from tap_plugin.lotr.models import Character

        a = Character.objects.create(name="Pippin", bio="took")
        b = Character.objects.create(name="Saruman", bio="fallen")
        self._tombstone(b)
        names = set(Character.all_objects.live().filter(pk__in=[a.pk, b.pk]).values_list("name", flat=True))
        assert names == {"Pippin"}

    def test_all_objects_tombstoned_returns_only_tombstoned(self):
        from tap_plugin.lotr.models import Character

        a = Character.objects.create(name="Merry", bio="brandybuck")
        b = Character.objects.create(name="Wormtongue", bio="schemer")
        self._tombstone(b)
        names = set(Character.all_objects.tombstoned().filter(pk__in=[a.pk, b.pk]).values_list("name", flat=True))
        assert names == {"Wormtongue"}

    def test_objects_tombstoned_composes_with_live_manager_and_returns_empty(self):
        """Chained filter composition: LiveManager + .tombstoned() = always empty.

        `Character.objects` is `LiveManager`, whose get_queryset() applies
        `.live()` (entity__deleted_at__isnull=True). Chaining `.tombstoned()`
        on top adds the opposite predicate (entity__deleted_at__isnull=False).
        The two predicates AND together to never-true, so the result is the
        empty set.

        This is honest QuerySet composition — chained filters compose, they
        don't replace each other. For BaseModel-subclass tombstone queries
        the canonical surface is `Model.all_objects.tombstoned()`. See the
        gotcha called out in `req-grid-entity-tombstone-managers`.
        """
        from tap_plugin.lotr.models import Character

        a = Character.objects.create(name="Galadriel", bio="elf")
        b = Character.objects.create(name="Witch-King", bio="nazgul")
        self._tombstone(b)
        assert Character.objects.tombstoned().filter(pk__in=[a.pk, b.pk]).count() == 0
