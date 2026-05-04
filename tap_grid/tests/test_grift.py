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

    def test_custom_format_preserved_importer_metadata_nested(self):
        """Incoming batch with a non-importer format keeps its format; importer
        metadata nests under reserved key `_tap_grift_import`."""
        bid = _batch_entity_id()
        batch_node = {
            "name": "Caller batch",
            "description": "",
            "description_json": {
                "format": "example.caller.v1",
                "data": {"caller_key": "caller_value", "nested": {"k": 1}},
            },
            "source": "test",
            "metadata": {},
        }
        container = _batch_container(bid, batch_node=batch_node)
        result = grift_import(_minimal_doc([container]))
        assert result.success

        batch = Batch.objects.get(entity_id=bid)
        assert batch.description_json["format"] == "example.caller.v1"
        data = batch.description_json["data"]
        # Caller-owned keys survive.
        assert data["caller_key"] == "caller_value"
        assert data["nested"] == {"k": 1}
        # Importer metadata lives under the reserved key.
        importer = data["_tap_grift_import"]
        assert importer["importer"] == "grift"
        assert importer["grift_version"] == "0"
        assert importer["import_mode"] == "upsert"
        assert importer["source_batch_entity_id"] == bid

    def test_legacy_importer_format_is_overwritten(self):
        """Incoming format `tap.grift.import.v0` is overwritten entirely — no
        nested duplicates."""
        bid = _batch_entity_id()
        batch_node = {
            "name": "Replay batch",
            "description": "",
            "description_json": {
                "format": "tap.grift.import.v0",
                "data": {"importer": "stale", "imported_at": "1970-01-01T00:00:00Z"},
            },
            "source": "test",
            "metadata": {},
        }
        container = _batch_container(bid, batch_node=batch_node)
        result = grift_import(_minimal_doc([container]))
        assert result.success

        batch = Batch.objects.get(entity_id=bid)
        assert batch.description_json["format"] == "tap.grift.import.v0"
        data = batch.description_json["data"]
        # Fresh importer data present, stale timestamp gone.
        assert data["importer"] == "grift"
        assert data["imported_at"] != "1970-01-01T00:00:00Z"
        # No nested _tap_grift_import — the whole block was overwritten, not nested.
        assert "_tap_grift_import" not in data

    def test_malformed_description_json_falls_back_to_importer_format(self):
        """Incoming description_json with non-dict data falls back to
        importer-only output instead of crashing."""
        bid = _batch_entity_id()
        batch_node = {
            "name": "Malformed batch",
            "description": "",
            "description_json": {"format": "example.bad", "data": "not an object"},
            "source": "test",
            "metadata": {},
        }
        container = _batch_container(bid, batch_node=batch_node)
        result = grift_import(_minimal_doc([container]))
        assert result.success

        batch = Batch.objects.get(entity_id=bid)
        assert batch.description_json["format"] == "tap.grift.import.v0"
        data = batch.description_json["data"]
        assert data["importer"] == "grift"

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


