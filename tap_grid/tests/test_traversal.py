"""Tests for the TAP traversal language — parser, executor, Search model, and search service.

Covers spec-grid-traversal-language.md and spec-grid-traversal-execution.md.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from tap_grid.exceptions import SearchExecutionError
from tap_grid.models import Search
from tap_grid.search_service import execute_search
from tap_grid.traversal.ast_nodes import (
    AndPred,
    Comparison,
    DotStep,
    EdgePattern,
    FieldPath,
    KeyStep,
    MatchClause,
    NodePattern,
    NotPred,
    OrPred,
    ParamRef,
    PathPattern,
    ReturnClause,
    ReturnItem,
    TraversalAST,
    WhereClause,
    WildcardStep,
)
from tap_grid.traversal.parser import TraversalParseError, parse_traversal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HUB_SPOKE_QUERY = [
    "MATCH (hub)-[e]-(neighbor)",
    "WHERE hub.entity_id = $entity_id",
    "RETURN hub, e, neighbor",
]

HUB_SPOKE_QUERY_STR = "MATCH (hub)-[e]-(neighbor) WHERE hub.entity_id = $entity_id RETURN hub, e, neighbor"


def _traversal_search(**kwargs):
    defaults = {
        "name": "Hub and Spoke",
        "search_type": "traversal",
        "root": "node",
        "definition": {"query": HUB_SPOKE_QUERY},
    }
    defaults.update(kwargs)
    return Search(**defaults)


# ---------------------------------------------------------------------------
# TestTraversalParser — req-grid-traversal-lang-shape / storage / patterns / filters / combinators / params / returns
# ---------------------------------------------------------------------------


class TestTraversalParser:
    def test_hub_spoke_list_form_parses(self):
        ast = parse_traversal(HUB_SPOKE_QUERY)
        assert isinstance(ast, TraversalAST)
        assert len(ast.match_clauses) == 1

    def test_hub_spoke_string_form_parses(self):
        ast = parse_traversal(HUB_SPOKE_QUERY_STR)
        assert isinstance(ast, TraversalAST)
        assert len(ast.match_clauses) == 1

    def test_list_and_string_forms_equivalent(self):
        """req-grid-traversal-lang-storage-3: both forms normalize to the same AST."""
        ast_list = parse_traversal(HUB_SPOKE_QUERY)
        ast_str = parse_traversal(HUB_SPOKE_QUERY_STR)
        assert ast_list == ast_str

    def test_match_clause_structure(self):
        """req-grid-traversal-lang-patterns: node/edge variables and direction."""
        ast = parse_traversal(HUB_SPOKE_QUERY)
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
        ast = parse_traversal("MATCH (a)-[e]->(b) WHERE a.entity_id = $id RETURN a, e, b")
        edge = ast.match_clauses[0].patterns[0].edges[0]
        assert edge.direction == "out"

    def test_inbound_edge_direction(self):
        """req-grid-traversal-lang-patterns-3: directed inbound."""
        ast = parse_traversal("MATCH (a)<-[e]-(b) WHERE a.entity_id = $id RETURN a, e, b")
        edge = ast.match_clauses[0].patterns[0].edges[0]
        assert edge.direction == "in"

    def test_typed_edge(self):
        """req-grid-traversal-lang-patterns-2: typed edge."""
        ast = parse_traversal("MATCH (a)-[e:ON_HOST]-(b) WHERE a.entity_id = $id RETURN a")
        edge = ast.match_clauses[0].patterns[0].edges[0]
        assert edge.edge_type == "ON_HOST"

    def test_node_label(self):
        """req-grid-traversal-lang-patterns-1: node label."""
        ast = parse_traversal("MATCH (h:host)-[e]-(n) WHERE h.entity_id = $id RETURN h")
        node = ast.match_clauses[0].patterns[0].nodes[0]
        assert node.label == "host"
        assert node.variable == "h"

    def test_path_variable(self):
        """req-grid-traversal-lang-patterns-4: path variable binding."""
        ast = parse_traversal("MATCH p = (a)-[e]-(b) WHERE a.entity_id = $id RETURN p")
        assert ast.match_clauses[0].path_var == "p"

    def test_where_clause_parsed(self):
        ast = parse_traversal(HUB_SPOKE_QUERY)
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
        ast = parse_traversal(
            'MATCH (n)-[e]-(m) WHERE n.entity_id = $id AND n.name = "web01" RETURN n'
        )
        pred = ast.where_clause.predicate
        assert isinstance(pred, AndPred)

    def test_or_predicate(self):
        """req-grid-traversal-lang-combinators-2: OR."""
        ast = parse_traversal(
            'MATCH (n)-[e]-(m) WHERE n.entity_id = $id OR n.name = "web01" RETURN n'
        )
        pred = ast.where_clause.predicate
        assert isinstance(pred, OrPred)

    def test_not_predicate(self):
        """req-grid-traversal-lang-combinators-3: NOT."""
        ast = parse_traversal(
            'MATCH (n)-[e]-(m) WHERE NOT n.name = "excluded" RETURN n'
        )
        pred = ast.where_clause.predicate
        assert isinstance(pred, NotPred)

    def test_bracket_key_access(self):
        """req-grid-traversal-lang-filters-4: keyed JSON access."""
        ast = parse_traversal(
            'MATCH (n)-[e]-(m) WHERE n.dimensions["tap.graph"] = "web" RETURN n'
        )
        pred = ast.where_clause.predicate
        assert isinstance(pred, Comparison)
        steps = pred.field_path.steps
        assert isinstance(steps[0], DotStep) and steps[0].name == "dimensions"
        assert isinstance(steps[1], KeyStep) and steps[1].key == "tap.graph"

    def test_array_wildcard_access(self):
        """req-grid-traversal-lang-filters-6: array wildcard [*]."""
        ast = parse_traversal(
            "MATCH (n)-[e]-(m) WHERE n.properties.aliases[*].name = $alias RETURN n"
        )
        pred = ast.where_clause.predicate
        steps = pred.field_path.steps
        assert any(isinstance(s, WildcardStep) for s in steps)

    def test_return_clause_items(self):
        """req-grid-traversal-lang-returns-3: variable returns."""
        ast = parse_traversal(HUB_SPOKE_QUERY)
        ret = ast.return_clause
        assert ret.items is not None
        assert len(ret.items) == 3
        variables = [item.path.variable for item in ret.items]
        assert "hub" in variables
        assert "e" in variables
        assert "neighbor" in variables

    def test_return_alias(self):
        """req-grid-traversal-lang-returns-5: AS alias."""
        ast = parse_traversal(
            "MATCH (h)-[e]-(n) WHERE h.entity_id = $id RETURN h.name AS accepted_name"
        )
        ret = ast.return_clause
        assert ret.items is not None
        assert ret.items[0].alias == "accepted_name"

    def test_omitted_return_is_none(self):
        """req-grid-traversal-lang-returns-1: omitted RETURN → items=None → graph envelope."""
        ast = parse_traversal("MATCH (hub)-[e]-(neighbor) WHERE hub.entity_id = $entity_id")
        assert ast.return_clause.items is None

    def test_required_params_extracted(self):
        ast = parse_traversal(HUB_SPOKE_QUERY)
        assert ast.required_params() == frozenset({"entity_id"})

    def test_invalid_syntax_raises_parse_error(self):
        """req-grid-traversal-exec-scope.sec-3: unsupported syntax rejected."""
        with pytest.raises(TraversalParseError):
            parse_traversal("MATCH (")

    def test_empty_string_raises_parse_error(self):
        with pytest.raises(TraversalParseError):
            parse_traversal("")


# ---------------------------------------------------------------------------
# TestTraversalExecutor — req-grid-traversal-exec-pipeline
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True, databases=["default", "search_readonly"])
class TestTraversalExecutor:
    def test_hub_spoke_returns_hub_and_neighbors(self):
        """Hub-and-spoke traversal returns hub + one-hop neighbors and edges."""
        from tap_grid.caller_context import CallerContext, set_caller_context
        from tap_grid.models import Edge, Entity
        import uuid

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
            search_type="traversal",
            root="node",
            name="test",
            definition={"query": HUB_SPOKE_QUERY},
        )
        result = execute_search(search, inputs={"entity_id": str(hub.pk)})

        node_ids = {n["entity_id"] for n in result["nodes"]}
        assert str(hub.pk) in node_ids
        assert str(neighbor.pk) in node_ids
        assert len(result["edges"]) == 1

    def test_outbound_only_direction(self):
        """Outbound-only pattern excludes inbound-only neighbors."""
        from tap_grid.caller_context import CallerContext, set_caller_context
        from tap_grid.models import Edge, Entity
        import uuid

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
            search_type="traversal",
            root="node",
            name="test",
            definition={
                "query": "MATCH (hub)-[e]->(neighbor) WHERE hub.entity_id = $entity_id RETURN hub, e, neighbor"
            },
        )
        result = execute_search(search, inputs={"entity_id": str(hub.pk)})
        node_ids = {n["entity_id"] for n in result["nodes"]}
        assert str(outbound_neighbor.pk) in node_ids
        assert str(inbound_neighbor.pk) not in node_ids

    def test_hub_not_found_returns_empty(self):
        """Missing hub entity returns empty nodes/edges with a warning."""
        import uuid

        search = Search(
            search_type="traversal",
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
            search_type="traversal",
            root="node",
            name="test",
            definition={"query": HUB_SPOKE_QUERY},
        )
        with pytest.raises(SearchExecutionError, match="entity_id"):
            execute_search(search, inputs={})

    def test_unsupported_multi_hop_raises(self):
        """V1 rejects bounded multi-hop patterns."""
        search = Search(
            search_type="traversal",
            root="node",
            name="test",
            definition={
                "query": "MATCH (a)-[e*1..3]-(b) WHERE a.entity_id = $entity_id RETURN a"
            },
        )
        with pytest.raises(SearchExecutionError, match="[Uu]nsupported"):
            execute_search(search, inputs={"entity_id": "00000000-0000-0000-0000-000000000000"})


# ---------------------------------------------------------------------------
# TestSearchModelTraversal — Search.validate() traversal branch
# ---------------------------------------------------------------------------


class TestSearchModelTraversal:
    def test_valid_traversal_search_validates_ok(self):
        s = Search(
            name="Test",
            search_type="traversal",
            root="node",
            definition={"query": HUB_SPOKE_QUERY},
        )
        # Should not raise.
        s.validate()

    def test_string_query_validates_ok(self):
        s = Search(
            name="Test",
            search_type="traversal",
            root="node",
            definition={"query": HUB_SPOKE_QUERY_STR},
        )
        s.validate()

    def test_missing_query_key_raises(self):
        s = Search(
            name="Test",
            search_type="traversal",
            root="node",
            definition={},
        )
        with pytest.raises(ValidationError) as exc_info:
            s.validate()
        assert "query" in str(exc_info.value)

    def test_invalid_query_syntax_raises(self):
        s = Search(
            name="Test",
            search_type="traversal",
            root="node",
            definition={"query": "MATCH ("},
        )
        with pytest.raises(ValidationError) as exc_info:
            s.validate()
        assert "parse" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# TestSearchServiceTraversal — execute_search dispatch
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True, databases=["default", "search_readonly"])
class TestSearchServiceTraversal:
    def test_traversal_dispatch_returns_canonical_envelope(self):
        """req-grid-traversal-exec-pipeline-4: results normalized into canonical envelope."""
        from tap_grid.caller_context import CallerContext, set_caller_context
        from tap_grid.models import Entity
        import uuid

        ctx = CallerContext(user=None, batch_id=str(uuid.uuid4()))
        set_caller_context(ctx)

        hub = Entity.objects.create(entity_type="character", name="Bilbo")

        search = Search(
            search_type="traversal",
            root="node",
            name="test",
            definition={"query": HUB_SPOKE_QUERY},
        )
        result = execute_search(search, inputs={"entity_id": str(hub.pk)})

        assert "nodes" in result
        assert "edges" in result
        assert "info" in result
        assert "warnings" in result
        assert result["info"]["search_type"] == "traversal"

    def test_unknown_search_type_raises(self):
        search = Search(
            name="Bad",
            search_type="unknown",
            root="node",
            definition={},
        )
        with pytest.raises(SearchExecutionError, match="Unknown search_type"):
            execute_search(search, inputs={})
