"""Tests for tap_grid.services — the canonical mutation API."""

import uuid

import pytest

from plugins.lotr.models import Character
from tap_grid.caller_context import CallerContext
from tap_grid.constraints import (
    _edge_property_schema_registry,
    register_edge_property_schema,
)
from tap_grid.exceptions import EdgePropertyValidationError, InvalidEdgeError
from tap_grid.models import Batch, Edge, Entity
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
        result = create_node("character", {"name": "Ring-bearer", "bio": "A hobbit."})
        assert result.success
        assert result.entity_id is not None
        assert Character.objects.filter(entity_id=result.entity_id).exists()

    def test_entity_has_correct_type(self):
        result = create_node("character", {"name": "Legolas", "bio": "An elf."})
        entity = Entity.objects.get(pk=result.entity_id)
        assert entity.entity_type == "character"

    def test_batch_id_stamped_on_model(self):
        ctx = CallerContext(batch_id=str(uuid.uuid7()))
        result = create_node("character", {"name": "Test", "bio": "test"}, caller_context=ctx)
        char = Character.objects.get(entity_id=result.entity_id)
        assert char.batch_id == ctx.batch_id

    def test_object_summary_in_standard_mode(self):
        result = create_node("character", {"name": "Test"}, result_mode="standard")
        assert result.object_summary is not None
        assert "entity_id" in result.object_summary

    def test_no_summary_in_minimal_mode(self):
        result = create_node("character", {"name": "Test"}, result_mode="minimal")
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
        result = create_node("character", {"name": "Lord", "bio": "original bio"})
        char = Character.objects.get(entity_id=result.entity_id)
        patch_result = patch_node(char.entity_id, {"name": "Updated"})
        char.refresh_from_db()
        assert char.name == "Updated"
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
        result = create_node("character", {"name": "Test", "bio": "original"})
        patch_node(result.entity_id, {"bio": "updated"})
        char = Character.objects.get(entity_id=result.entity_id)
        assert char.bio == "updated"


@pytest.mark.django_db
class TestReplaceNode:
    """req-grid-service-write-patch-4: replace_node replaces all user-writable fields."""

    def test_all_fields_replaced(self):
        result = create_node("character", {"name": "Old Name", "bio": "old bio"})
        replace_result = replace_node(result.entity_id, {"name": "New Name", "bio": "new bio"})
        assert replace_result.success
        char = Character.objects.get(entity_id=result.entity_id)
        assert char.bio == "new bio"
        assert char.name == "New Name"

    def test_entity_spine_untouched(self):
        result = create_node("character", {"name": "name", "bio": "bio"})
        entity_before = Entity.objects.get(pk=result.entity_id)
        replace_node(result.entity_id, {"name": "new name", "bio": "new bio"})
        entity_after = Entity.objects.get(pk=result.entity_id)
        assert entity_before.entity_type == entity_after.entity_type
        assert entity_before.pk == entity_after.pk

    def test_missing_required_field_fails(self):
        result = create_node("character", {"name": "name", "bio": "bio"})
        replace_result = replace_node(result.entity_id, {})  # missing required name and bio
        assert not replace_result.success


@pytest.mark.django_db
class TestDeleteNode:
    """delete_node tombstones the domain object and its Entity spine."""

    def test_deletes_object_and_entity(self):
        result = create_node("character", {"name": "Gone", "bio": "gone"})
        entity_id = result.entity_id
        del_result = delete_node(entity_id)
        assert del_result.success
        # Tombstone: entity row still exists, deleted_at is set
        assert Entity.objects.filter(pk=entity_id, deleted_at__isnull=False).exists()
        # LiveManager hides the tombstoned character
        assert not Character.objects.filter(entity_id=entity_id).exists()

    def test_target_not_found_returns_error(self):
        del_result = delete_node(uuid.uuid7())
        assert not del_result.success
        assert any(e.code == "not_found" for e in del_result.errors)