# ---------------------------------------------------------------------------
# Envelope dimensions merged onto imported entities (req-grid-dimension-dc-5)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGriftEnvelopeDimensions:
    """GRIFT imports honor envelope.dimensions on create (req-grid-dimension-dc-5)."""

    def _dimension_node(self, entity_id: str, envelope_dims: dict[str, str]) -> dict[str, Any]:
        return {
            "entity": {
                "entity_id": entity_id,
                "entity_type": "dimension",
                "name": "scoped-dim",
                "dimensions": envelope_dims,
            },
            "node": {"name": "scoped-dim", "description": ""},
        }

    def test_envelope_dims_merged_with_model_defaults(self):
        """Envelope dimensions merge with DEFAULT_DIMENSIONS; non-overlapping keys both present."""
        batch_id = _batch_entity_id()
        node_id = _node_entity_id()
        doc = _minimal_doc(
            [
                _batch_container(
                    batch_id,
                    nodes=[self._dimension_node(node_id, {"tap.env": "genericom-prod"})],
                )
            ]
        )
        result = grift_import(doc)
        assert result.success, result.issues

        entity = Entity.objects.get(pk=uuid.UUID(node_id))
        assert entity.dimensions == {"tap.meta": "dimension", "tap.env": "genericom-prod"}

    def test_envelope_dims_override_model_defaults(self):
        """Envelope key wins over colliding DEFAULT_DIMENSIONS key."""
        batch_id = _batch_entity_id()
        node_id = _node_entity_id()
        doc = _minimal_doc(
            [
                _batch_container(
                    batch_id,
                    nodes=[self._dimension_node(node_id, {"tap.meta": "overridden"})],
                )
            ]
        )
        result = grift_import(doc)
        assert result.success

        entity = Entity.objects.get(pk=uuid.UUID(node_id))
        assert entity.dimensions == {"tap.meta": "overridden"}

    def test_empty_envelope_dims_leaves_only_model_defaults(self):
        """Empty envelope dimensions still applies DEFAULT_DIMENSIONS."""
        batch_id = _batch_entity_id()
        node_id = _node_entity_id()
        doc = _minimal_doc(
            [_batch_container(batch_id, nodes=[self._dimension_node(node_id, {})])]
        )
        result = grift_import(doc)
        assert result.success

        entity = Entity.objects.get(pk=uuid.UUID(node_id))
        assert entity.dimensions == {"tap.meta": "dimension"}





