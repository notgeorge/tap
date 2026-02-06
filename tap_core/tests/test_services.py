"""Tests for tap_core.services — the canonical mutation API."""

import pytest

from tap_core.models import Edge, Entity
from tap_core.services import create_edge, create_entity, delete_edge, delete_entity, update_entity
from tap_plugins.core_examples.models import Concept


@pytest.mark.django_db
class TestCreateEntity:
    def test_creates_with_type_and_name(self):
        entity = create_entity("concept", display_name="Least Privilege")
        assert entity.entity_type == "concept"
        assert entity.display_name == "Least Privilege"
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
        entity = create_entity("concept", display_name="Old Name")
        updated = update_entity(entity, display_name="New Name")
        assert updated.display_name == "New Name"
        entity.refresh_from_db()
        assert entity.display_name == "New Name"


@pytest.mark.django_db
class TestDeleteEntity:
    def test_deletes_entity(self):
        entity = create_entity("concept")
        pk = entity.pk
        delete_entity(entity)
        assert not Entity.objects.filter(pk=pk).exists()

    def test_cascades_to_edges(self):
        a = create_entity("concept", display_name="A")
        b = create_entity("precept", display_name="B")
        edge = create_edge(a, b, "applies_to")
        delete_entity(a)
        # Edge should be gone (from_entity cascade)
        assert not Edge.objects.filter(pk=edge.pk).exists()

    def test_cascades_to_domain_model(self):
        entity = create_entity("concept", display_name="Separation of Concerns")
        Concept.objects.create(entity=entity, summary="Keep things separate.")
        delete_entity(entity)
        assert not Concept.objects.filter(entity_id=entity.pk).exists()


@pytest.mark.django_db
class TestCreateEdge:
    def test_creates_edge_with_backing_entity(self):
        a = create_entity("concept")
        b = create_entity("precept")
        edge = create_edge(a, b, "applies_to")
        assert edge.from_entity == a
        assert edge.to_entity == b
        assert edge.edge_type == "applies_to"
        # Edge has a backing Entity
        assert edge.entity is not None
        assert edge.entity.entity_type == "edge"

    def test_edge_properties(self):
        a = create_entity("concept")
        b = create_entity("concept")
        edge = create_edge(a, b, "depends_on", properties={"strength": "strong"})
        assert edge.properties == {"strength": "strong"}

    def test_depends_on_works_across_types(self):
        concept = create_entity("concept", display_name="Defense in Depth")
        precept = create_entity("precept", display_name="Use MFA")
        edge = create_edge(concept, precept, "depends_on")
        assert edge.edge_type == "depends_on"


@pytest.mark.django_db
class TestDeleteEdge:
    def test_deletes_edge_and_backing_entity(self):
        a = create_entity("concept")
        b = create_entity("precept")
        edge = create_edge(a, b, "applies_to")
        backing_entity_pk = edge.entity.pk
        delete_edge(edge)
        assert not Edge.objects.filter(pk=edge.pk).exists()
        assert not Entity.objects.filter(pk=backing_entity_pk).exists()

    def test_source_entities_survive(self):
        a = create_entity("concept")
        b = create_entity("precept")
        edge = create_edge(a, b, "applies_to")
        delete_edge(edge)
        # The endpoints should still exist
        assert Entity.objects.filter(pk=a.pk).exists()
        assert Entity.objects.filter(pk=b.pk).exists()
