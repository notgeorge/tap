"""Tests for the TAP gryphon language — parser, executor, Search model, and search service.

Covers spec-grid-traversal-language.md and spec-grid-traversal-execution.md.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from tap_grid.exceptions import SearchExecutionError
from tap_grid.gryphon.ast_nodes import (
    AndPred,
    Comparison,
    DotStep,
    GryphonAST,
    KeyStep,
    NotPred,
    OrPred,
    ParamRef,
    WildcardStep,
)
from tap_grid.gryphon.parser import GryphonParseError, parse_gryphon
from tap_grid.models import Search
from tap_grid.search import execute_search

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HUB_SPOKE_QUERY = [
    "MATCH (hub)-[e]-(neighbor)",
    "WHERE hub.entity_id = $entity_id",
    "RETURN hub, e, neighbor",
]

HUB_SPOKE_QUERY_STR = "MATCH (hub)-[e]-(neighbor) WHERE hub.entity_id = $entity_id RETURN hub, e, neighbor"


def _gryphon_search(**kwargs):
    defaults = {
        "name": "Hub and Spoke",
        "search_type": "gryphon",
        "root": "node",
        "definition": {"query": HUB_SPOKE_QUERY},
    }
    defaults.update(kwargs)
    return Search(**defaults)


# ---------------------------------------------------------------------------
# TestGryphonParser — req-grid-traversal-lang-shape / storage / patterns / filters / combinators / params / returns
# ---------------------------------------------------------------------------


class TestGryphonParser:
    def test_hub_spoke_list_form_parses(self):
        ast = parse_gryphon(HUB_SPOKE_QUERY)
        assert isinstance(ast, GryphonAST)
        assert len(ast.match_clauses) == 1

    def test_hub_spoke_string_form_parses(self):
        ast = parse_gryphon(HUB_SPOKE_QUERY_STR)
        assert isinstance(ast, GryphonAST)
        assert len(ast.match_clauses) == 1

    def test_list_and_string_forms_equivalent(self):
        """req-grid-traversal-lang-storage-3: both forms normalize to the same AST."""
        ast_list = parse_gryphon(HUB_SPOKE_QUERY)
        ast_str = parse_gryphon(HUB_SPOKE_QUERY_STR)
        assert ast_list == ast_str

    def test_match_clause_structure(self):
        """req-grid-traversal-lang-patterns: node/edge variables and direction."""
        ast = parse_gryphon(HUB_SPOKE_QUERY)
        mc = ast.match_clauses[0]
        assert mc.path_var is None
        assert len(mc.patterns) == 1
        pattern = mc.patterns[0]
        assert len(pattern.nodes) == 2
        assert len(pattern.edges) == 1
        hub_node = pattern.nodes[0]
        assert hub_node.variable == "hub"
        edge = pattern.edges[0]
        assert edge.variable == "e"
        assert edge.direction == "any"

    def test_outbound_edge_direction(self):
        """req-grid-traversal-lang-patterns-3: directed outbound."""
        ast = parse_gryphon("MATCH (a)-[e]->(b) WHERE a.entity_id = $id RETURN a, e, b")
        edge = ast.match_clauses[0].patterns[0].edges[0]
        assert edge.direction == "out"

    def test_inbound_edge_direction(self):
        """req-grid-traversal-lang-patterns-3: directed inbound."""
        ast = parse_gryphon("MATCH (a)<-[e]-(b) WHERE a.entity_id = $id RETURN a, e, b")
        edge = ast.match_clauses[0].patterns[0].edges[0]
        assert edge.direction == "in"

    def test_typed_edge(self):
        """req-grid-traversal-lang-patterns-2: typed edge."""
        ast = parse_gryphon("MATCH (a)-[e:ON_HOST]-(b) WHERE a.entity_id = $id RETURN a")
        edge = ast.match_clauses[0].patterns[0].edges[0]
        assert edge.edge_type == "ON_HOST"

    def test_node_label(self):
        """req-grid-traversal-lang-patterns-1: node label."""
        ast = parse_gryphon("MATCH (h:host)-[e]-(n) WHERE h.entity_id = $id RETURN h")
        node = ast.match_clauses[0].patterns[0].nodes[0]
        assert node.label == "host"
        assert node.variable == "h"

    def test_path_variable(self):
        """req-grid-traversal-lang-patterns-4: path variable binding."""
        ast = parse_gryphon("MATCH p = (a)-[e]-(b) WHERE a.entity_id = $id RETURN p")
        assert ast.match_clauses[0].path_var == "p"

    def test_where_clause_parsed(self):
        ast = parse_gryphon(HUB_SPOKE_QUERY)
        assert ast.where_clause is not None
        pred = ast.where_clause.predicate
        assert isinstance(pred, Comparison)
        assert pred.field_path.variable == "hub"
        assert isinstance(pred.field_path.steps[0], DotStep)
        assert pred.field_path.steps[0].name == "entity_id"
        assert pred.op == "="
        assert isinstance(pred.value, ParamRef)
        assert pred.value.name == "entity_id"

    def test_and_predicate(self):
        """req-grid-traversal-lang-combinators-1: AND."""
        ast = parse_gryphon('MATCH (n)-[e]-(m) WHERE n.entity_id = $id AND n.name = "web01" RETURN n')
        pred = ast.where_clause.predicate
        assert isinstance(pred, AndPred)

    def test_or_predicate(self):
        """req-grid-traversal-lang-combinators-2: OR."""
        ast = parse_gryphon('MATCH (n)-[e]-(m) WHERE n.entity_id = $id OR n.name = "web01" RETURN n')
        pred = ast.where_clause.predicate
        assert isinstance(pred, OrPred)

    def test_not_predicate(self):
        """req-grid-traversal-lang-combinators-3: NOT."""
        ast = parse_gryphon('MATCH (n)-[e]-(m) WHERE NOT n.name = "excluded" RETURN n')
        pred = ast.where_clause.predicate
        assert isinstance(pred, NotPred)

    def test_bracket_key_access(self):
        """req-grid-traversal-lang-filters-4: keyed JSON access."""
        ast = parse_gryphon('MATCH (n)-[e]-(m) WHERE n.dimensions["tap.graph"] = "web" RETURN n')
        pred = ast.where_clause.predicate
        assert isinstance(pred, Comparison)
        steps = pred.field_path.steps
        assert isinstance(steps[0], DotStep) and steps[0].name == "dimensions"
        assert isinstance(steps[1], KeyStep) and steps[1].key == "tap.graph"

    def test_array_wildcard_access(self):
        """req-grid-traversal-lang-filters-6: array wildcard [*]."""
        ast = parse_gryphon("MATCH (n)-[e]-(m) WHERE n.properties.aliases[*].name = $alias RETURN n")
        pred = ast.where_clause.predicate
        steps = pred.field_path.steps
        assert any(isinstance(s, WildcardStep) for s in steps)

    def test_return_clause_items(self):
        """req-grid-traversal-lang-returns-3: variable returns."""
        ast = parse_gryphon(HUB_SPOKE_QUERY)
        ret = ast.return_clause
        assert ret.items is not None
        assert len(ret.items) == 3
        variables = [item.path.variable for item in ret.items]
        assert "hub" in variables
        assert "e" in variables
        assert "neighbor" in variables

    def test_return_alias(self):
        """req-grid-traversal-lang-returns-5: AS alias."""
        ast = parse_gryphon("MATCH (h)-[e]-(n) WHERE h.entity_id = $id RETURN h.name AS accepted_name")
        ret = ast.return_clause
        assert ret.items is not None
        assert ret.items[0].alias == "accepted_name"

    def test_omitted_return_is_none(self):
        """req-grid-traversal-lang-returns-1: omitted RETURN → items=None → graph envelope."""
        ast = parse_gryphon("MATCH (hub)-[e]-(neighbor) WHERE hub.entity_id = $entity_id")
        assert ast.return_clause.items is None

    def test_required_params_extracted(self):
        ast = parse_gryphon(HUB_SPOKE_QUERY)
        assert ast.required_params() == frozenset({"entity_id"})

    def test_invalid_syntax_raises_parse_error(self):
        """req-grid-traversal-exec-scope.sec-3: unsupported syntax rejected."""
        with pytest.raises(GryphonParseError):
            parse_gryphon("MATCH (")

    def test_empty_string_raises_parse_error(self):
        with pytest.raises(GryphonParseError):
            parse_gryphon("")

    def test_node_only_pattern_parses(self):
        """req-grid-traversal-lang-patterns: node-only MATCH pattern is valid syntax."""
        ast = parse_gryphon("MATCH (c:character) RETURN c.entity_id, c.name")
        mc = ast.match_clauses[0]
        pattern = mc.patterns[0]
        assert len(pattern.nodes) == 1
        assert len(pattern.edges) == 0
        assert pattern.nodes[0].label == "character"

    def test_node_only_no_label_parses(self):
        """Node-only pattern without label is syntactically valid."""
        ast = parse_gryphon("MATCH (n) RETURN n.entity_id")
        pattern = ast.match_clauses[0].patterns[0]
        assert len(pattern.edges) == 0
        assert pattern.nodes[0].label is None


# ---------------------------------------------------------------------------
# TestGryphonExecutor — req-grid-traversal-exec-pipeline
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True, databases=["default", "search_readonly"])
class TestGryphonExecutor:
    def test_hub_spoke_returns_hub_and_neighbors(self):
        """Hub-and-spoke traversal returns hub + one-hop neighbors and edges."""
        import uuid

        from tap_grid.caller_context import CallerContext, set_caller_context
        from tap_grid.models import Edge, Entity

        ctx = CallerContext(user=None, batch_id=str(uuid.uuid4()))
        set_caller_context(ctx)

        hub = Entity.objects.create(entity_type="character", name="Frodo")
        neighbor = Entity.objects.create(entity_type="location", name="The Shire")
        Edge.objects.create(
            entity=Entity.objects.create(entity_type="edge"),
            from_entity=hub,
            to_entity=neighbor,
            edge_type="LOCATED_IN",
        )

        search = Search(
            search_type="gryphon",
            root="node",
            name="test",
            definition={"query": HUB_SPOKE_QUERY},
        )
        result = execute_search(search, inputs={"entity_id": str(hub.pk)})

        node_ids = {n["entity"]["entity_id"] for n in result["nodes"]}
        assert str(hub.pk) in node_ids
        assert str(neighbor.pk) in node_ids
        assert len(result["edges"]) == 1

    def test_outbound_only_direction(self):
        """Outbound-only pattern excludes inbound-only neighbors."""
        import uuid

        from tap_grid.caller_context import CallerContext, set_caller_context
        from tap_grid.models import Edge, Entity

        ctx = CallerContext(user=None, batch_id=str(uuid.uuid4()))
        set_caller_context(ctx)

        hub = Entity.objects.create(entity_type="character", name="Frodo")
        outbound_neighbor = Entity.objects.create(entity_type="location", name="Rivendell")
        inbound_neighbor = Entity.objects.create(entity_type="character", name="Gandalf")
        edge_entity_out = Entity.objects.create(entity_type="edge")
        edge_entity_in = Entity.objects.create(entity_type="edge")
        Edge.objects.create(
            entity=edge_entity_out,
            from_entity=hub,
            to_entity=outbound_neighbor,
            edge_type="VISITED",
        )
        Edge.objects.create(
            entity=edge_entity_in,
            from_entity=inbound_neighbor,
            to_entity=hub,
            edge_type="KNOWS",
        )

        search = Search(
            search_type="gryphon",
            root="node",
            name="test",
            definition={
                "query": "MATCH (hub)-[e]->(neighbor) WHERE hub.entity_id = $entity_id RETURN hub, e, neighbor"
            },
        )
        result = execute_search(search, inputs={"entity_id": str(hub.pk)})
        node_ids = {n["entity"]["entity_id"] for n in result["nodes"]}
        assert str(outbound_neighbor.pk) in node_ids
        assert str(inbound_neighbor.pk) not in node_ids

    def test_hub_not_found_returns_empty(self):
        """Missing hub entity returns empty nodes/edges with a warning."""
        import uuid

        search = Search(
            search_type="gryphon",
            root="node",
            name="test",
            definition={"query": HUB_SPOKE_QUERY},
        )
        missing_id = str(uuid.uuid4())
        result = execute_search(search, inputs={"entity_id": missing_id})
        assert result["nodes"] == []
        assert result["edges"] == []

    def test_missing_required_input_raises(self):
        """req-grid-traversal-exec-scope.sec-4: inputs validated before execution."""
        search = Search(
            search_type="gryphon",
            root="node",
            name="test",
            definition={"query": HUB_SPOKE_QUERY},
        )
        with pytest.raises(SearchExecutionError, match="entity_id"):
            execute_search(search, inputs={})

    def test_unsupported_multi_hop_raises(self):
        """V1 rejects bounded multi-hop patterns."""
        search = Search(
            search_type="gryphon",
            root="node",
            name="test",
            definition={"query": "MATCH (a)-[e*1..3]-(b) WHERE a.entity_id = $entity_id RETURN a"},
        )
        with pytest.raises(SearchExecutionError, match="[Uu]nsupported"):
            execute_search(search, inputs={"entity_id": "00000000-0000-0000-0000-000000000000"})

    def test_type_scan_returns_projected_nodes(self):
        """req-grid-traversal-lang-returns-4: type scan with field projection."""
        import uuid

        from plugins.lotr.models import Character
        from tap_grid.caller_context import CallerContext, set_caller_context
        from tap_grid.models import Entity

        ctx = CallerContext(user=None, batch_id=str(uuid.uuid4()))
        set_caller_context(ctx)

        for name in ("Frodo", "Sam"):
            entity = Entity.objects.create(entity_type="character", name=name)
            Character.objects.create(entity=entity, name=name, bio=f"{name} bio")

        search = Search(
            search_type="gryphon",
            root="node",
            name="test",
            definition={"query": "MATCH (c:character) RETURN c.entity_id, c.name, c.bio"},
        )
        result = execute_search(search, inputs={})

        assert "nodes" in result
        assert "edges" in result
        assert result["edges"] == []
        assert len(result["nodes"]) >= 2
        node = result["nodes"][0]
        assert "entity_id" in node
        assert "name" in node
        assert "bio" in node

    def test_type_scan_envelope_when_return_omitted(self):
        """req-grid-traversal-lang-returns-1: type scan without RETURN gives graph envelope."""
        import uuid

        from plugins.lotr.models import Character
        from tap_grid.caller_context import CallerContext, set_caller_context
        from tap_grid.models import Entity

        ctx = CallerContext(user=None, batch_id=str(uuid.uuid4()))
        set_caller_context(ctx)

        entity = Entity.objects.create(entity_type="character", name="Gandalf")
        Character.objects.create(entity=entity, name="Gandalf", bio="A wizard.")

        search = Search(
            search_type="gryphon",
            root="node",
            name="test",
            definition={"query": "MATCH (c:character)"},
        )
        result = execute_search(search, inputs={})

        assert "nodes" in result
        node = result["nodes"][0]
        # Graph envelope nodes use GRIFT full shape: {entity: {...}, node: {...}}.
        assert "entity" in node
        assert "node" in node
        assert "entity_id" in node["entity"]
        assert "entity_type" in node["entity"]
        assert "name" in node["entity"]

    def test_type_scan_no_label_raises(self):
        """Type scan requires a node label to know which entity type to scan."""
        search = Search(
            search_type="gryphon",
            root="node",
            name="test",
            definition={"query": "MATCH (c) RETURN c.entity_id"},
        )
        with pytest.raises(SearchExecutionError, match="[Ll]abel"):
            execute_search(search, inputs={})

    def test_type_scan_unknown_label_raises(self):
        """Type scan with an unregistered entity type raises SearchExecutionError."""
        search = Search(
            search_type="gryphon",
            root="node",
            name="test",
            definition={"query": "MATCH (c:nonexistent_type) RETURN c.entity_id"},
        )
        with pytest.raises(SearchExecutionError, match="[Uu]nknown"):
            execute_search(search, inputs={})


# ---------------------------------------------------------------------------
# TestSearchModelGryphon — Search.validate() gryphon branch
# ---------------------------------------------------------------------------


class TestSearchModelGryphon:
    def test_valid_gryphon_search_validates_ok(self):
        s = Search(
            name="Test",
            search_type="gryphon",
            root="node",
            definition={"query": HUB_SPOKE_QUERY},
        )
        # Should not raise.
        s.validate()

    def test_string_query_validates_ok(self):
        s = Search(
            name="Test",
            search_type="gryphon",
            root="node",
            definition={"query": HUB_SPOKE_QUERY_STR},
        )
        s.validate()

    def test_missing_query_key_raises(self):
        s = Search(
            name="Test",
            search_type="gryphon",
            root="node",
            definition={},
        )
        with pytest.raises(ValidationError) as exc_info:
            s.validate()
        assert "query" in str(exc_info.value)

    def test_invalid_query_syntax_raises(self):
        s = Search(
            name="Test",
            search_type="gryphon",
            root="node",
            definition={"query": "MATCH ("},
        )
        with pytest.raises(ValidationError) as exc_info:
            s.validate()
        assert "parse" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# TestSearchServiceGryphon — execute_search dispatch
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True, databases=["default", "search_readonly"])
class TestSearchServiceGryphon:
    def test_gryphon_dispatch_returns_canonical_envelope(self):
        """req-grid-traversal-exec-pipeline-4: results normalized into canonical envelope."""
        import uuid

        from tap_grid.caller_context import CallerContext, set_caller_context
        from tap_grid.models import Entity

        ctx = CallerContext(user=None, batch_id=str(uuid.uuid4()))
        set_caller_context(ctx)

        hub = Entity.objects.create(entity_type="character", name="Bilbo")

        search = Search(
            search_type="gryphon",
            root="node",
            name="test",
            definition={"query": HUB_SPOKE_QUERY},
        )
        result = execute_search(search, inputs={"entity_id": str(hub.pk)})

        assert "nodes" in result
        assert "edges" in result
        assert "info" in result
        assert "warnings" in result
        assert result["info"]["search_type"] == "gryphon"

    def test_unknown_search_type_raises(self):
        search = Search(
            name="Bad",
            search_type="unknown",
            root="node",
            definition={},
        )
        with pytest.raises(SearchExecutionError, match="Unknown search_type"):
            execute_search(search, inputs={})


# ---------------------------------------------------------------------------
# TestGryphonEdgeTypeScan — edge-type scan execution mode
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True, databases=["default", "search_readonly"])
class TestGryphonEdgeTypeScan:
    def _setup_realm_locations(self):
        """Create realm→location CONTAINS edges for testing."""
        import uuid

        from tap_grid.caller_context import CallerContext, set_caller_context
        from tap_grid.models import Edge, Entity

        ctx = CallerContext(user=None, batch_id=str(uuid.uuid4()))
        set_caller_context(ctx)

        realm = Entity.objects.create(entity_type="realm", name="Middle-earth")
        mordor = Entity.objects.create(entity_type="location", name="Mordor")
        gondor = Entity.objects.create(entity_type="location", name="Gondor")
        frodo = Entity.objects.create(entity_type="character", name="Frodo")

        Edge.objects.create(
            entity=Entity.objects.create(entity_type="edge"),
            from_entity=realm,
            to_entity=mordor,
            edge_type="CONTAINS",
        )
        Edge.objects.create(
            entity=Entity.objects.create(entity_type="edge"),
            from_entity=realm,
            to_entity=gondor,
            edge_type="CONTAINS",
        )
        # A non-matching edge type to verify filtering.
        Edge.objects.create(
            entity=Entity.objects.create(entity_type="edge"),
            from_entity=frodo,
            to_entity=mordor,
            edge_type="LOCATED_IN",
        )
        return realm, mordor, gondor, frodo

    def test_edge_type_scan_returns_matching_edges(self):
        """Edge-type scan returns all edges of the given type with correct endpoints."""
        realm, mordor, gondor, _frodo = self._setup_realm_locations()

        search = Search(
            search_type="gryphon",
            root="node",
            name="test",
            definition={"query": "MATCH (r:realm)-[e:CONTAINS]->(l:location)"},
        )
        result = execute_search(search, inputs={})

        node_ids = {n["entity"]["entity_id"] for n in result["nodes"]}
        assert str(realm.pk) in node_ids
        assert str(mordor.pk) in node_ids
        assert str(gondor.pk) in node_ids
        assert len(result["edges"]) == 2

    def test_edge_type_scan_filters_by_endpoint_type(self):
        """Only edges with matching endpoint types are returned."""
        _realm, _mordor, _gondor, frodo = self._setup_realm_locations()

        search = Search(
            search_type="gryphon",
            root="node",
            name="test",
            definition={"query": "MATCH (r:realm)-[e:CONTAINS]->(l:location)"},
        )
        result = execute_search(search, inputs={})

        node_ids = {n["entity"]["entity_id"] for n in result["nodes"]}
        # Frodo is not a realm or location endpoint of CONTAINS.
        assert str(frodo.pk) not in node_ids

    def test_edge_type_scan_inbound_direction(self):
        """Inbound edge-type scan reverses endpoint label mapping."""
        realm, mordor, gondor, _frodo = self._setup_realm_locations()

        # Inbound: left_node matches to_entity, right_node matches from_entity.
        search = Search(
            search_type="gryphon",
            root="node",
            name="test",
            definition={"query": "MATCH (l:location)<-[e:CONTAINS]-(r:realm)"},
        )
        result = execute_search(search, inputs={})

        node_ids = {n["entity"]["entity_id"] for n in result["nodes"]}
        assert str(realm.pk) in node_ids
        assert str(mordor.pk) in node_ids
        assert str(gondor.pk) in node_ids
        assert len(result["edges"]) == 2

    def test_edge_type_scan_requires_typed_edge(self):
        """Edge-type scan without a typed edge raises SearchExecutionError."""
        search = Search(
            search_type="gryphon",
            root="node",
            name="test",
            definition={"query": "MATCH (a:realm)-[e]->(b:location)"},
        )
        with pytest.raises(SearchExecutionError, match="typed edge"):
            execute_search(search, inputs={})


# ---------------------------------------------------------------------------
# TestGryphonUnion — multiple MATCH clauses with UNION merge
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True, databases=["default", "search_readonly"])
class TestGryphonUnion:
    def _setup_graph(self):
        """Create a small graph with realm, locations, characters, and artifacts."""
        import uuid

        from tap_grid.caller_context import CallerContext, set_caller_context
        from tap_grid.models import Edge, Entity

        ctx = CallerContext(user=None, batch_id=str(uuid.uuid4()))
        set_caller_context(ctx)

        realm = Entity.objects.create(entity_type="realm", name="Middle-earth")
        mordor = Entity.objects.create(entity_type="location", name="Mordor")
        frodo = Entity.objects.create(entity_type="character", name="Frodo")
        ring = Entity.objects.create(entity_type="artifact", name="The One Ring")

        Edge.objects.create(
            entity=Entity.objects.create(entity_type="edge"),
            from_entity=realm,
            to_entity=mordor,
            edge_type="CONTAINS",
        )
        Edge.objects.create(
            entity=Entity.objects.create(entity_type="edge"),
            from_entity=frodo,
            to_entity=mordor,
            edge_type="LOCATED_IN",
        )
        Edge.objects.create(
            entity=Entity.objects.create(entity_type="edge"),
            from_entity=frodo,
            to_entity=ring,
            edge_type="WIELDS",
        )
        return realm, mordor, frodo, ring

    def test_two_match_clauses_merged(self):
        """Two MATCH clauses return merged, deduplicated results."""
        realm, mordor, frodo, ring = self._setup_graph()

        query = [
            "MATCH (r:realm)-[e1:CONTAINS]->(l:location)",
            "MATCH (c:character)-[e2:WIELDS]->(a:artifact)",
        ]
        search = Search(
            search_type="gryphon",
            root="node",
            name="test",
            definition={"query": query},
        )
        result = execute_search(search, inputs={})

        node_ids = {n["entity"]["entity_id"] for n in result["nodes"]}
        assert str(realm.pk) in node_ids
        assert str(mordor.pk) in node_ids
        assert str(frodo.pk) in node_ids
        assert str(ring.pk) in node_ids
        assert len(result["edges"]) == 2

    def test_shared_nodes_deduplicated(self):
        """Nodes appearing in multiple clause results are not duplicated."""
        realm, mordor, frodo, ring = self._setup_graph()

        # Both clauses will return Mordor (as location in CONTAINS and as target in LOCATED_IN).
        query = [
            "MATCH (r:realm)-[e1:CONTAINS]->(l:location)",
            "MATCH (c:character)-[e2:LOCATED_IN]->(l2:location)",
        ]
        search = Search(
            search_type="gryphon",
            root="node",
            name="test",
            definition={"query": query},
        )
        result = execute_search(search, inputs={})

        node_ids = [n["entity"]["entity_id"] for n in result["nodes"]]
        # Mordor should appear exactly once despite being in both results.
        assert node_ids.count(str(mordor.pk)) == 1

    def test_four_clause_saga_shape(self):
        """Full four-clause query shape matching the saga demo pattern."""
        realm, mordor, frodo, ring = self._setup_graph()

        query = [
            "MATCH (r:realm)-[e1:CONTAINS]->(l:location)",
            "MATCH (l2:location)-[e2:CONTAINS]->(l3:location)",
            "MATCH (c:character)-[e3:LOCATED_IN]->(loc:location)",
            "MATCH (c2:character)-[e4:WIELDS]->(a:artifact)",
        ]
        search = Search(
            search_type="gryphon",
            root="node",
            name="test",
            definition={"query": query},
        )
        result = execute_search(search, inputs={})

        node_ids = {n["entity"]["entity_id"] for n in result["nodes"]}
        # All four entity types should be represented.
        assert str(realm.pk) in node_ids
        assert str(mordor.pk) in node_ids
        assert str(frodo.pk) in node_ids
        assert str(ring.pk) in node_ids


# ---------------------------------------------------------------------------
# TestGryphonV2Extensions — multi-hop-aggregation spec coverage
#   - NOT EXISTS grammar and correlation
#   - COUNT aggregation + implicit GROUP BY
#   - Edge pattern without a variable: -[:TYPE]-> (regression)
#   - rows envelope field
# ---------------------------------------------------------------------------


class TestGryphonV2ParserExtensions:
    """Parser coverage for the multi-hop-aggregation extension."""

    def test_edge_pattern_without_variable_parses_as_edge_type(self):
        """-[:TYPE]-> (no variable) must bind edge_type, not variable."""
        ast = parse_gryphon("MATCH (a)-[:CONTAINS]->(b)")
        edge = ast.match_clauses[0].patterns[0].edges[0]
        assert edge.variable is None
        assert edge.edge_type == "CONTAINS"
        assert edge.direction == "out"

    def test_count_aggregate_in_return(self):
        """COUNT(var) AS alias produces an AggregateReturnItem."""
        from tap_grid.gryphon.ast_nodes import AggregateReturnItem

        ast = parse_gryphon(
            "MATCH (a)-[:R]->(b) RETURN a.entity_id AS id, COUNT(b) AS n"
        )
        items = ast.return_clause.items
        assert items is not None and len(items) == 2
        assert any(isinstance(i, AggregateReturnItem) for i in items)
        agg = next(i for i in items if isinstance(i, AggregateReturnItem))
        assert agg.aggregate.function == "count"
        assert agg.aggregate.argument.variable == "b"
        assert agg.alias == "n"

    def test_not_exists_clause_parses(self):
        """NOT EXISTS { MATCH ... WHERE ... } is a recognized top-level clause."""
        q = (
            "MATCH (a)-[:R1]->(b) "
            "NOT EXISTS { MATCH (c)-[:R2]->(b) WHERE c.entity_type = \"character\" } "
            "RETURN a.entity_id, COUNT(b) AS n"
        )
        ast = parse_gryphon(q)
        assert len(ast.not_exists_clauses) == 1
        nec = ast.not_exists_clauses[0]
        assert len(nec.match_clause.patterns) == 1
        assert nec.where_clause is not None


@pytest.mark.django_db(transaction=True, databases=["default", "search_readonly"])
class TestGryphonV2Executor:
    """Executor coverage for COUNT + GROUP BY, NOT EXISTS, and the rows envelope."""

    def _setup_wielders(self):
        """Three characters wielding artifacts (some multi-wielders), for GROUP BY tests."""
        import uuid

        from tap_grid.caller_context import CallerContext, set_caller_context
        from tap_grid.models import Edge, Entity

        ctx = CallerContext(user=None, batch_id=str(uuid.uuid4()))
        set_caller_context(ctx)

        frodo = Entity.objects.create(entity_type="character", name="Frodo")
        sam = Entity.objects.create(entity_type="character", name="Sam")
        aragorn = Entity.objects.create(entity_type="character", name="Aragorn")

        ring = Entity.objects.create(entity_type="artifact", name="One Ring")
        sting = Entity.objects.create(entity_type="artifact", name="Sting")
        anduril = Entity.objects.create(entity_type="artifact", name="Anduril")

        for src, tgt in [(frodo, ring), (frodo, sting), (sam, sting), (aragorn, anduril)]:
            Edge.objects.create(
                entity=Entity.objects.create(entity_type="edge"),
                from_entity=src,
                to_entity=tgt,
                edge_type="WIELDS",
            )
        return frodo, sam, aragorn, ring, sting, anduril

    def test_count_with_group_by_produces_rows(self):
        """COUNT(artifact) grouped by wielder produces one row per wielder with correct count."""
        frodo, sam, aragorn, *_ = self._setup_wielders()

        search = Search(
            search_type="gryphon",
            root="node",
            name="wielder-counts",
            definition={
                "query": (
                    "MATCH (c:character)-[:WIELDS]->(a:artifact) "
                    "RETURN c.entity_id AS wielder, COUNT(a) AS count"
                )
            },
        )
        result = execute_search(search, inputs={})
        assert "rows" in result
        rows = {r["wielder"]: r["count"] for r in result["rows"]}
        assert rows[str(frodo.pk)] == 2  # ring + sting
        assert rows[str(sam.pk)] == 1  # sting
        assert rows[str(aragorn.pk)] == 1  # anduril

    def test_not_exists_excludes_correlated_rows(self):
        """NOT EXISTS filters out outer rows whose shared var matches an inner pattern."""
        frodo, sam, aragorn, ring, sting, anduril = self._setup_wielders()

        # Find characters wielding artifacts that Sam does NOT also wield.
        # Sam wields Sting. So expected: Frodo (wields ring AND sting; sting excluded → only ring)
        # and Aragorn (wields anduril, Sam doesn't). Sam himself is not returned because of
        # the anti-join — but actually the anti-join filters on shared artifact not on character.
        # Redo: the query asks "for each outer (c, a) where c wields a, exclude if Sam also
        # wields a." So Frodo-Ring stays (Sam doesn't wield ring), Frodo-Sting excluded,
        # Sam-Sting excluded, Aragorn-Anduril stays.
        # Grouped by c: Frodo=1 (ring), Aragorn=1 (anduril). Sam has no surviving artifacts.
        search = Search(
            search_type="gryphon",
            root="node",
            name="not-wielded-by-sam",
            definition={
                "query": (
                    "MATCH (c:character)-[:WIELDS]->(a:artifact) "
                    "NOT EXISTS { "
                    "  MATCH (sam:character)-[:WIELDS]->(a) "
                    "  WHERE sam.name = \"Sam\" "
                    "} "
                    "RETURN c.entity_id AS wielder, COUNT(a) AS count"
                )
            },
        )
        result = execute_search(search, inputs={})
        rows = {r["wielder"]: r["count"] for r in result["rows"]}
        assert rows.get(str(frodo.pk)) == 1
        assert rows.get(str(aragorn.pk)) == 1
        # Sam is excluded entirely — his only wield (Sting) was anti-joined out.
        assert str(sam.pk) not in rows

    def test_envelope_contains_rows_key(self):
        """Aggregating queries surface the `rows` key in the canonical envelope."""
        self._setup_wielders()

        search = Search(
            search_type="gryphon",
            root="node",
            name="aggregate",
            definition={
                "query": (
                    "MATCH (c:character)-[:WIELDS]->(a:artifact) "
                    "RETURN c.entity_id AS wielder, COUNT(a) AS count"
                )
            },
        )
        result = execute_search(search, inputs={})
        assert "rows" in result
        assert isinstance(result["rows"], list)
        assert all("wielder" in r and "count" in r for r in result["rows"])

    # ------------------------------------------------------------------
    # Multi-hop executor coverage — req-grid-gryphon-multihop-{1,2,3}
    # ------------------------------------------------------------------

    def _setup_three_layer_chain(self):
        """Characters own realms which contain locations — a 3-layer chain."""
        import uuid

        from tap_grid.caller_context import CallerContext, set_caller_context
        from tap_grid.models import Edge, Entity

        ctx = CallerContext(user=None, batch_id=str(uuid.uuid4()))
        set_caller_context(ctx)

        frodo = Entity.objects.create(entity_type="character", name="Frodo")
        aragorn = Entity.objects.create(entity_type="character", name="Aragorn")

        shire = Entity.objects.create(entity_type="realm", name="Shire")
        gondor = Entity.objects.create(entity_type="realm", name="Gondor")
        arnor = Entity.objects.create(entity_type="realm", name="Arnor")

        hobbiton = Entity.objects.create(entity_type="location", name="Hobbiton")
        buckland = Entity.objects.create(entity_type="location", name="Buckland")
        minas_tirith = Entity.objects.create(entity_type="location", name="Minas Tirith")
        annuminas = Entity.objects.create(entity_type="location", name="Annuminas")

        # Character OWNS realm.
        for src, tgt in [(frodo, shire), (aragorn, gondor), (aragorn, arnor)]:
            Edge.objects.create(
                entity=Entity.objects.create(entity_type="edge"),
                from_entity=src, to_entity=tgt, edge_type="OWNS",
            )
        # Realm CONTAINS location.
        for src, tgt in [
            (shire, hobbiton), (shire, buckland),
            (gondor, minas_tirith),
            (arnor, annuminas),
        ]:
            Edge.objects.create(
                entity=Entity.objects.create(entity_type="edge"),
                from_entity=src, to_entity=tgt, edge_type="CONTAINS",
            )
        return {
            "frodo": frodo, "aragorn": aragorn,
            "shire": shire, "gondor": gondor, "arnor": arnor,
            "hobbiton": hobbiton, "buckland": buckland,
            "minas_tirith": minas_tirith, "annuminas": annuminas,
        }

    def test_two_hop_chain_counts_leaf_per_root(self):
        """req-grid-gryphon-multihop-1: 2-hop chain with COUNT groups correctly."""
        e = self._setup_three_layer_chain()

        # For each character, count locations reachable via owned realms.
        search = Search(
            search_type="gryphon",
            root="node",
            name="two-hop",
            definition={
                "query": (
                    "MATCH (c:character)-[:OWNS]->(r:realm)-[:CONTAINS]->(l:location) "
                    "RETURN c.entity_id AS character, COUNT(l) AS locations"
                )
            },
        )
        result = execute_search(search, inputs={})
        rows = {r["character"]: r["locations"] for r in result["rows"]}
        # Frodo owns Shire (2 locations: Hobbiton, Buckland).
        # Aragorn owns Gondor (1) + Arnor (1) = 2 locations total.
        assert rows[str(e["frodo"].pk)] == 2
        assert rows[str(e["aragorn"].pk)] == 2

    def test_two_hop_chain_with_no_anchor_warning(self):
        """req-grid-gryphon-multihop: no WHERE anchor on a multi-hop emits a warning."""
        self._setup_three_layer_chain()

        search = Search(
            search_type="gryphon",
            root="node",
            name="no-anchor",
            definition={
                "query": (
                    "MATCH (c:character)-[:OWNS]->(r:realm)-[:CONTAINS]->(l:location) "
                    "RETURN c.entity_id AS id, COUNT(l) AS n"
                )
            },
        )
        result = execute_search(search, inputs={})
        # Warning attached by the advanced executor (service layer promotes via envelope).
        assert "multi_hop_no_anchor" in result.get("warnings", {})

    def test_two_hop_intermediate_label_filters(self):
        """req-grid-gryphon-multihop-3: intermediate label acts as a type filter."""
        e = self._setup_three_layer_chain()

        # Same chain but label the intermediate — results should be identical because
        # every realm-typed entity is in fact a realm. Exercises the label pass-through.
        search = Search(
            search_type="gryphon",
            root="node",
            name="labeled-middle",
            definition={
                "query": (
                    "MATCH (c:character)-[:OWNS]->(r:realm)-[:CONTAINS]->(l:location) "
                    "WHERE c.name = \"Frodo\" "
                    "RETURN c.entity_id AS character, COUNT(l) AS locations"
                )
            },
        )
        result = execute_search(search, inputs={})
        rows = {r["character"]: r["locations"] for r in result["rows"]}
        assert rows[str(e["frodo"].pk)] == 2
        assert str(e["aragorn"].pk) not in rows

    def test_two_hop_with_mixed_directions(self):
        """req-grid-gryphon-multihop-2: each hop's direction is honored independently.

        Pattern: (l:location)<-[:CONTAINS]-(r:realm)<-[:OWNS]-(c:character)
        Reads the same edges backwards — locations → realms → owning characters.
        """
        e = self._setup_three_layer_chain()

        search = Search(
            search_type="gryphon",
            root="node",
            name="mixed-dir",
            definition={
                "query": (
                    "MATCH (l:location)<-[:CONTAINS]-(r:realm)<-[:OWNS]-(c:character) "
                    "RETURN c.entity_id AS character, COUNT(l) AS locations"
                )
            },
        )
        result = execute_search(search, inputs={})
        rows = {r["character"]: r["locations"] for r in result["rows"]}
        assert rows[str(e["frodo"].pk)] == 2
        assert rows[str(e["aragorn"].pk)] == 2

    def test_two_hop_outer_with_not_exists_correlation(self):
        """req-grid-gryphon-not-exists: NOT EXISTS correlated on a variable from a 2-hop outer."""
        import uuid

        from tap_grid.caller_context import CallerContext, set_caller_context
        from tap_grid.models import Edge, Entity

        e = self._setup_three_layer_chain()

        # Flag one location as "restricted" via an edge from a separate guard entity.
        ctx = CallerContext(user=None, batch_id=str(uuid.uuid4()))
        set_caller_context(ctx)
        guard = Entity.objects.create(entity_type="character", name="Guard")
        Edge.objects.create(
            entity=Entity.objects.create(entity_type="edge"),
            from_entity=guard, to_entity=e["minas_tirith"], edge_type="RESTRICTS",
        )

        # Count per character the locations they reach via a realm — excluding any
        # location restricted by some guard character.
        search = Search(
            search_type="gryphon",
            root="node",
            name="two-hop-not-exists",
            definition={
                "query": (
                    "MATCH (c:character)-[:OWNS]->(r:realm)-[:CONTAINS]->(l:location) "
                    "NOT EXISTS { MATCH (g:character)-[:RESTRICTS]->(l) } "
                    "RETURN c.entity_id AS character, COUNT(l) AS locations"
                )
            },
        )
        result = execute_search(search, inputs={})
        rows = {r["character"]: r["locations"] for r in result["rows"]}
        # Frodo: 2 (Shire contains Hobbiton, Buckland) — neither restricted.
        assert rows[str(e["frodo"].pk)] == 2
        # Aragorn: would be 2 (Minas Tirith, Annuminas) but Minas Tirith is restricted → 1.
        assert rows[str(e["aragorn"].pk)] == 1

    def test_multi_hop_inner_not_exists(self):
        """req-grid-gryphon-not-exists: NOT EXISTS inner pattern itself is multi-hop."""
        import uuid

        from tap_grid.caller_context import CallerContext, set_caller_context
        from tap_grid.models import Edge, Entity

        e = self._setup_three_layer_chain()

        # Set up a 2-hop restriction chain: one guard → restriction → minas tirith.
        ctx = CallerContext(user=None, batch_id=str(uuid.uuid4()))
        set_caller_context(ctx)
        high_guard = Entity.objects.create(entity_type="character", name="HighGuard")
        restriction = Entity.objects.create(entity_type="realm", name="Restriction Seal")
        Edge.objects.create(
            entity=Entity.objects.create(entity_type="edge"),
            from_entity=high_guard, to_entity=restriction, edge_type="ISSUES",
        )
        Edge.objects.create(
            entity=Entity.objects.create(entity_type="edge"),
            from_entity=restriction, to_entity=e["minas_tirith"], edge_type="SEALS",
        )

        # Outer single-hop: character owns realm. Inner NOT EXISTS is a 2-hop chain.
        # Want: count characters whose owned realm contains NO location that is
        # sealed via a 2-hop restriction chain.
        search = Search(
            search_type="gryphon",
            root="node",
            name="multi-hop-inner-not-exists",
            definition={
                "query": (
                    "MATCH (c:character)-[:OWNS]->(r:realm)-[:CONTAINS]->(l:location) "
                    "NOT EXISTS { "
                    "  MATCH (g:character)-[:ISSUES]->(sr:realm)-[:SEALS]->(l) "
                    "} "
                    "RETURN c.entity_id AS character, COUNT(l) AS locations"
                )
            },
        )
        result = execute_search(search, inputs={})
        rows = {r["character"]: r["locations"] for r in result["rows"]}
        # Frodo: 2 locations, none sealed → 2
        assert rows[str(e["frodo"].pk)] == 2
        # Aragorn: 2 locations, Minas Tirith sealed → 1
        assert rows[str(e["aragorn"].pk)] == 1

    def test_variable_length_edge_rejected(self):
        """req-grid-gryphon-multihop-4: variable-length edges parse but executor rejects."""
        self._setup_three_layer_chain()

        search = Search(
            search_type="gryphon",
            root="node",
            name="var-length",
            definition={
                "query": (
                    "MATCH (c:character)-[:OWNS*1..3]->(r:realm) "
                    "RETURN c.entity_id AS id, COUNT(r) AS n"
                )
            },
        )
        with pytest.raises(SearchExecutionError, match="[Vv]ariable-length"):
            execute_search(search, inputs={})

    def test_two_hop_no_return_graph_envelope(self):
        """req-grid-gryphon-multihop-envelope-1: omitted RETURN returns all nodes and edges."""
        e = self._setup_three_layer_chain()

        search = Search(
            search_type="gryphon",
            root="node",
            name="envelope-all",
            definition={
                "query": (
                    "MATCH (c:character)-[e1:OWNS]->(r:realm)-[e2:CONTAINS]->(l:location)"
                )
            },
        )
        result = execute_search(search, inputs={})

        node_ids = {n["entity"]["entity_id"] for n in result["nodes"]}
        # All 9 entities in the chain should be present.
        for name in ("frodo", "aragorn", "shire", "gondor", "arnor",
                      "hobbiton", "buckland", "minas_tirith", "annuminas"):
            assert str(e[name].pk) in node_ids, f"{name} missing from nodes"

        # Edges: 3 OWNS + 4 CONTAINS = 7
        assert len(result["edges"]) == 7
        edge_types = {edg["edge"]["edge_type"] for edg in result["edges"]}
        assert edge_types == {"OWNS", "CONTAINS"}

        # rows should be empty for graph envelope
        assert result.get("rows", []) == []

    def test_two_hop_bare_variable_return_graph_envelope(self):
        """req-grid-gryphon-multihop-envelope-2: RETURN with bare variables returns named entities."""
        e = self._setup_three_layer_chain()

        # Only request the character and location — skip the intermediate realm.
        search = Search(
            search_type="gryphon",
            root="node",
            name="envelope-selected",
            definition={
                "query": (
                    "MATCH (c:character)-[e1:OWNS]->(r:realm)-[e2:CONTAINS]->(l:location) "
                    "RETURN c, l"
                )
            },
        )
        result = execute_search(search, inputs={})

        node_ids = {n["entity"]["entity_id"] for n in result["nodes"]}
        # Characters and locations should be present.
        assert str(e["frodo"].pk) in node_ids
        assert str(e["aragorn"].pk) in node_ids
        assert str(e["hobbiton"].pk) in node_ids
        # Realms should NOT be in nodes (not requested).
        assert str(e["shire"].pk) not in node_ids

        # Edges should still be returned (connecting edges included automatically).
        assert len(result["edges"]) == 7

    def test_two_hop_graph_envelope_with_where_anchor(self):
        """req-grid-gryphon-multihop-envelope: WHERE anchor scopes the subgraph."""
        e = self._setup_three_layer_chain()

        search = Search(
            search_type="gryphon",
            root="node",
            name="envelope-anchored",
            definition={
                "query": (
                    "MATCH (c:character)-[e1:OWNS]->(r:realm)-[e2:CONTAINS]->(l:location) "
                    "WHERE c.name = \"Frodo\""
                )
            },
        )
        result = execute_search(search, inputs={})

        node_ids = {n["entity"]["entity_id"] for n in result["nodes"]}
        # Only Frodo's chain: Frodo, Shire, Hobbiton, Buckland
        assert str(e["frodo"].pk) in node_ids
        assert str(e["shire"].pk) in node_ids
        assert str(e["hobbiton"].pk) in node_ids
        assert str(e["buckland"].pk) in node_ids
        # Aragorn's chain should not appear.
        assert str(e["aragorn"].pk) not in node_ids
        assert str(e["gondor"].pk) not in node_ids

    def test_two_hop_graph_envelope_deduplication(self):
        """Nodes appearing at multiple positions in the chain are deduplicated."""
        e = self._setup_three_layer_chain()

        search = Search(
            search_type="gryphon",
            root="node",
            name="envelope-dedup",
            definition={
                "query": (
                    "MATCH (c:character)-[e1:OWNS]->(r:realm)-[e2:CONTAINS]->(l:location)"
                )
            },
        )
        result = execute_search(search, inputs={})

        entity_ids = [n["entity"]["entity_id"] for n in result["nodes"]]
        # No duplicates.
        assert len(entity_ids) == len(set(entity_ids))