# ---------------------------------------------------------------------------
# Force re-import + batch-scoped sweep + purge
#   spec-grid-import-grift.md req-grid-import-grift-force-reimport
#                             req-grid-import-grift-batch-scoped-sweep
#                             req-grid-import-grift-sweep-purge
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGriftForceReimport:
    @pytest.fixture(autouse=True)
    def _debug_on(self, settings):
        """Most tests exercise force re-import, which requires DEBUG=True.
        Individual tests that verify the gate flip DEBUG back to False locally."""
        settings.DEBUG = True

    def _initial_doc(self, batch_id: str, node_ids: list[str]) -> dict[str, Any]:
        return _minimal_doc(
            [
                _batch_container(
                    batch_id,
                    nodes=[_character_node(nid, name=f"char-{i}") for i, nid in enumerate(node_ids)],
                )
            ]
        )

    def test_force_reimport_re_applies_edited_content(self):
        """A revised batch passed via force_batches updates nodes that changed."""
        from tap_grid.models import BatchEvent, BatchEventType

        bid = _batch_entity_id()
        nid = _node_entity_id()
        result = grift_import(self._initial_doc(bid, [nid]))
        assert result.success

        # Revise node payload and force re-import.
        revised = _minimal_doc(
            [_batch_container(bid, nodes=[_character_node(nid, name="Renamed", bio="New bio")])]
        )
        result2 = grift_import(revised, force_batches=[bid])
        assert result2.success, result2.errors
        assert result2.counts.batches_force_reimported == 1

        # Payload updated in place.
        from plugins.lotr.models import Character

        c = Character.objects.get(entity_id=uuid.UUID(nid))
        assert c.name == "Renamed"
        assert c.bio == "New bio"

        # FORCE_REIMPORT audit event landed.
        evt = BatchEvent.objects.filter(
            batch__entity_id=bid, event_type=BatchEventType.FORCE_REIMPORT
        ).first()
        assert evt is not None
        assert evt.metadata.get("purge") is False

    def test_force_reimport_refused_without_debug(self, settings):
        """DEBUG=False rejects force re-import with a dedicated error code."""
        settings.DEBUG = False
        bid = _batch_entity_id()
        doc = self._initial_doc(bid, [_node_entity_id()])
        result = grift_import(doc, force_batches=[bid])
        assert not result.success
        assert any(e.code == "force_reimport_refused_production" for e in result.errors)

    def test_purge_requires_force_batches(self):
        """--purge without --force-batches is rejected at the API."""
        result = grift_import(_minimal_doc([]), purge=True)
        assert not result.success
        assert any(e.code == "purge_requires_force_reimport" for e in result.errors)

    def test_purge_refused_without_debug(self, settings):
        """DEBUG=False rejects --purge even when --force-batches is passed."""
        settings.DEBUG = False
        bid = _batch_entity_id()
        doc = self._initial_doc(bid, [_node_entity_id()])
        result = grift_import(doc, force_batches=[bid], purge=True)
        assert not result.success
        # Both gates trip; purge-specific error is reported.
        assert any(
            e.code in ("sweep_purge_refused_production", "force_reimport_refused_production")
            for e in result.errors
        )

    def test_sweep_tombstones_orphan_nodes(self):
        """A revised batch dropping a node tombstones it via the sweep."""
        bid = _batch_entity_id()
        nid_keep = _node_entity_id()
        nid_drop = _node_entity_id()
        grift_import(self._initial_doc(bid, [nid_keep, nid_drop]))

        revised = _minimal_doc(
            [_batch_container(bid, nodes=[_character_node(nid_keep, name="char-0")])]
        )
        result = grift_import(revised, force_batches=[bid])
        assert result.success, result.errors

        # Swept entity reported.
        batch_summary = result.imported_batches[0]
        swept_ids = {s.entity_id for s in batch_summary.swept_entities}
        assert nid_drop in swept_ids
        assert nid_keep not in swept_ids

        # Tombstone applied (entity present but soft-deleted).
        dropped = Entity.objects.get(pk=uuid.UUID(nid_drop))
        assert dropped.deleted_at is not None
        kept = Entity.objects.get(pk=uuid.UUID(nid_keep))
        assert kept.deleted_at is None

    def test_sweep_skips_externally_written_entity(self):
        """Guardrail A — an entity touched by a different batch is skipped."""
        from tap_grid.batch import create_batch
        from tap_grid.caller_context import CallerContext
        from tap_grid.services import write_batch
        from tap_grid.service_types import WriteOperation

        bid = _batch_entity_id()
        nid = _node_entity_id()
        grift_import(self._initial_doc(bid, [nid]))

        # Another batch updates the node after initial import.
        other_batch = create_batch(name="other")
        ctx = CallerContext(user=None, batch_id=str(other_batch.entity_id))
        write_batch(
            [WriteOperation(verb="replace_node", target=nid, payload={"name": "Touched", "bio": "By other"})],
            caller_context=ctx,
        )

        # Revise the batch to drop the node — sweep should skip via Guardrail A.
        revised = _minimal_doc([_batch_container(bid, nodes=[])])
        result = grift_import(revised, force_batches=[bid])
        assert result.success, result.errors

        summary = result.imported_batches[0]
        assert len(summary.sweep_skipped) == 1
        assert summary.sweep_skipped[0].reason == "sweep_skipped_external_write"
        assert summary.sweep_skipped[0].entity_id == nid

        # Entity survives.
        kept = Entity.objects.get(pk=uuid.UUID(nid))
        assert kept.deleted_at is None

    def test_sweep_skips_referenced_entity(self):
        """Guardrail B — a node candidate with a surviving edge is skipped."""
        bid = _batch_entity_id()
        wielder = _node_entity_id()
        artifact = _node_entity_id()
        edge_id = _edge_entity_id()

        def _artifact_node(nid: str, name: str) -> dict[str, Any]:
            return {
                "entity": {
                    "entity_id": nid,
                    "entity_type": "artifact",
                    "name": name,
                    "dimensions": {},
                },
                "node": {"name": name, "power": "modest", "origin": "Valinor"},
            }

        initial = _minimal_doc(
            [
                _batch_container(
                    bid,
                    nodes=[_character_node(wielder, "Wielder"), _artifact_node(artifact, "Ring")],
                    edges=[_wields_edge(edge_id, wielder, artifact)],
                )
            ]
        )
        r0 = grift_import(initial)
        assert r0.success, r0.errors

        # Revise to drop the artifact NODE but keep the edge referencing it.
        # The edge's to_entity_id still points at a grid entity (artifact is
        # present from the initial import), so preflight doesn't trip. After
        # the upsert phase the artifact is a sweep candidate; Guardrail B
        # sees the surviving edge and skips the sweep.
        revised = _minimal_doc(
            [
                _batch_container(
                    bid,
                    nodes=[_character_node(wielder, "Wielder")],
                    edges=[_wields_edge(edge_id, wielder, artifact)],
                )
            ]
        )
        result = grift_import(revised, force_batches=[bid])
        assert result.success, result.errors
        assert len(result.imported_batches) == 1
        summary = result.imported_batches[0]
        reasons = {s.reason for s in summary.sweep_skipped}
        assert "sweep_skipped_referenced" in reasons
        # Artifact should still be live (not tombstoned).
        live = Entity.objects.get(pk=uuid.UUID(artifact))
        assert live.deleted_at is None

    def test_sweep_strict_aborts_on_guardrail_miss(self):
        """--sweep-strict aborts the entire force re-import if any candidate fails."""
        from tap_grid.batch import create_batch
        from tap_grid.caller_context import CallerContext
        from tap_grid.services import write_batch
        from tap_grid.service_types import WriteOperation

        bid = _batch_entity_id()
        nid_keep = _node_entity_id()
        nid_drop = _node_entity_id()
        grift_import(self._initial_doc(bid, [nid_keep, nid_drop]))

        # Another batch touches nid_drop so it fails Guardrail A.
        other_batch = create_batch(name="external")
        ctx = CallerContext(user=None, batch_id=str(other_batch.entity_id))
        write_batch(
            [WriteOperation(verb="replace_node", target=nid_drop, payload={"name": "Touched", "bio": "X"})],
            caller_context=ctx,
        )

        # Strict-mode force re-import should abort — no writes applied.
        revised = _minimal_doc(
            [_batch_container(bid, nodes=[_character_node(nid_keep, name="Changed", bio="Y")])]
        )
        result = grift_import(revised, force_batches=[bid], sweep_strict=True)
        assert not result.success
        assert any(e.code == "sweep_strict_aborted" for e in result.errors)

        # Name change on nid_keep was rolled back.
        from plugins.lotr.models import Character

        unchanged = Character.objects.get(entity_id=uuid.UUID(nid_keep))
        assert unchanged.name == "char-0"  # original

    def test_purge_hard_deletes_orphans(self):
        """--purge removes the entity and its batch-scoped BatchEvent rows."""
        from tap_grid.models import BatchEvent

        bid = _batch_entity_id()
        nid = _node_entity_id()
        grift_import(self._initial_doc(bid, [nid]))

        # Confirm entity + its BatchEvent exist.
        assert Entity.objects.filter(pk=uuid.UUID(nid)).exists()
        assert BatchEvent.objects.filter(entity_id=uuid.UUID(nid)).exists()

        # Revise to drop the node, purge enabled.
        revised = _minimal_doc([_batch_container(bid, nodes=[])])
        result = grift_import(revised, force_batches=[bid], purge=True)
        assert result.success, result.errors

        summary = result.imported_batches[0]
        assert any(s.action == "purge" for s in summary.swept_entities)

        # Entity and its BatchEvent rows are gone from the DB.
        assert not Entity.objects.filter(pk=uuid.UUID(nid)).exists()
        assert not BatchEvent.objects.filter(entity_id=uuid.UUID(nid)).exists()

    def test_force_reimport_unnamed_batch_reports_not_found(self):
        """force_batches naming an unknown id emits a diagnostic error."""
        bogus = str(uuid.uuid4())
        result = grift_import(_minimal_doc([]), force_batches=[bogus])
        assert not result.success
        assert any(e.code == "force_reimport_batch_not_found" for e in result.errors)


