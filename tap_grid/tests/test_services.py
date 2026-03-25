"""Tests for tap_grid.services — the canonical mutation API."""

import uuid

import pytest

from tap_grid.caller_context import CallerContext, set_caller_context
from tap_grid.constraints import (
    _edge_property_schema_registry,
    register_edge_property_schema,
)
from tap_grid.exceptions import EdgePropertyValidationError, InvalidEdgeError
from tap_grid.models import Edge, Entity
from tap_grid.service_types import WriteOperation
from tap_grid.services import (
    create_edge,
    create_entity,
    create_node,
    delete_edge,
    delete_entity,
    delete_node,
    patch_edge,
    patch_node,
    replace_node,
    update_edge_properties,
    update_entity,
    write_batch,
)
from plugins.lotr.models import Character


@pytest.mark.django_db
class TestCreateEntity:
    def test_creates_with_type_and_name(self):
        entity = create_entity("character", name="Frodo Baggins")
        assert entity.entity_type == "character"
        assert entity.name == "Frodo Baggins"
        assert entity.pk is not None

    def test_auto_generates_uuid7(self):
        e1 = create_entity("character")
        e2 = create_entity("character")
        assert e1.pk != e2.pk
        # UUIDv7 is time-ordered: second should sort after first
        assert str(e2.pk) > str(e1.pk)

    def test_stamps_grid_id(self):
        entity = create_entity("character")
        assert entity.originating_grid_id is not None


@pytest.mark.django_db
class TestUpdateEntity:
    def test_updates_fields(self):
        entity = create_entity("character", name="Old Name")
        updated = update_entity(entity, name="New Name")
        assert updated.name == "New Name"
        entity.refresh_from_db()
        assert entity.name == "New Name"


@pytest.mark.django_db
class TestDeleteEntity:
    def test_deletes_entity(self):
        entity = create_entity("character")
        pk = entity.pk
        delete_entity(entity)
        assert not Entity.objects.filter(pk=pk).exists()

    def test_cascades_to_edges(self):
        a = create_entity("character", name="Frodo")
        b = create_entity("location", name="Mordor")
        edge = create_edge(a, b, "LOCATED_IN")
        delete_entity(a)
        # Edge should be gone (from_entity cascade)
        assert not Edge.objects.filter(pk=edge.pk).exists()

    def test_cascades_to_domain_model(self):
        entity = create_entity("character", name="Legolas")
        Character.objects.create(entity=entity, bio="An elf of Mirkwood.")
        delete_entity(entity)
        assert not Character.objects.filter(entity_id=entity.pk).exists()


@pytest.mark.django_db
class TestCreateEdge:
    def test_creates_edge_with_backing_entity(self):
        a = create_entity("character")
        b = create_entity("location")
        edge = create_edge(a, b, "LOCATED_IN")
        assert edge.from_entity == a
        assert edge.to_entity == b
        assert edge.edge_type == "LOCATED_IN"
        # Edge has a backing Entity
        assert edge.entity is not None
        assert edge.entity.entity_type == "edge"

    def test_edge_properties(self):
        a = create_entity("wanderer")
        b = create_entity("wanderer")
        edge = create_edge(a, b, "WANDERS_TOWARD", properties={"distance": "far"})
        assert edge.properties == {"distance": "far"}

    def test_allies_with_between_characters(self):
        char_a = create_entity("character", name="Frodo")
        char_b = create_entity("character", name="Gandalf")
        edge = create_edge(char_a, char_b, "ALLIES_WITH")
        assert edge.edge_type == "ALLIES_WITH"


@pytest.mark.django_db
class TestDeleteEdge:
    def test_deletes_edge_and_backing_entity(self):
        a = create_entity("character")
        b = create_entity("location")
        edge = create_edge(a, b, "LOCATED_IN")
        backing_entity_pk = edge.entity.pk
        delete_edge(edge)
        assert not Edge.objects.filter(pk=edge.pk).exists()
        assert not Entity.objects.filter(pk=backing_entity_pk).exists()

    def test_source_entities_survive(self):
        a = create_entity("character")
        b = create_entity("location")
        edge = create_edge(a, b, "LOCATED_IN")
        delete_edge(edge)
        # The endpoints should still exist
        assert Entity.objects.filter(pk=a.pk).exists()
        assert Entity.objects.filter(pk=b.pk).exists()


