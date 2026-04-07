"""Tests for GRIFT subgraph serializers — spec-grift-subgraph."""

from __future__ import annotations

import uuid

import pytest

from tap_grid.grift.subgraph import (
    batch_resolve_shapes,
    batch_resolve_typed_models,
    serialize_edge_extended,
    serialize_edge_full,
    serialize_edge_lite,
    serialize_entity_envelope,
    serialize_node_extended,
    serialize_node_full,
    serialize_node_lite,
    serialize_node_payload,
    serialize_subgraph,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_character(name="Frodo", bio="A hobbit"):
    from tap_grid.caller_context import CallerContext, set_caller_context
    from tap_grid.models import Entity

    ctx = CallerContext(user=None, batch_id=str(uuid.uuid4()))
    set_caller_context(ctx)

    from plugins.lotr.models import Character

    entity = Entity.objects.create(entity_type="character", name=name)
    character = Character.objects.create(entity=entity, name=name, bio=bio)
    return character


def _make_edge(from_entity, to_entity, edge_type="KNOWS"):
    from tap_grid.caller_context import CallerContext, set_caller_context
    from tap_grid.models import Edge, Entity

    ctx = CallerContext(user=None, batch_id=str(uuid.uuid4()))
    set_caller_context(ctx)

    edge_entity = Entity.objects.create(entity_type="edge", name=edge_type)
    return Edge.objects.create(
        entity=edge_entity,
        from_entity=from_entity,
        to_entity=to_entity,
        edge_type=edge_type,
        properties={},
    )


# ---------------------------------------------------------------------------
# Entity envelope
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSerializeEntityEnvelope:
    def test_all_fields_present(self):
        character = _make_character()
        envelope = serialize_entity_envelope(character.entity)
        assert "entity_id" in envelope
        assert "entity_type" in envelope
        assert "name" in envelope
        assert "dimensions" in envelope
        assert "created_at" in envelope
        assert "updated_at" in envelope
        assert "deleted_at" in envelope

    def test_entity_id_is_string(self):
        character = _make_character()
        envelope = serialize_entity_envelope(character.entity)
        assert isinstance(envelope["entity_id"], str)

    def test_entity_type_matches(self):
        character = _make_character()
        envelope = serialize_entity_envelope(character.entity)
        assert envelope["entity_type"] == "character"


# ---------------------------------------------------------------------------
# Node payload
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSerializeNodePayload:
    def test_extracts_field_schema_keys(self):
        character = _make_character(name="Frodo", bio="A hobbit")
        payload = serialize_node_payload(character)
        assert "name" in payload
        assert "bio" in payload
        assert payload["name"] == "Frodo"
        assert payload["bio"] == "A hobbit"

    def test_excludes_non_field_schema_keys(self):
        character = _make_character()
        payload = serialize_node_payload(character)
        assert "entity_id" not in payload
        assert "batch_id" not in payload
        assert "flip_map" not in payload


# ---------------------------------------------------------------------------
# Node lite
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSerializeNodeLite:
    def test_flat_shape(self):
        character = _make_character()
        node = serialize_node_lite(character.entity)
        assert "entity_id" in node
        assert "entity_type" in node
        assert "name" in node
        assert "entity" not in node
        assert "node" not in node


# ---------------------------------------------------------------------------
# Node full
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSerializeNodeFull:
    def test_nested_shape(self):
        character = _make_character(name="Frodo", bio="A hobbit")
        node = serialize_node_full(character.entity, character)
        assert "entity" in node
        assert "node" in node
        assert node["entity"]["entity_id"] == str(character.entity_id)
        assert node["entity"]["entity_type"] == "character"
        assert node["node"]["name"] == "Frodo"
        assert node["node"]["bio"] == "A hobbit"

    def test_none_typed_model(self):
        character = _make_character()
        node = serialize_node_full(character.entity, None)
        assert node["node"] == {}


# ---------------------------------------------------------------------------
# Node extended
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSerializeNodeExtended:
    def test_includes_presentation_fields(self):
        character = _make_character(name="Frodo")
        node = serialize_node_extended(character.entity, character, icon_url="/static/icon.svg", shape="ellipse")
        assert node["icon_url"] == "/static/icon.svg"
        assert node["shape"] == "ellipse"
        assert "url_id" in node
        assert "--" in node["url_id"]

    def test_url_id_derived_from_name(self):
        character = _make_character(name="Frodo Baggins")
        node = serialize_node_extended(character.entity, character)
        assert node["url_id"].startswith("frodo-baggins--")

    def test_still_has_entity_and_node(self):
        character = _make_character()
        node = serialize_node_extended(character.entity, character)
        assert "entity" in node
        assert "node" in node


# ---------------------------------------------------------------------------
# Edge lite
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSerializeEdgeLite:
    def test_flat_shape(self):
        c1 = _make_character("Frodo")
        c2 = _make_character("Sam")
        edge = _make_edge(c1.entity, c2.entity, "KNOWS")
        lite = serialize_edge_lite(edge)
        assert "entity_id" in lite
        assert "from_entity_id" in lite
        assert "to_entity_id" in lite
        assert "edge_type" in lite
        assert "properties" in lite
        assert "entity" not in lite


# ---------------------------------------------------------------------------
# Edge full
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSerializeEdgeFull:
    def test_nested_shape(self):
        c1 = _make_character("Frodo")
        c2 = _make_character("Sam")
        edge = _make_edge(c1.entity, c2.entity, "KNOWS")
        # select_related needed for full serialization
        from tap_grid.models import Edge

        edge = Edge.objects.select_related("entity").get(pk=edge.pk)
        full = serialize_edge_full(edge)
        assert "entity" in full
        assert "edge" in full
        assert full["entity"]["entity_type"] == "edge"
        assert full["edge"]["from_entity_id"] == str(c1.entity_id)
        assert full["edge"]["to_entity_id"] == str(c2.entity_id)
        assert full["edge"]["edge_type"] == "KNOWS"


# ---------------------------------------------------------------------------
# Edge extended
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSerializeEdgeExtended:
    def test_includes_endpoint_names(self):
        c1 = _make_character("Frodo")
        c2 = _make_character("Sam")
        edge = _make_edge(c1.entity, c2.entity, "KNOWS")
        from tap_grid.models import Edge

        edge = Edge.objects.select_related("entity").get(pk=edge.pk)
        ext = serialize_edge_extended(edge, from_name="Frodo", to_name="Sam")
        assert ext["from_name"] == "Frodo"
        assert ext["to_name"] == "Sam"
        assert "entity" in ext
        assert "edge" in ext


# ---------------------------------------------------------------------------
# Batch resolution
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBatchResolveTypedModels:
    def test_resolves_by_entity_type(self):
        c1 = _make_character("Frodo")
        c2 = _make_character("Sam")
        entities = [c1.entity, c2.entity]
        result = batch_resolve_typed_models(entities, "default")
        assert str(c1.entity_id) in result
        assert str(c2.entity_id) in result
        assert result[str(c1.entity_id)].name == "Frodo"

    def test_skips_edge_entity_type(self):
        from tap_grid.models import Entity

        edge_entity = Entity.objects.create(entity_type="edge", name="test")
        result = batch_resolve_typed_models([edge_entity], "default")
        assert str(edge_entity.pk) not in result


@pytest.mark.django_db
class TestBatchResolveShapes:
    def test_returns_shape_from_default_display(self):
        result = batch_resolve_shapes({"character"})
        assert "character" in result
        assert result["character"] == "ellipse"

    def test_unknown_type_defaults_to_ellipse(self):
        result = batch_resolve_shapes({"nonexistent_xyz"})
        assert result["nonexistent_xyz"] == "ellipse"


# ---------------------------------------------------------------------------
# Subgraph convenience
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSerializeSubgraph:
    def test_lite_returns_flat_nodes(self):
        c = _make_character()
        result = serialize_subgraph([c.entity], [], layer="lite", db_alias="default")
        assert "nodes" in result
        assert "edges" in result
        assert "entity_id" in result["nodes"][0]
        assert "entity" not in result["nodes"][0]

    def test_full_returns_nested_nodes(self):
        c = _make_character()
        result = serialize_subgraph([c.entity], [], layer="full", db_alias="default")
        assert "entity" in result["nodes"][0]
        assert "node" in result["nodes"][0]

    def test_extended_returns_presentation_fields(self):
        c = _make_character(name="Frodo")
        result = serialize_subgraph([c.entity], [], layer="extended", db_alias="default")
        node = result["nodes"][0]
        assert "icon_url" in node
        assert "shape" in node
        assert "url_id" in node