# ---------------------------------------------------------------------------
# Identity Sanity: envelope/payload name match
# (req-grid-import-grift-preflight "Envelope/Payload Name Match")
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEnvelopePayloadNameMatch:
    def _node_with_names(self, entity_id: str, envelope_name: str | None, payload_name: str) -> dict[str, Any]:
        envelope: dict[str, Any] = {
            "entity_id": entity_id,
            "entity_type": "character",
            "dimensions": {},
        }
        if envelope_name is not None:
            envelope["name"] = envelope_name
        return {
            "entity": envelope,
            "node": {"name": payload_name, "bio": "A hobbit"},
        }

    def test_matched_names_pass_preflight(self):
        nid = _node_entity_id()
        node = self._node_with_names(nid, envelope_name="Frodo", payload_name="Frodo")
        container = _batch_container(_batch_entity_id(), nodes=[node])
        result = grift_import(_minimal_doc([container]))
        assert result.success
        assert not any(e.code == "envelope_payload_name_mismatch" for e in result.errors)

    def test_envelope_name_omitted_passes(self):
        """Bundles that omit envelope.name keep working — the spine projection
        is materialized from the model's name on import."""
        nid = _node_entity_id()
        node = self._node_with_names(nid, envelope_name=None, payload_name="Frodo")
        container = _batch_container(_batch_entity_id(), nodes=[node])
        result = grift_import(_minimal_doc([container]))
        assert result.success
        assert not any(e.code == "envelope_payload_name_mismatch" for e in result.errors)

    def test_envelope_name_empty_rejected_by_schema(self):
        """Explicitly-empty envelope.name is rejected at the document-schema
        layer before the mismatch check runs. This makes the mismatch
        check's empty-envelope-name guard belt-and-suspenders, never the
        primary defense."""
        nid = _node_entity_id()
        node = self._node_with_names(nid, envelope_name="", payload_name="Frodo")
        container = _batch_container(_batch_entity_id(), nodes=[node])
        result = grift_import(_minimal_doc([container]))
        assert not result.success
        assert any(e.code == "schema_validation_failed" for e in result.errors)
        assert not any(e.code == "envelope_payload_name_mismatch" for e in result.errors)

    def test_whitespace_only_difference_passes(self):
        """Surrounding whitespace is trimmed before comparison."""
        nid = _node_entity_id()
        node = self._node_with_names(nid, envelope_name="  Frodo  ", payload_name="Frodo")
        container = _batch_container(_batch_entity_id(), nodes=[node])
        result = grift_import(_minimal_doc([container]))
        assert result.success
        assert not any(e.code == "envelope_payload_name_mismatch" for e in result.errors)

    def test_mismatch_fails_preflight(self):
        nid = _node_entity_id()
        node = self._node_with_names(nid, envelope_name="Bilbo", payload_name="Frodo")
        container = _batch_container(_batch_entity_id(), nodes=[node])
        result = grift_import(_minimal_doc([container]))
        assert not result.success
        mismatches = [e for e in result.errors if e.code == "envelope_payload_name_mismatch"]
        assert len(mismatches) == 1
        # Issue carries enough context to be operator-actionable.
        assert mismatches[0].entity_id == nid
        assert mismatches[0].entity_type == "character"
        assert "Bilbo" in mismatches[0].message and "Frodo" in mismatches[0].message
        assert mismatches[0].path.endswith(".entity.name")

    def test_mismatches_accrue_across_file(self):
        """Multiple offending nodes each produce their own issue; preflight
        does not stop at the first mismatch."""
        nid_a = _node_entity_id()
        nid_b = _node_entity_id()
        node_a = self._node_with_names(nid_a, envelope_name="X", payload_name="A")
        node_b = self._node_with_names(nid_b, envelope_name="Y", payload_name="B")
        container = _batch_container(_batch_entity_id(), nodes=[node_a, node_b])
        result = grift_import(_minimal_doc([container]))
        assert not result.success
        mismatches = [e for e in result.errors if e.code == "envelope_payload_name_mismatch"]
        offending_ids = {e.entity_id for e in mismatches}
        assert offending_ids == {nid_a, nid_b}

    def test_mismatch_blocks_writes(self):
        """A failing preflight must not mutate the database."""
        nid = _node_entity_id()
        node = self._node_with_names(nid, envelope_name="Bilbo", payload_name="Frodo")
        container = _batch_container(_batch_entity_id(), nodes=[node])
        result = grift_import(_minimal_doc([container]))
        assert not result.success
        assert not Entity.objects.filter(pk=uuid.UUID(nid)).exists()