@pytest.mark.django_db
class TestNoEdgesBetweenEdges:
    """req-grid-edge-nono: create_edge() rejects edges whose endpoints are themselves edges."""

    def test_edge_as_from_entity_raises(self):
        """create_edge() raises InvalidEdgeError when from_entity is an edge (nono-1)."""
        a = create_entity("character")
        b = create_entity("location")
        edge = create_edge(a, b, "LOCATED_IN")
        c = create_entity("character")
        with pytest.raises(InvalidEdgeError, match="from_entity is an edge"):
            create_edge(edge.entity, c, "ALLIES_WITH")

    def test_edge_as_to_entity_raises(self):
        """create_edge() raises InvalidEdgeError when to_entity is an edge (nono-2)."""
        a = create_entity("character")
        b = create_entity("location")
        edge = create_edge(a, b, "LOCATED_IN")
        c = create_entity("character")
        with pytest.raises(InvalidEdgeError, match="to_entity is an edge"):
            create_edge(c, edge.entity, "ALLIES_WITH")

    def test_nono_check_precedes_constraint_validation(self):
        """The entity-type check fires before validate_edge() (nono-3)."""
        a = create_entity("character")
        b = create_entity("location")
        edge = create_edge(a, b, "LOCATED_IN")
        # Even an edge type that would otherwise be blocked by constraint validation
        # should raise InvalidEdgeError for the nono reason, not a constraint reason.
        c = create_entity("character")
        with pytest.raises(InvalidEdgeError, match="from_entity is an edge"):
            create_edge(edge.entity, c, "TOTALLY_UNKNOWN_TYPE")

    def test_normal_entities_are_not_affected(self):
        """Non-edge entities can still be connected (regression guard)."""
        a = create_entity("character")
        b = create_entity("character")
        edge = create_edge(a, b, "ALLIES_WITH")
        assert edge.pk is not None


@pytest.mark.django_db
class TestUpdateEdgeProperties:
    """req-grid-edge-properties: update_edge_properties() service function.

    Uses wanderer entities — no OUTBOUND_EDGES/INBOUND_EDGES constraints,
    so test-only edge types are accepted without constraint errors.
    """

    @pytest.fixture(autouse=True)
    def isolate_registry(self) -> None:
        saved = _edge_property_schema_registry.all()
        _edge_property_schema_registry._reset_for_testing()
        yield
        _edge_property_schema_registry._reset_for_testing(saved)

    def test_updates_properties_and_persists(self):
        """update_edge_properties() saves the new payload to the database (properties-5)."""
        a = create_entity("wanderer")
        b = create_entity("wanderer")
        edge = create_edge(a, b, "WANDERS_TOWARD")
        updated = update_edge_properties(edge, {"distance": "short"})
        updated.refresh_from_db()
        assert updated.properties == {"distance": "short"}

    def test_returns_updated_edge(self):
        """update_edge_properties() returns the updated Edge instance."""
        a = create_entity("wanderer")
        b = create_entity("wanderer")
        edge = create_edge(a, b, "WANDERS_TOWARD")
        result = update_edge_properties(edge, {"note": "hi"})
        assert result.pk == edge.pk
        assert result.properties == {"note": "hi"}

    def test_valid_properties_pass_schema(self):
        """update_edge_properties() succeeds when properties match the schema (properties-5)."""
        register_edge_property_schema(
            "SCHEMA_EDGE",
            {"type": "object", "properties": {"score": {"type": "integer"}}},
        )
        a = create_entity("wanderer")
        b = create_entity("wanderer")
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
        a = create_entity("wanderer")
        b = create_entity("wanderer")
        edge = Edge.objects.create(from_entity=a, to_entity=b, edge_type="SCHEMA_EDGE_FAIL", properties={})
        with pytest.raises(EdgePropertyValidationError):
            update_edge_properties(edge, {"score": "not-a-number"})


# ===========================================================================
# Phase 3 — write_batch() and typed service verbs
# ===========================================================================


@pytest.mark.django_db
class TestCreateNode:
    """req-grid-service-write-surface-1: create_node creates a typed domain object."""

    def test_creates_character(self):
        result = create_node("character", {"bio": "A hobbit.", "title": "Ring-bearer"})
        assert result.success
        assert result.entity_id is not None
        assert Character.objects.filter(entity_id=result.entity_id).exists()

    def test_entity_has_correct_type(self):
        result = create_node("character", {"bio": "An elf."})
        entity = Entity.objects.get(pk=result.entity_id)
        assert entity.entity_type == "character"

    def test_batch_id_stamped_on_model(self):
        ctx = CallerContext(batch_id=str(uuid.uuid7()))
        result = create_node("character", {"bio": "test"}, caller_context=ctx)
        char = Character.objects.get(entity_id=result.entity_id)
        assert char.batch_id == ctx.batch_id

    def test_object_summary_in_standard_mode(self):
        result = create_node("character", {}, result_mode="standard")
        assert result.object_summary is not None
        assert "entity_id" in result.object_summary

    def test_no_summary_in_minimal_mode(self):
        result = create_node("character", {}, result_mode="minimal")
        assert result.object_summary is None


