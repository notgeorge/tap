"""Tests for the GRIFT v0 importer (tap_grid/grift.py)."""

import uuid
from typing import Any

import pytest

from tap_grid.grift import (
    grift_import,
)
from tap_grid.models import Batch, Edge, Entity

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _batch_entity_id() -> str:
    return str(uuid.uuid4())


def _node_entity_id() -> str:
    return str(uuid.uuid4())


def _edge_entity_id() -> str:
    return str(uuid.uuid4())


def _minimal_doc(batches: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Minimal valid GRIFT document."""
    return {
        "metadata": {"grift_version": "0"},
        "_reserved": {},
        "batches": batches or [],
    }


def _batch_container(
    batch_entity_id: str,
    nodes: list[dict[str, Any]] | None = None,
    edges: list[dict[str, Any]] | None = None,
    batch_node: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "batch_entity": {
            "entity_id": batch_entity_id,
            "entity_type": "batch",
            "name": "Test batch",
            "dimensions": {},
        },
        "batch_node": batch_node
        or {
            "name": "Test batch",
            "description": "",
            "description_json": None,
            "source": "test",
            "metadata": {},
        },
        "nodes": nodes or [],
        "edges": edges or [],
    }


def _character_node(entity_id: str, name: str = "Frodo", bio: str = "A hobbit") -> dict[str, Any]:
    return {
        "entity": {
            "entity_id": entity_id,
            "entity_type": "character",
            "name": name,
            "dimensions": {},
        },
        "node": {"name": name, "bio": bio},
    }


def _wields_edge(edge_entity_id: str, from_id: str, to_id: str) -> dict[str, Any]:
    return {
        "entity": {
            "entity_id": edge_entity_id,
            "entity_type": "edge",
            "dimensions": {},
        },
        "edge": {
            "from_entity_id": from_id,
            "to_entity_id": to_id,
            "edge_type": "WIELDS",
            "properties": {},
        },
    }


# ---------------------------------------------------------------------------
# Document-level schema tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGriftDocumentSchema:
    def test_empty_doc_succeeds(self):
        result = grift_import(_minimal_doc())
        assert result.success
        assert result.grift_version == "0"

    def test_invalid_json_string(self):
        result = grift_import("{ not valid json }")
        assert not result.success
        assert result.errors[0].code == "invalid_json"
        assert result.errors[0].phase == "parse"

    def test_missing_metadata_key(self):
        doc = {"_reserved": {}, "batches": []}
        result = grift_import(doc)
        assert not result.success
        assert any(e.code == "schema_validation_failed" and "metadata" in e.message for e in result.errors)

    def test_missing_batches_key(self):
        doc = {"metadata": {"grift_version": "0"}, "_reserved": {}}
        result = grift_import(doc)
        assert not result.success
        assert any(e.code == "schema_validation_failed" for e in result.errors)

    def test_unknown_top_level_key(self):
        doc = _minimal_doc()
        doc["unknown_key"] = "value"
        result = grift_import(doc)
        assert not result.success
        assert any(e.code == "schema_validation_failed" and "unknown_key" in e.message for e in result.errors)

    def test_reserved_object_is_ignored(self):
        doc = _minimal_doc()
        doc["_reserved"] = {"future": "extension"}
        result = grift_import(doc)
        assert result.success

    def test_bytes_input_parsed(self):
        import json

        result = grift_import(json.dumps(_minimal_doc()).encode())
        assert result.success

    def test_missing_grift_version(self):
        doc = {"metadata": {}, "_reserved": {}, "batches": []}
        result = grift_import(doc)
        assert not result.success
        assert any("grift_version" in e.message for e in result.errors)

    def test_unknown_metadata_key(self):
        doc = _minimal_doc()
        doc["metadata"]["extra"] = "x"
        result = grift_import(doc)
        assert not result.success


# ---------------------------------------------------------------------------
# Entity envelope validation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGriftEnvelopeValidation:
    def test_batch_entity_type_not_batch_fails(self):
        bid = _batch_entity_id()
        container = _batch_container(bid)
        container["batch_entity"]["entity_type"] = "character"
        result = grift_import(_minimal_doc([container]))
        assert not result.success
        assert any(e.code == "entity_type_mismatch" for e in result.errors)

    def test_edge_entity_type_not_edge_fails(self):
        bid = _batch_entity_id()
        nid = _node_entity_id()
        aid = _node_entity_id()
        eid = _edge_entity_id()
        char = _character_node(nid)
        char2 = _character_node(aid, name="Sam")
        edge = _wields_edge(eid, nid, aid)
        edge["entity"]["entity_type"] = "wrong"
        container = _batch_container(bid, nodes=[char, char2], edges=[edge])
        result = grift_import(_minimal_doc([container]))
        assert not result.success
        assert any(e.code == "entity_type_mismatch" for e in result.errors)

    def test_missing_required_envelope_field(self):
        bid = _batch_entity_id()
        container = _batch_container(bid)
        del container["batch_entity"]["entity_id"]
        result = grift_import(_minimal_doc([container]))
        assert not result.success
        assert any("entity_id" in e.message for e in result.errors)

    def test_invalid_uuid_in_envelope(self):
        bid = _batch_entity_id()
        container = _batch_container(bid)
        container["batch_entity"]["entity_id"] = "not-a-uuid"
        result = grift_import(_minimal_doc([container]))
        assert not result.success
        assert any(e.code == "schema_validation_failed" for e in result.errors)

    def test_unknown_key_in_envelope_rejected(self):
        bid = _batch_entity_id()
        container = _batch_container(bid)
        container["batch_entity"]["sneaky"] = "extra"
        result = grift_import(_minimal_doc([container]))
        assert not result.success

    def test_name_empty_string_rejected(self):
        bid = _batch_entity_id()
        container = _batch_container(bid)
        container["batch_entity"]["name"] = ""
        result = grift_import(_minimal_doc([container]))
        assert not result.success
        assert any(
            "name" in e.message or "non-empty" in e.message or "too short" in e.message
            for e in result.errors
        )

    def test_dimensions_non_string_value_rejected(self):
        bid = _batch_entity_id()
        container = _batch_container(bid)
        container["batch_entity"]["dimensions"] = {"key": 123}
        result = grift_import(_minimal_doc([container]))
        assert not result.success


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGriftDuplicateDetection:
    def test_duplicate_entity_id_across_batches_fails(self):
        shared_id = _node_entity_id()
        bid1 = _batch_entity_id()
        bid2 = _batch_entity_id()
        container1 = _batch_container(bid1, nodes=[_character_node(shared_id)])
        container2 = _batch_container(bid2, nodes=[_character_node(shared_id, name="Sam")])
        result = grift_import(_minimal_doc([container1, container2]))
        assert not result.success
        assert any(e.code == "duplicate_entity_id" for e in result.errors)

    def test_duplicate_batch_entity_id_fails(self):
        shared_bid = _batch_entity_id()
        container1 = _batch_container(shared_bid)
        container2 = _batch_container(shared_bid)
        result = grift_import(_minimal_doc([container1, container2]))
        assert not result.success
        assert any(e.code == "duplicate_batch_id" for e in result.errors)


# ---------------------------------------------------------------------------
# Unknown entity type
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGriftUnknownEntityType:
    def test_unknown_node_type_fails(self):
        bid = _batch_entity_id()
        nid = _node_entity_id()
        node = {
            "entity": {"entity_id": nid, "entity_type": "nonexistent_type", "dimensions": {}},
            "node": {"name": "X"},
        }
        container = _batch_container(bid, nodes=[node])
        result = grift_import(_minimal_doc([container]))
        assert not result.success
        assert any(e.code == "unknown_entity_type" for e in result.errors)


# ---------------------------------------------------------------------------
# Dangling edge handling
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGriftDanglingEdges:
    def test_dangling_edge_strict_fails_preflight(self):
        bid = _batch_entity_id()
        nid = _node_entity_id()
        ghost_id = str(uuid.uuid4())  # never imported / not in grid
        eid = _edge_entity_id()

        char = _character_node(nid)
        edge = _wields_edge(eid, nid, ghost_id)
        container = _batch_container(bid, nodes=[char], edges=[edge])

        result = grift_import(_minimal_doc([container]), dangling_edge_mode="strict")
        assert not result.success
        assert any(e.code == "dangling_edge" for e in result.errors)
        assert result.counts.batches_imported == 0

    def test_dangling_edge_permissive_skips_edge(self):
        bid = _batch_entity_id()
        nid = _node_entity_id()
        ghost_id = str(uuid.uuid4())
        eid = _edge_entity_id()

        char = _character_node(nid)
        edge = _wields_edge(eid, nid, ghost_id)
        container = _batch_container(bid, nodes=[char], edges=[edge])

        result = grift_import(_minimal_doc([container]), dangling_edge_mode="permissive")
        assert result.success
        assert result.counts.nodes_imported == 1
        assert result.counts.edges_skipped == 1
        assert result.counts.edges_imported == 0


# ---------------------------------------------------------------------------
# Upsert: create path
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGriftUpsertCreate:
    def test_creates_node_with_preserved_entity_id(self):
        bid = _batch_entity_id()
        nid = _node_entity_id()
        char = _character_node(nid)
        container = _batch_container(bid, nodes=[char])

        result = grift_import(_minimal_doc([container]))
        assert result.success
        assert result.counts.nodes_imported == 1
        assert Entity.objects.filter(pk=uuid.UUID(nid)).exists()

    def test_creates_edge_with_preserved_entity_id(self):
        bid = _batch_entity_id()
        nid1 = _node_entity_id()
        nid2 = _node_entity_id()
        eid = _edge_entity_id()

        char1 = _character_node(nid1, name="Frodo")
        artifact_id = nid2
        artifact_node = {
            "entity": {"entity_id": artifact_id, "entity_type": "artifact", "dimensions": {}},
            "node": {"name": "Sting", "power": "glows", "origin": "Erebor"},
        }
        edge = _wields_edge(eid, nid1, artifact_id)
        container = _batch_container(bid, nodes=[char1, artifact_node], edges=[edge])

        result = grift_import(_minimal_doc([container]))
        assert result.success
        assert result.counts.nodes_imported == 2
        assert result.counts.edges_imported == 1
        assert Entity.objects.filter(pk=uuid.UUID(eid), entity_type="edge").exists()
        assert Edge.objects.filter(entity_id=uuid.UUID(eid)).exists()

    def test_creates_batch_with_preserved_entity_id(self):
        bid = _batch_entity_id()
        container = _batch_container(bid)
        result = grift_import(_minimal_doc([container]))
        assert result.success
        assert Batch.objects.filter(entity_id=bid).exists()

    def test_import_result_contains_batch_summary(self):
        bid = _batch_entity_id()
        nid = _node_entity_id()
        container = _batch_container(bid, nodes=[_character_node(nid)])
        result = grift_import(_minimal_doc([container]))
        assert result.success
        assert len(result.imported_batches) == 1
        assert result.imported_batches[0].batch_entity_id == bid
        assert result.imported_batches[0].nodes_imported == 1


# ---------------------------------------------------------------------------
# Upsert: replace path
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGriftUpsertReplace:
    def test_replaces_existing_node_on_second_import(self):
        bid1 = _batch_entity_id()
        nid = _node_entity_id()

        # First import creates the character.
        char = _character_node(nid, name="Frodo", bio="Original bio")
        result1 = grift_import(_minimal_doc([_batch_container(bid1, nodes=[char])]))
        assert result1.success

        # Second import replaces with updated data under a new batch.
        bid2 = _batch_entity_id()
        updated_char = _character_node(nid, name="Frodo Updated", bio="Updated bio")
        result2 = grift_import(_minimal_doc([_batch_container(bid2, nodes=[updated_char])]))
        assert result2.success
        assert result2.counts.nodes_imported == 1

        from plugins.lotr.models import Character

        char_obj = Character.objects.get(entity_id=uuid.UUID(nid))
        assert char_obj.name == "Frodo Updated"
        assert char_obj.bio == "Updated bio"


# ---------------------------------------------------------------------------
# Idempotency: batch-level skip
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGriftIdempotency:
    def test_same_batch_skipped_on_second_import(self):
        bid = _batch_entity_id()
        nid = _node_entity_id()
        char = _character_node(nid)
        container = _batch_container(bid, nodes=[char])
        doc = _minimal_doc([container])

        result1 = grift_import(doc)
        assert result1.success
        assert result1.counts.batches_imported == 1

        result2 = grift_import(doc)
        assert result2.success
        assert result2.counts.batches_imported == 0
        assert result2.counts.batches_skipped == 1
        assert len(result2.skipped_batches) == 1
        assert result2.skipped_batches[0].batch_entity_id == bid
        assert result2.skipped_batches[0].reason == "batch_already_imported"

    def test_skipped_batch_does_not_duplicate_entities(self):
        bid = _batch_entity_id()
        nid = _node_entity_id()
        char = _character_node(nid)
        container = _batch_container(bid, nodes=[char])
        doc = _minimal_doc([container])

        grift_import(doc)
        grift_import(doc)

        assert Entity.objects.filter(pk=uuid.UUID(nid)).count() == 1


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGriftProvenance:
    def test_description_json_records_importer_metadata(self):
        bid = _batch_entity_id()
        container = _batch_container(bid)
        result = grift_import(_minimal_doc([container]))
        assert result.success

        batch = Batch.objects.get(entity_id=bid)
        assert batch.description_json is not None
        assert batch.description_json["format"] == "tap.grift.import.v0"
        data = batch.description_json["data"]
        assert data["importer"] == "grift"
        assert data["grift_version"] == "0"
        assert data["import_mode"] == "upsert"
        assert data["source_batch_entity_id"] == bid

    def test_result_import_mode_is_upsert(self):
        result = grift_import(_minimal_doc())
        assert result.import_mode == "upsert"

    def test_result_reference_time_is_set(self):
        result = grift_import(_minimal_doc())
        assert result.reference_time
        # Basic RFC 3339 sanity: contains "T"
        assert "T" in result.reference_time


# ---------------------------------------------------------------------------
# Identity sanity: entity_type consistency
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGriftIdentitySanity:
    def test_existing_entity_wrong_type_fails_preflight(self):
        """If an entity_id exists in the grid as a different type, preflight fails."""
        bid1 = _batch_entity_id()
        nid = _node_entity_id()

        # First import: creates a character.
        result1 = grift_import(_minimal_doc([_batch_container(bid1, nodes=[_character_node(nid)])]))
        assert result1.success

        # Second import: same entity_id but now claims it's an artifact.
        bid2 = _batch_entity_id()
        wrong_type_node = {
            "entity": {"entity_id": nid, "entity_type": "artifact", "dimensions": {}},
            "node": {"name": "Sting", "power": "glows", "origin": "Erebor"},
        }
        result2 = grift_import(_minimal_doc([_batch_container(bid2, nodes=[wrong_type_node])]))
        assert not result2.success
        assert any(e.code == "entity_type_mismatch" and e.entity_id == nid for e in result2.errors)
        assert result2.counts.batches_imported == 0

    def test_existing_entity_matching_type_succeeds(self):
        """Re-importing an entity with the same entity_type passes preflight."""
        bid1 = _batch_entity_id()
        nid = _node_entity_id()
        result1 = grift_import(_minimal_doc([_batch_container(bid1, nodes=[_character_node(nid)])]))
        assert result1.success

        bid2 = _batch_entity_id()
        result2 = grift_import(
            _minimal_doc([_batch_container(bid2, nodes=[_character_node(nid, name="Frodo Updated")])])
        )
        assert result2.success


# ---------------------------------------------------------------------------
# Multi-batch document
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGriftMultiBatch:
    def test_two_batches_both_imported(self):
        bid1 = _batch_entity_id()
        bid2 = _batch_entity_id()
        nid1 = _node_entity_id()
        nid2 = _node_entity_id()

        doc = _minimal_doc(
            [
                _batch_container(bid1, nodes=[_character_node(nid1, name="Frodo")]),
                _batch_container(bid2, nodes=[_character_node(nid2, name="Sam")]),
            ]
        )

        result = grift_import(doc)
        assert result.success
        assert result.counts.batches_imported == 2
        assert result.counts.nodes_imported == 2
        assert Entity.objects.filter(pk=uuid.UUID(nid1)).exists()
        assert Entity.objects.filter(pk=uuid.UUID(nid2)).exists()

    def test_second_batch_skipped_first_imported(self):
        bid1 = _batch_entity_id()
        bid2 = _batch_entity_id()
        nid1 = _node_entity_id()
        nid2 = _node_entity_id()

        doc1 = _minimal_doc([_batch_container(bid2, nodes=[_character_node(nid2, name="Sam")])])
        grift_import(doc1)

        doc2 = _minimal_doc(
            [
                _batch_container(bid1, nodes=[_character_node(nid1, name="Frodo")]),
                _batch_container(bid2, nodes=[_character_node(nid2, name="Sam")]),
            ]
        )
        result = grift_import(doc2)
        assert result.success
        assert result.counts.batches_imported == 1
        assert result.counts.batches_skipped == 1