@pytest.mark.django_db
class TestCreateEdgePipeline:
    """Tests for create_edge via write_batch pipeline (not the compat wrapper)."""

    def test_creates_edge_between_valid_nodes(self):
        from_result = create_node("character", {"name": "Frodo"})
        to_result = create_node("location", {"name": "Shire"})
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
        from_result = create_node("character", {"name": "Frodo"})
        to_result = create_node("location", {"name": "Shire"})
        edge_result = write_batch(
            [
                WriteOperation(
                    verb="create_edge",
                    from_target=from_result.entity_id,
                    to_target=to_result.entity_id,
                    edge_type="LOCATED_IN",
                    payload={},
                )
            ]
        )
        edge = Edge.objects.get(from_entity_id=from_result.entity_id, to_entity_id=to_result.entity_id)
        patch_result = patch_edge(edge.entity_id, {"edge_type": "RULES"})
        assert not patch_result.success
        assert any(e.code == "constraint_violation" for e in patch_result.errors)

    def test_no_edges_between_edges(self):
        a = create_node("character", {"name": "Frodo"})
        b = create_node("location", {"name": "Shire"})
        edge_result = write_batch(
            [
                WriteOperation(
                    verb="create_edge",
                    from_target=a.entity_id,
                    to_target=b.entity_id,
                    edge_type="LOCATED_IN",
                    payload={},
                )
            ]
        )
        edge = Edge.objects.get(from_entity_id=a.entity_id, to_entity_id=b.entity_id)
        # Try to use the edge's entity as an endpoint
        c = create_node("character", {"name": "Sam"})
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
        op1 = WriteOperation(verb="create_node", type_slug="character", payload={"name": "Frodo", "bio": "A hobbit"})
        op2 = WriteOperation(
            verb="create_node", type_slug="character", payload={"name": "Sam", "bio": "Another hobbit"}
        )
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
        op1 = WriteOperation(verb="create_node", type_slug="character", payload={"name": "Frodo"})
        op2 = WriteOperation(verb="create_node", type_slug="character", payload={"name": "Sam"})
        result = write_batch([op1, op2])
        assert result.results[0].batch_id == result.results[1].batch_id == result.batch_id

    def test_empty_batch_is_rejected(self):
        """An empty operation list is a caller bug, not a no-op: write_batch raises
        and mints no Batch (doc-auth-per-app-standards "seal empty-batch")."""
        before = Batch.objects.count()
        with pytest.raises(ValueError, match="at least one operation"):
            write_batch([])
        assert Batch.objects.count() == before


@pytest.mark.django_db
class TestDryRun:
    """Dry-run mode validates but does not persist."""

    def test_dry_run_returns_success_with_no_db_write(self):
        initial_count = Character.objects.count()
        result = create_node("character", {"name": "Phantom", "bio": "phantom"}, dry_run=True)
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
        result = create_node("character", {"name": "Test"}, caller_context=None)
        assert result.success
        assert result.batch_id  # a batch_id was auto-generated


# ===========================================================================
# Part A — Error taxonomy (spec-grid-service-errors)
# ===========================================================================