@pytest.mark.django_db
class TestCreateNodeValidation:
    """req-grid-service-write-payloads-2: schema validation rejects bad payloads."""

    def test_unknown_field_rejected(self):
        result = create_node("character", {"bio": "ok", "nonexistent_field": "bad"})
        assert not result.success
        assert any(e.code == "validation_error" for e in result.errors)

    def test_invalid_type_rejected(self):
        result = create_node("character", {"bio": 999})  # bio must be string
        assert not result.success
        assert any(e.code == "validation_error" for e in result.errors)

    def test_unknown_entity_type_rejected(self):
        result = create_node("nonexistent_type_xyz", {})
        assert not result.success
        assert any(e.code == "not_found" for e in result.errors)


@pytest.mark.django_db
class TestPatchNode:
    """req-grid-service-write-patch: patch semantics leave omitted fields unchanged."""

    def test_omitted_fields_unchanged(self):
        result = create_node("character", {"bio": "original bio", "title": "Lord"})
        char = Character.objects.get(entity_id=result.entity_id)
        patch_result = patch_node(char.entity_id, {"title": "Updated"})
        char.refresh_from_db()
        assert char.title == "Updated"
        assert char.bio == "original bio"  # untouched

    def test_json_field_deep_merge(self):
        """Patch applies deep merge to JSONField values (req-grid-service-write-patch-1)."""
        from tap_grid.models import Search

        result = create_node(
            "search",
            {"name": "test-search", "search_type": "orm", "root": "node", "definition": {"filters": {"name": "Frodo"}}},
        )
        assert result.success, f"create failed: {result.errors}"
        patch_result = patch_node(result.entity_id, {"definition": {"order_by": ["name"]}})
        assert patch_result.success
        search = Search.objects.get(entity_id=result.entity_id)
        assert search.definition == {"filters": {"name": "Frodo"}, "order_by": ["name"]}  # deep merged

    def test_scalar_field_replaces(self):
        result = create_node("character", {"bio": "original"})
        patch_node(result.entity_id, {"bio": "updated"})
        char = Character.objects.get(entity_id=result.entity_id)
        assert char.bio == "updated"


@pytest.mark.django_db
class TestReplaceNode:
    """req-grid-service-write-patch-4: replace_node replaces all user-writable fields."""

    def test_all_fields_replaced(self):
        result = create_node("character", {"bio": "old bio", "title": "Old Title"})
        replace_result = replace_node(result.entity_id, {"bio": "new bio", "title": "New Title"})
        assert replace_result.success
        char = Character.objects.get(entity_id=result.entity_id)
        assert char.bio == "new bio"
        assert char.title == "New Title"

    def test_entity_spine_untouched(self):
        result = create_node("character", {"bio": "bio"})
        entity_before = Entity.objects.get(pk=result.entity_id)
        replace_node(result.entity_id, {"bio": "new bio", "title": "title"})
        entity_after = Entity.objects.get(pk=result.entity_id)
        assert entity_before.entity_type == entity_after.entity_type
        assert entity_before.pk == entity_after.pk

    def test_missing_required_field_fails(self):
        result = create_node("character", {"bio": "bio", "title": "title"})
        replace_result = replace_node(result.entity_id, {})  # missing required bio and title
        assert not replace_result.success


@pytest.mark.django_db
class TestDeleteNode:
    """delete_node removes the domain object and its Entity spine."""

    def test_deletes_object_and_entity(self):
        result = create_node("character", {"bio": "gone"})
        entity_id = result.entity_id
        del_result = delete_node(entity_id)
        assert del_result.success
        assert not Entity.objects.filter(pk=entity_id).exists()
        assert not Character.objects.filter(entity_id=entity_id).exists()

    def test_target_not_found_returns_error(self):
        del_result = delete_node(uuid.uuid7())
        assert not del_result.success
        assert any(e.code == "not_found" for e in del_result.errors)


