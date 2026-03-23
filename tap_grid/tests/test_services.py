"""Tests for tap_grid.services — the canonical mutation API."""

import pytest

from tap_grid.constraints import (
    _edge_property_schema_registry,
    register_edge_property_schema,
)
from tap_grid.exceptions import EdgePropertyValidationError, InvalidEdgeError
from tap_grid.models import Edge, Entity
from tap_grid.services import (
    create_edge,
    create_entity,
    delete_edge,
    delete_entity,
    update_edge_properties,
    update_entity,
)
from plugins.core_examples.models import Concept


@pytest.mark.django_db
class TestCreateEntity:
    def test_creates_with_type_and_name(self):
        entity = create_entity("concept", name="Least Privilege")
        assert entity.entity_type == "concept"
        assert entity.name == "Least Privilege"
        assert entity.pk is not None

    def test_auto_generates_uuid7(self):
        e1 = create_entity("concept")
        e2 = create_entity("concept")
        assert e1.pk != e2.pk
        # UUIDv7 is time-ordered: second should sort after first
        assert str(e2.pk) > str(e1.pk)

    def test_stamps_grid_id(self):
        entity = create_entity("concept")
        assert entity.originating_grid_id is not None


@pytest.mark.django_db
class TestUpdateEntity:
    def test_updates_fields(self):
        entity = create_entity("concept", name="Old Name")
        updated = update_entity(entity, name="New Name")
        assert updated.name == "New Name"
        entity.refresh_from_db()
        assert entity.name == "New Name"


@pytest.mark.django_db
class TestDeleteEntity:
    def test_deletes_entity(self):
        entity = create_entity("concept")
        pk = entity.pk
        delete_entity(entity)
        assert not Entity.objects.filter(pk=pk).exists()

    def test_cascades_to_edges(self):
        a = create_entity("concept", name="A")
        b = create_entity("precept", name="B")
        edge = create_edge(a, b, "APPLIES_TO")
        delete_entity(a)
        # Edge should be gone (from_entity cascade)
        assert not Edge.objects.filter(pk=edge.pk).exists()

    def test_cascades_to_domain_model(self):
        entity = create_entity("concept", name="Separation of Concerns")
        Concept.objects.create(entity=entity, summary="Keep things separate.")
        delete_entity(entity)
        assert not Concept.objects.filter(entity_id=entity.pk).exists()


@pytest.mark.django_db
class TestCreateEdge:
    def test_creates_edge_with_backing_entity(self):
        a = create_entity("concept")
        b = create_entity("precept")
        edge = create_edge(a, b, "APPLIES_TO")
        assert edge.from_entity == a
        assert edge.to_entity == b
        assert edge.edge_type == "APPLIES_TO"
        # Edge has a backing Entity
        assert edge.entity is not None
        assert edge.entity.entity_type == "edge"

    def test_edge_properties(self):
        a = create_entity("concept")
        b = create_entity("concept")
        edge = create_edge(a, b, "DEPENDS_ON", properties={"strength": "strong"})
        assert edge.properties == {"strength": "strong"}

    def test_depends_on_between_concepts(self):
        concept_a = create_entity("concept", name="Defense in Depth")
        concept_b = create_entity("concept", name="Least Privilege")
        edge = create_edge(concept_a, concept_b, "DEPENDS_ON")
        assert edge.edge_type == "DEPENDS_ON"


@pytest.mark.django_db
class TestDeleteEdge:
    def test_deletes_edge_and_backing_entity(self):
        a = create_entity("concept")
        b = create_entity("precept")
        edge = create_edge(a, b, "APPLIES_TO")
        backing_entity_pk = edge.entity.pk
        delete_edge(edge)
        assert not Edge.objects.filter(pk=edge.pk).exists()
        assert not Entity.objects.filter(pk=backing_entity_pk).exists()

    def test_source_entities_survive(self):
        a = create_entity("concept")
        b = create_entity("precept")
        edge = create_edge(a, b, "APPLIES_TO")
        delete_edge(edge)
        # The endpoints should still exist
        assert Entity.objects.filter(pk=a.pk).exists()
        assert Entity.objects.filter(pk=b.pk).exists()