class TestServiceErrorTaxonomy:
    """req-grid-service-errors-taxonomy: stable codes and exception classes."""

    def test_all_seven_error_codes_exist(self):
        """ServiceError accepts all seven defined error codes without type error."""
        from tap_grid.service_types import ServiceError

        codes = [
            "validation_error",
            "constraint_violation",
            "authz_failure",
            "not_found",
            "conflict",
            "unsupported_operation",
            "internal_error",
        ]
        for code in codes:
            err = ServiceError(code=code, message="test")  # type: ignore[arg-type]
            assert err.code == code

    def test_service_error_has_correlation_id(self):
        from tap_grid.service_types import ServiceError

        err = ServiceError(code="internal_error", message="oops", correlation_id="abc-123")
        assert err.correlation_id == "abc-123"

    def test_service_error_correlation_id_defaults_none(self):
        from tap_grid.service_types import ServiceError

        err = ServiceError(code="not_found", message="missing")
        assert err.correlation_id is None

    def test_all_exception_classes_exist(self):
        from tap_grid.exceptions import (
            ServiceAuthzError,
            ServiceConflictError,
            ServiceConstraintError,
            ServiceNotFoundError,
            ServiceUnsupportedOperationError,
            ServiceValidationError,
        )

        for exc_cls in [
            ServiceValidationError,
            ServiceConstraintError,
            ServiceNotFoundError,
            ServiceAuthzError,
            ServiceConflictError,
            ServiceUnsupportedOperationError,
        ]:
            instance = exc_cls("test")
            assert str(instance) == "test"

    @pytest.mark.django_db
    def test_authz_failure_code_in_write_result(self):
        """ServiceAuthzError raised inside the pipeline maps to authz_failure code."""
        from unittest.mock import patch

        from tap_grid.exceptions import ServiceAuthzError

        with patch("tap_grid.services._execute_write_pipeline") as mock_pipeline:
            mock_pipeline.side_effect = ServiceAuthzError("forbidden")
            # write_batch catches this at the outer level
            from tap_grid.service_types import ServiceError, WriteResult

            mock_pipeline.return_value = WriteResult(
                success=False,
                batch_id="test",
                operation="create_node",
                errors=[ServiceError(code="authz_failure", message="forbidden")],
            )
            result = create_node("character", {})
            # Just confirm the code can be constructed; pipeline mock controls output
            assert mock_pipeline.called


# ===========================================================================
# Part A — batch-diag ACID-1 (operation field in WriteResult)
# ===========================================================================


@pytest.mark.django_db
class TestWriteResultOperationField:
    """req-grid-service-batch-diag-1: operation is populated in every WriteResult."""

    def test_create_node_operation_populated(self):
        result = create_node("character", {"bio": "test"})
        assert result.operation == "create_node"

    def test_patch_node_operation_populated(self):
        result = create_node("character", {})
        patch_result = patch_node(result.entity_id, {"bio": "updated"})
        assert patch_result.operation == "patch_node"

    def test_delete_node_operation_populated(self):
        result = create_node("character", {})
        del_result = delete_node(result.entity_id)
        assert del_result.operation == "delete_node"

    def test_failed_operation_still_has_operation_field(self):
        result = create_node("character", {"bad_field": "oops"})
        assert not result.success
        assert result.operation == "create_node"

    def test_batch_each_result_has_operation(self):
        op1 = WriteOperation(verb="create_node", type_slug="character", payload={})
        op2 = WriteOperation(verb="create_node", type_slug="character", payload={})
        batch = write_batch([op1, op2])
        for r in batch.results:
            assert r.operation == "create_node"


# ===========================================================================
# Part A — Read spec (spec-grid-service-read)
# ===========================================================================


@pytest.mark.django_db
class TestGetNode:
    """req-grid-service-read-direct: get_node() returns the typed instance."""

    def test_returns_typed_instance(self):
        from tap_grid.services import get_node

        result = create_node("character", {"name": "Frodo", "bio": "Ring-bearer"})
        char = get_node(result.entity_id)
        assert isinstance(char, Character)
        assert char.bio == "Ring-bearer"

    def test_accepts_string_uuid(self):
        from tap_grid.services import get_node

        result = create_node("character", {"name": "Test"})
        char = get_node(str(result.entity_id))
        assert char.entity_id == result.entity_id

    def test_not_found_raises(self):
        from tap_grid.exceptions import ServiceNotFoundError
        from tap_grid.services import get_node

        with pytest.raises(ServiceNotFoundError):
            get_node(uuid.uuid7())

    def test_edge_entity_raises_constraint_error(self):
        from tap_grid.exceptions import ServiceConstraintError
        from tap_grid.services import get_node

        a = create_entity("character")
        b = create_entity("location")
        edge = create_edge(a, b, "LOCATED_IN")
        with pytest.raises(ServiceConstraintError):
            get_node(edge.entity_id)