@pytest.mark.django_db
class TestCreateEdgePipeline:
    """Tests for create_edge via write_batch pipeline (not the compat wrapper)."""

    def test_creates_edge_between_valid_nodes(self):
        from_result = create_node("character", {})
        to_result = create_node("location", {})
        op = WriteOperation(
            verb="create_edge",
            from_target=from_result.entity_id,
            to_target=to_result.entity_id,
            edge_type="LOCATED_IN",
            payload={},
        )
        batch = write_batch([op])
        assert batch.success
        assert Edge.objects.filter(
            from_entity_id=from_result.entity_id,
            to_entity_id=to_result.entity_id,
            edge_type="LOCATED_IN",
        ).exists()

    def test_edge_type_immutable_on_patch(self):
        from_result = create_node("character", {})
        to_result = create_node("location", {})
        edge_result = write_batch([WriteOperation(
            verb="create_edge",
            from_target=from_result.entity_id,
            to_target=to_result.entity_id,
            edge_type="LOCATED_IN",
            payload={},
        )])
        edge = Edge.objects.get(from_entity_id=from_result.entity_id, to_entity_id=to_result.entity_id)
        patch_result = patch_edge(edge.entity_id, {"edge_type": "RULES"})
        assert not patch_result.success
        assert any(e.code == "constraint_violation" for e in patch_result.errors)

    def test_no_edges_between_edges(self):
        a = create_node("character", {})
        b = create_node("location", {})
        edge_result = write_batch([WriteOperation(
            verb="create_edge",
            from_target=a.entity_id,
            to_target=b.entity_id,
            edge_type="LOCATED_IN",
            payload={},
        )])
        edge = Edge.objects.get(from_entity_id=a.entity_id, to_entity_id=b.entity_id)
        # Try to use the edge's entity as an endpoint
        c = create_node("character", {})
        bad_op = WriteOperation(
            verb="create_edge",
            from_target=edge.entity_id,  # edge entity as source — not allowed
            to_target=c.entity_id,
            edge_type="ALLIES_WITH",
            payload={},
        )
        batch = write_batch([bad_op])
        assert not batch.success
        assert any(e.code == "constraint_violation" for e in batch.results[0].errors)


@pytest.mark.django_db
class TestWriteBatch:
    """req-grid-service-write-surface-3: write_batch() is atomic; failure rolls back all."""

    def test_multi_op_batch_commits(self):
        op1 = WriteOperation(verb="create_node", type_slug="character", payload={"bio": "Frodo"})
        op2 = WriteOperation(verb="create_node", type_slug="character", payload={"bio": "Sam"})
        result = write_batch([op1, op2])
        assert result.success
        assert len(result.results) == 2
        assert all(r.success for r in result.results)

    def test_one_invalid_op_rolls_back_all(self):
        op1 = WriteOperation(verb="create_node", type_slug="character", payload={"bio": "Valid"})
        op2 = WriteOperation(verb="create_node", type_slug="character", payload={"bad_field": "oops"})
        initial_count = Character.objects.count()
        result = write_batch([op1, op2])
        assert not result.success
        # No characters should have been created
        assert Character.objects.count() == initial_count

    def test_shared_batch_id_across_all_results(self):
        op1 = WriteOperation(verb="create_node", type_slug="character", payload={})
        op2 = WriteOperation(verb="create_node", type_slug="character", payload={})
        result = write_batch([op1, op2])
        assert result.results[0].batch_id == result.results[1].batch_id == result.batch_id


@pytest.mark.django_db
class TestDryRun:
    """Dry-run mode validates but does not persist."""

    def test_dry_run_returns_success_with_no_db_write(self):
        initial_count = Character.objects.count()
        result = create_node("character", {"bio": "phantom"}, dry_run=True)
        assert result.success
        assert Character.objects.count() == initial_count

    def test_dry_run_catches_validation_errors(self):
        result = create_node("character", {"unknown_key": "bad"}, dry_run=True)
        assert not result.success
        assert any(e.code == "validation_error" for e in result.errors)

    def test_dry_run_flag_propagated_to_batch_result(self):
        op = WriteOperation(verb="create_node", type_slug="character", payload={})
        batch = write_batch([op], dry_run=True)
        assert batch.dry_run is True


@pytest.mark.django_db
class TestCallerContextFlows:
    """CallerContext user and batch_id are threaded through the pipeline."""

    def test_provided_batch_id_reused(self):
        ctx = CallerContext(batch_id=str(uuid.uuid7()))
        r1 = create_node("character", {}, caller_context=ctx)
        r2 = create_node("character", {}, caller_context=ctx)
        assert r1.batch_id == ctx.batch_id
        assert r2.batch_id == ctx.batch_id

    def test_auto_generated_batch_id_when_none_provided(self):
        # Pass explicit None caller_context so no batch_id is inherited from fixture.
        result = create_node("character", {}, caller_context=None)
        assert result.success
        assert result.batch_id  # a batch_id was auto-generated