@pytest.mark.django_db
class TestNoEdgesBetweenEdges:
    """req-grid-edge-nono: create_edge() rejects edges whose endpoints are themselves edges."""

    def test_edge_as_from_entity_raises(self):
        """create_edge() raises InvalidEdgeError when from_entity is an edge (nono-1)."""
        a = create_entity("concept")
        b = create_entity("precept")
        edge = create_edge(a, b, "APPLIES_TO")
        c = create_entity("concept")
        with pytest.raises(InvalidEdgeError, match="from_entity is an edge"):
            create_edge(edge.entity, c, "DEPENDS_ON")

    def test_edge_as_to_entity_raises(self):
        """create_edge() raises InvalidEdgeError when to_entity is an edge (nono-2)."""
        a = create_entity("concept")
        b = create_entity("precept")
        edge = create_edge(a, b, "APPLIES_TO")
        c = create_entity("concept")
        with pytest.raises(InvalidEdgeError, match="to_entity is an edge"):
            create_edge(c, edge.entity, "DEPENDS_ON")

    def test_nono_check_precedes_constraint_validation(self):
        """The entity-type check fires before validate_edge() (nono-3)."""
        a = create_entity("concept")
        b = create_entity("precept")
        edge = create_edge(a, b, "APPLIES_TO")
        # Even an edge type that would otherwise be blocked by constraint validation
        # should raise InvalidEdgeError for the nono reason, not a constraint reason.
        c = create_entity("concept")
        with pytest.raises(InvalidEdgeError, match="from_entity is an edge"):
            create_edge(edge.entity, c, "TOTALLY_UNKNOWN_TYPE")

    def test_normal_entities_are_not_affected(self):
        """Non-edge entities can still be connected (regression guard)."""
        a = create_entity("concept")
        b = create_entity("concept")
        edge = create_edge(a, b, "DEPENDS_ON")
        assert edge.pk is not None


@pytest.mark.django_db
class TestUpdateEdgeProperties:
    """req-grid-edge-properties: update_edge_properties() service function."""

    @pytest.fixture(autouse=True)
    def isolate_registry(self) -> None:
        saved = _edge_property_schema_registry.all()
        _edge_property_schema_registry._reset_for_testing()
        yield
        _edge_property_schema_registry._reset_for_testing(saved)

    def test_updates_properties_and_persists(self):
        """update_edge_properties() saves the new payload to the database (properties-5)."""
        a = create_entity("concept")
        b = create_entity("concept")
        edge = create_edge(a, b, "DEPENDS_ON")
        updated = update_edge_properties(edge, {"strength": "weak"})
        updated.refresh_from_db()
        assert updated.properties == {"strength": "weak"}

    def test_returns_updated_edge(self):
        """update_edge_properties() returns the updated Edge instance."""
        a = create_entity("concept")
        b = create_entity("concept")
        edge = create_edge(a, b, "DEPENDS_ON")
        result = update_edge_properties(edge, {"note": "hi"})
        assert result.pk == edge.pk
        assert result.properties == {"note": "hi"}

    def test_valid_properties_pass_schema(self):
        """update_edge_properties() succeeds when properties match the schema (properties-5)."""
        register_edge_property_schema(
            "SCHEMA_EDGE",
            {"type": "object", "properties": {"score": {"type": "integer"}}},
        )
        a = create_entity("concept")
        b = create_entity("concept")
        edge = Edge.objects.create(from_entity=a, to_entity=b, edge_type="SCHEMA_EDGE", properties={})
        update_edge_properties(edge, {"score": 10})
        edge.refresh_from_db()
        assert edge.properties == {"score": 10}

    def test_invalid_properties_raise(self):
        """update_edge_properties() raises EdgePropertyValidationError for schema violations (properties-5, properties-8)."""
        register_edge_property_schema(
            "SCHEMA_EDGE_FAIL",
            {"type": "object", "properties": {"score": {"type": "integer"}}},
        )
        a = create_entity("concept")
        b = create_entity("concept")
        edge = Edge.objects.create(from_entity=a, to_entity=b, edge_type="SCHEMA_EDGE_FAIL", properties={})
        with pytest.raises(EdgePropertyValidationError):
            update_edge_properties(edge, {"score": "not-a-number"})
