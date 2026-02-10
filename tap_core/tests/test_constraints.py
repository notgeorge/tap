"""Tests for edge constraint validation."""

import pytest

from tap_core.constraints import (
    WILDCARD,
    _parse_constraint_list,
    get_constraints,
    register_constraints,
    validate_edge,
)
from tap_core.exceptions import InvalidEdgeError


class TestParseConstraintList:
    """Test _parse_constraint_list function."""

    def test_parses_basic_constraint(self) -> None:
        constraints = [
            {
                "nodes": [{"type": "concept"}],
                "edges": [{"type": "APPLIES_TO"}],
            },
        ]
        result = _parse_constraint_list(constraints)
        assert result == {"APPLIES_TO": {"concept"}}

    def test_parses_multiple_nodes(self) -> None:
        constraints = [
            {
                "nodes": [{"type": "concept"}, {"type": "precept"}],
                "edges": [{"type": "APPLIES_TO"}],
            },
        ]
        result = _parse_constraint_list(constraints)
        assert result == {"APPLIES_TO": {"concept", "precept"}}

    def test_parses_multiple_edges(self) -> None:
        constraints = [
            {
                "nodes": [{"type": "concept"}],
                "edges": [{"type": "APPLIES_TO"}, {"type": "DEPENDS_ON"}],
            },
        ]
        result = _parse_constraint_list(constraints)
        assert result == {
            "APPLIES_TO": {"concept"},
            "DEPENDS_ON": {"concept"},
        }

    def test_parses_wildcard_when_nodes_absent(self) -> None:
        constraints = [
            {
                "edges": [{"type": "REFERENCES"}],
            },
        ]
        result = _parse_constraint_list(constraints)
        assert result["REFERENCES"] is WILDCARD

    def test_merges_nodes_for_same_edge_type(self) -> None:
        constraints = [
            {
                "nodes": [{"type": "concept"}],
                "edges": [{"type": "APPLIES_TO"}],
            },
            {
                "nodes": [{"type": "precept"}],
                "edges": [{"type": "APPLIES_TO"}],
            },
        ]
        result = _parse_constraint_list(constraints)
        assert result == {"APPLIES_TO": {"concept", "precept"}}

    def test_wildcard_takes_precedence(self) -> None:
        constraints = [
            {
                "nodes": [{"type": "concept"}],
                "edges": [{"type": "APPLIES_TO"}],
            },
            {
                # Wildcard for same edge type
                "edges": [{"type": "APPLIES_TO"}],
            },
        ]
        result = _parse_constraint_list(constraints)
        assert result["APPLIES_TO"] is WILDCARD


class TestRegisterConstraints:
    """Test register_constraints and get_constraints."""

    def test_registers_and_retrieves_constraints(self) -> None:
        register_constraints(
            "test_entity",
            outbound=[{"nodes": [{"type": "target"}], "edges": [{"type": "LINKS_TO"}]}],
            inbound=None,
        )
        constraints = get_constraints("test_entity")
        assert constraints is not None
        assert constraints.outbound == {"LINKS_TO": {"target"}}
        assert constraints.inbound is None

    def test_returns_none_for_unregistered(self) -> None:
        assert get_constraints("nonexistent_type") is None


class TestValidateEdge:
    """Test validate_edge function."""

    @pytest.fixture(autouse=True)
    def setup_constraints(self) -> None:
        """Register test constraints."""
        # source_node: can only create VALID_EDGE to target_node
        register_constraints(
            "source_node",
            outbound=[{"nodes": [{"type": "target_node"}], "edges": [{"type": "VALID_EDGE"}]}],
            inbound=None,
        )
        # target_node: can only receive VALID_EDGE from source_node
        register_constraints(
            "target_node",
            outbound=None,
            inbound=[{"nodes": [{"type": "source_node"}], "edges": [{"type": "VALID_EDGE"}]}],
        )
        # blocked_node: cannot create any outbound edges
        register_constraints(
            "blocked_node",
            outbound=[],
            inbound=None,
        )
        # wildcard_node: can create WILD_EDGE to any node type
        register_constraints(
            "wildcard_node",
            outbound=[{"edges": [{"type": "WILD_EDGE"}]}],
            inbound=None,
        )

    def test_valid_edge_passes(self) -> None:
        # Should not raise
        validate_edge("source_node", "target_node", "VALID_EDGE")

    def test_invalid_edge_type_raises(self) -> None:
        with pytest.raises(InvalidEdgeError) as exc_info:
            validate_edge("source_node", "target_node", "INVALID_EDGE")
        assert "cannot create 'INVALID_EDGE' edges" in str(exc_info.value)

    def test_invalid_target_raises(self) -> None:
        with pytest.raises(InvalidEdgeError) as exc_info:
            validate_edge("source_node", "wrong_target", "VALID_EDGE")
        assert "cannot create 'VALID_EDGE' edge to wrong_target" in str(exc_info.value)

    def test_blocked_outbound_raises(self) -> None:
        with pytest.raises(InvalidEdgeError) as exc_info:
            validate_edge("blocked_node", "target_node", "ANY_EDGE")
        assert "cannot create any outbound edges" in str(exc_info.value)

    def test_invalid_inbound_source_raises(self) -> None:
        with pytest.raises(InvalidEdgeError) as exc_info:
            validate_edge("wrong_source", "target_node", "VALID_EDGE")
        assert "cannot receive 'VALID_EDGE' edge from wrong_source" in str(exc_info.value)

    def test_wildcard_allows_any_target(self) -> None:
        # Should not raise for any target
        validate_edge("wildcard_node", "any_target", "WILD_EDGE")
        validate_edge("wildcard_node", "another_target", "WILD_EDGE")

    def test_unregistered_types_pass(self) -> None:
        # No constraints = no restrictions
        validate_edge("unregistered_from", "unregistered_to", "ANY_EDGE")