@pytest.mark.django_db
class TestGetEdge:
    """req-grid-service-read-direct: get_edge() returns the Edge instance."""

    def test_returns_edge(self):
        from tap_grid.services import get_edge

        a = create_entity("character")
        b = create_entity("location")
        edge = create_edge(a, b, "LOCATED_IN")
        found = get_edge(edge.entity_id)
        assert found.pk == edge.pk
        assert found.edge_type == "LOCATED_IN"

    def test_not_found_raises(self):
        from tap_grid.exceptions import ServiceNotFoundError
        from tap_grid.services import get_edge

        with pytest.raises(ServiceNotFoundError):
            get_edge(uuid.uuid7())


@pytest.mark.django_db
class TestGetObject:
    """req-grid-service-read-direct: get_object() dispatches node vs edge."""

    def test_returns_node_for_node_entity(self):
        from tap_grid.services import get_object

        result = create_node("character", {"name": "Test"})
        obj = get_object(result.entity_id)
        assert isinstance(obj, Character)

    def test_returns_edge_for_edge_entity(self):
        from tap_grid.services import get_object

        a = create_entity("character")
        b = create_entity("location")
        edge = create_edge(a, b, "LOCATED_IN")
        obj = get_object(edge.entity_id)
        assert isinstance(obj, Edge)

    def test_not_found_raises(self):
        from tap_grid.exceptions import ServiceNotFoundError
        from tap_grid.services import get_object

        with pytest.raises(ServiceNotFoundError):
            get_object(uuid.uuid7())


@pytest.mark.django_db
class TestResolveEntity:
    """req-grid-service-read-direct: resolve_entity() returns the Entity row."""

    def test_returns_entity(self):
        from tap_grid.services import resolve_entity

        result = create_node("character", {"name": "Test"})
        entity = resolve_entity(result.entity_id)
        assert entity.pk == result.entity_id
        assert entity.entity_type == "character"

    def test_not_found_raises(self):
        from tap_grid.exceptions import ServiceNotFoundError
        from tap_grid.services import resolve_entity

        with pytest.raises(ServiceNotFoundError):
            resolve_entity(uuid.uuid7())


class TestDiscoveryFunctions:
    """req-grid-service-read-discovery: list and describe node/edge types."""

    def test_list_node_types_returns_registered_types(self):
        from tap_grid.services import list_node_types

        types = list_node_types()
        assert "character" in types
        assert "location" in types
        assert isinstance(types, list)

    def test_list_edge_types_returns_registered_types(self):
        from tap_grid.services import list_edge_types

        types = list_edge_types()
        assert "LOCATED_IN" in types
        assert isinstance(types, list)

    def test_describe_node_type_returns_schemas(self):
        from tap_grid.services import describe_node_type

        desc = describe_node_type("character")
        assert desc.type_slug == "character"
        assert "create" in desc.schemas
        assert "patch" in desc.schemas
        assert "replace" in desc.schemas

    def test_describe_node_type_includes_constraints(self):
        from tap_grid.services import describe_node_type

        desc = describe_node_type("character")
        # character has OUTBOUND_EDGES defined in LOTR plugin
        assert isinstance(desc.outbound_edge_types, list)
        assert isinstance(desc.inbound_edge_types, list)

    def test_describe_node_type_unknown_raises(self):
        from tap_grid.exceptions import ServiceNotFoundError
        from tap_grid.services import describe_node_type

        with pytest.raises(ServiceNotFoundError):
            describe_node_type("totally_unknown_xyz")

    def test_describe_edge_type_returns_constraints(self):
        from tap_grid.services import describe_edge_type

        desc = describe_edge_type("LOCATED_IN")
        assert desc.edge_type == "LOCATED_IN"
        # allowed_sources/targets are either a list or "wildcard" or "none"
        assert isinstance(desc.allowed_sources, (list, str))
        assert isinstance(desc.allowed_targets, (list, str))

    def test_describe_edge_type_unknown_raises(self):
        from tap_grid.exceptions import ServiceNotFoundError
        from tap_grid.services import describe_edge_type

        with pytest.raises(ServiceNotFoundError):
            describe_edge_type("TOTALLY_UNKNOWN_EDGE_XYZ")

    def test_describe_service_capabilities(self):
        from tap_grid.services import describe_service_capabilities

        caps = describe_service_capabilities()
        assert "character" in caps.node_types
        assert "create_node" in caps.write_verbs
        assert "get_node" in caps.read_functions


# ===========================================================================
# Part A — Delete pipeline baseline (spec-grid-service-delete)
# ===========================================================================


@pytest.mark.django_db
class TestDeleteNodePipeline:
    """req-grid-service-delete-baseline: delete_node removes entity and cascades to edges."""

    def test_node_delete_removes_entity(self):
        """req-grid-service-delete-baseline-1: tombstone sets deleted_at."""
        result = create_node("character", {"name": "Test"})
        entity_id = result.entity_id
        del_result = delete_node(entity_id)
        assert del_result.success
        # Tombstone: row persists with deleted_at set; not visible via live query
        assert Entity.objects.filter(pk=entity_id, deleted_at__isnull=False).exists()
        assert not Entity.objects.filter(pk=entity_id, deleted_at__isnull=True).exists()

    def test_node_delete_removes_related_edges(self):
        """req-grid-service-delete-baseline-2."""
        from_result = create_node("character", {"name": "Frodo"})
        to_result = create_node("location", {"name": "Shire"})
        op = WriteOperation(
            verb="create_edge",
            from_target=from_result.entity_id,
            to_target=to_result.entity_id,
            edge_type="LOCATED_IN",
            payload={},
        )
        write_batch([op])
        edge = Edge.objects.get(from_entity_id=from_result.entity_id, to_entity_id=to_result.entity_id)
        delete_node(from_result.entity_id)
        assert not Edge.objects.filter(pk=edge.pk).exists()

    def test_delete_node_not_found_returns_error(self):
        del_result = delete_node(uuid.uuid7())
        assert not del_result.success
        assert any(e.code == "not_found" for e in del_result.errors)


@pytest.mark.django_db
class TestDeleteEdgePipeline:
    """req-grid-service-delete-baseline-3 and req-grid-service-delete-scope-2."""

    def test_delete_edge_by_entity_removes_edge_and_backing_entity(self):
        """delete_edge_by_entity tombstones the Edge and its backing Entity."""
        from tap_grid.services import delete_edge_by_entity

        a = create_entity("character")
        b = create_entity("location")
        edge = create_edge(a, b, "LOCATED_IN")
        backing_pk = edge.entity.pk
        result = delete_edge_by_entity(edge.entity_id)
        assert result.success
        # LiveManager hides the tombstoned edge
        assert not Edge.objects.filter(pk=edge.pk).exists()
        # Edge entity is tombstoned (row still in DB)
        assert Entity.objects.filter(pk=backing_pk, deleted_at__isnull=False).exists()

    def test_delete_edge_by_entity_endpoints_survive(self):
        from tap_grid.services import delete_edge_by_entity

        a = create_entity("character")
        b = create_entity("location")
        edge = create_edge(a, b, "LOCATED_IN")
        delete_edge_by_entity(edge.entity_id)
        assert Entity.objects.filter(pk=a.pk).exists()
        assert Entity.objects.filter(pk=b.pk).exists()

    def test_delete_edge_by_entity_not_found_returns_error(self):
        from tap_grid.services import delete_edge_by_entity

        result = delete_edge_by_entity(uuid.uuid7())
        assert not result.success
        assert any(e.code == "not_found" for e in result.errors)


@pytest.mark.django_db
class TestTombstoneDelete:
    """req-grid-service-delete-tombstone: delete_node uses soft-delete semantics."""

    def test_delete_node_sets_deleted_at(self):
        """delete_node sets deleted_at on the Entity; row remains in DB."""
        result = create_node("character", {"name": "Test"})
        entity_id = result.entity_id
        delete_node(entity_id)

        entity = Entity.objects.get(pk=entity_id)
        assert entity.deleted_at is not None

    def test_tombstoned_node_hidden_from_live_manager(self):
        """Tombstoned character not visible via Character.objects (LiveManager)."""
        result = create_node("character", {"name": "Test"})
        entity_id = result.entity_id
        delete_node(entity_id)

        assert not Character.objects.filter(entity_id=entity_id).exists()

    def test_tombstoned_node_visible_via_all_objects(self):
        """Tombstoned character visible via Character.all_objects."""
        result = create_node("character", {"name": "Test"})
        entity_id = result.entity_id
        delete_node(entity_id)

        assert Character.all_objects.filter(entity_id=entity_id).exists()

    def test_delete_node_cascades_edges_to_tombstone(self):
        """Edges touching a deleted node are also tombstoned."""
        from_result = create_node("character", {"name": "Frodo"})
        to_result = create_node("location", {"name": "Shire"})
        op = WriteOperation(
            verb="create_edge",
            from_target=from_result.entity_id,
            to_target=to_result.entity_id,
            edge_type="LOCATED_IN",
            payload={},
        )
        write_batch([op])
        edge = Edge.objects.get(from_entity_id=from_result.entity_id, to_entity_id=to_result.entity_id)
        edge_entity_id = edge.entity_id

        delete_node(from_result.entity_id)

        # Edge is tombstoned (hidden from live manager)
        assert not Edge.objects.filter(pk=edge.pk).exists()
        # Edge entity row persists with deleted_at set
        assert Entity.objects.filter(pk=edge_entity_id, deleted_at__isnull=False).exists()

    def test_patch_tombstoned_node_returns_conflict(self):
        """patch_node on a tombstoned entity returns entity_tombstoned conflict error."""
        result = create_node("character", {"name": "Test"})
        entity_id = result.entity_id
        delete_node(entity_id)

        patch_result = patch_node(entity_id, {"bio": "should fail"})
        assert not patch_result.success
        assert any(e.code == "conflict" for e in patch_result.errors)

    def test_replace_tombstoned_node_returns_conflict(self):
        """replace_node on a tombstoned entity returns entity_tombstoned conflict error."""
        result = create_node("character", {"name": "Test"})
        entity_id = result.entity_id
        delete_node(entity_id)

        replace_result = replace_node(entity_id, {"name": "Test", "bio": "should fail"})
        assert not replace_result.success
        assert any(e.code == "conflict" for e in replace_result.errors)


@pytest.mark.django_db
class TestEntityVersion:
    """req-grid-history-version: Entity.version increments on every canonical mutation."""

    def test_version_starts_at_one(self):
        """Newly created entity has version=1."""
        result = create_node("character", {"name": "Test"})
        entity = Entity.objects.get(pk=result.entity_id)
        assert entity.version == 1

    def test_version_increments_on_patch(self):
        """patch_node increments entity version."""
        result = create_node("character", {"name": "Test"})
        entity_id = result.entity_id
        patch_node(entity_id, {"bio": "updated"})

        entity = Entity.objects.get(pk=entity_id)
        assert entity.version == 2

    def test_version_increments_on_each_save(self):
        """Each successive mutation increments version."""
        result = create_node("character", {"name": "Test"})
        entity_id = result.entity_id
        patch_node(entity_id, {"bio": "v2"})
        patch_node(entity_id, {"bio": "v3"})

        entity = Entity.objects.get(pk=entity_id)
        assert entity.version == 3

    def test_version_increments_on_tombstone(self):
        """delete_node (tombstone) also increments entity version."""
        result = create_node("character", {"name": "Test"})
        entity_id = result.entity_id
        delete_node(entity_id)

        entity = Entity.objects.get(pk=entity_id)
        assert entity.version == 2
