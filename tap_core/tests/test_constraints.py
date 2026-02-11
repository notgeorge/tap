"""Tests for edge constraint validation."""

import pytest

from tap_core.constraints import (
    WILDCARD,
    _parse_constraint_list,
    get_constraints,
    get_edge_type_constraints,
    register_constraints,
    register_edge_type_constraints,
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


class TestRegisterEdgeTypeConstraints:
    """Test register_edge_type_constraints and get_edge_type_constraints."""

    def test_registers_basic_constraint(self) -> None:
        register_edge_type_constraints(
            "TEST_EDGE",
            sources=[{"type": "source_type"}],
            targets=[{"type": "target_type"}],
        )
        constraints = get_edge_type_constraints("TEST_EDGE")
        assert constraints is not None
        assert constraints.sources == {"source_type"}
        assert constraints.targets == {"target_type"}

    def test_registers_wildcard_source(self) -> None:
        register_edge_type_constraints(
            "WILD_SOURCE_EDGE",
            sources=None,  # Wildcard
            targets=[{"type": "target"}],
        )
        constraints = get_edge_type_constraints("WILD_SOURCE_EDGE")
        assert constraints is not None
        assert constraints.sources is WILDCARD
        assert constraints.targets == {"target"}

    def test_registers_wildcard_target(self) -> None:
        register_edge_type_constraints(
            "WILD_TARGET_EDGE",
            sources=[{"type": "source"}],
            targets=None,  # Wildcard
        )
        constraints = get_edge_type_constraints("WILD_TARGET_EDGE")
        assert constraints is not None
        assert constraints.sources == {"source"}
        assert constraints.targets is WILDCARD

    def test_registers_both_wildcards(self) -> None:
        register_edge_type_constraints(
            "FULLY_WILD_EDGE",
            sources=None,
            targets=None,
        )
        constraints = get_edge_type_constraints("FULLY_WILD_EDGE")
        assert constraints is not None
        assert constraints.sources is WILDCARD
        assert constraints.targets is WILDCARD

    def test_merges_multiple_registrations(self) -> None:
        register_edge_type_constraints(
            "MERGE_EDGE",
            sources=[{"type": "a"}],
            targets=[{"type": "x"}],
        )
        register_edge_type_constraints(
            "MERGE_EDGE",
            sources=[{"type": "b"}],
            targets=[{"type": "y"}],
        )
        constraints = get_edge_type_constraints("MERGE_EDGE")
        assert constraints is not None
        assert constraints.sources == {"a", "b"}
        assert constraints.targets == {"x", "y"}

    def test_wildcard_takes_precedence_in_merge(self) -> None:
        register_edge_type_constraints(
            "MERGE_WILD_EDGE",
            sources=[{"type": "a"}],
            targets=[{"type": "x"}],
        )
        register_edge_type_constraints(
            "MERGE_WILD_EDGE",
            sources=None,  # Wildcard overrides
            targets=[{"type": "y"}],
        )
        constraints = get_edge_type_constraints("MERGE_WILD_EDGE")
        assert constraints is not None
        assert constraints.sources is WILDCARD
        assert constraints.targets == {"x", "y"}

    def test_returns_none_for_unregistered(self) -> None:
        assert get_edge_type_constraints("NONEXISTENT_EDGE") is None


class TestValidateEdgeWithEdgeConstraints:
    """Test validate_edge with Permission Union (node OR edge constraints)."""

    @pytest.fixture(autouse=True)
    def setup_constraints(self) -> None:
        """Register node and edge constraints for testing."""
        # Node with specific outbound/inbound constraints
        register_constraints(
            "constrained_node",
            outbound=[{"nodes": [{"type": "allowed_target"}], "edges": [{"type": "NODE_ALLOWED"}]}],
            inbound=[{"nodes": [{"type": "allowed_source"}], "edges": [{"type": "NODE_ALLOWED"}]}],
        )
        # Node with explicit block (empty list)
        register_constraints(
            "blocked_outbound_node",
            outbound=[],
            inbound=None,
        )
        register_constraints(
            "blocked_inbound_node",
            outbound=None,
            inbound=[],
        )
        # Unconstrained node (no constraints registered)
        # (just don't register anything for "unconstrained_node")

        # Edge constraint that grants permission
        register_edge_type_constraints(
            "EDGE_ALLOWED",
            sources=[{"type": "constrained_node"}, {"type": "unconstrained_node"}],
            targets=[{"type": "constrained_node"}, {"type": "unconstrained_node"}],
        )
        # Edge constraint with wildcard source
        register_edge_type_constraints(
            "WILD_SOURCE",
            sources=None,  # Any source
            targets=[{"type": "specific_target"}],
        )
        # Edge constraint with wildcard target
        register_edge_type_constraints(
            "WILD_TARGET",
            sources=[{"type": "specific_source"}],
            targets=None,  # Any target
        )

    def test_node_constraint_alone_allows(self) -> None:
        """Node constraint allows edge, no edge constraint needed."""
        validate_edge("constrained_node", "allowed_target", "NODE_ALLOWED")

    def test_edge_constraint_alone_allows(self) -> None:
        """Edge constraint allows edge even when node doesn't list edge type."""
        # constrained_node doesn't have EDGE_ALLOWED in its OUTBOUND_EDGES
        # but edge constraint grants permission
        validate_edge("constrained_node", "unconstrained_node", "EDGE_ALLOWED")

    def test_edge_constraint_allows_unknown_edge_type(self) -> None:
        """Edge constraint allows edge type that node doesn't know about."""
        validate_edge("unconstrained_node", "unconstrained_node", "EDGE_ALLOWED")

    def test_node_explicit_block_overrides_edge_constraint(self) -> None:
        """Node's explicit block (OUTBOUND_EDGES=[]) cannot be overridden."""
        # Even though EDGE_ALLOWED allows blocked_outbound_node, the block wins
        with pytest.raises(InvalidEdgeError) as exc_info:
            validate_edge("blocked_outbound_node", "unconstrained_node", "EDGE_ALLOWED")
        assert "cannot create any outbound edges" in str(exc_info.value)

    def test_inbound_block_overrides_edge_constraint(self) -> None:
        """Node's explicit inbound block cannot be overridden."""
        with pytest.raises(InvalidEdgeError) as exc_info:
            validate_edge("unconstrained_node", "blocked_inbound_node", "EDGE_ALLOWED")
        assert "cannot receive any inbound edges" in str(exc_info.value)

    def test_edge_wildcard_source_allows_any_source(self) -> None:
        """Edge constraint with wildcard source allows any source type."""
        # specific_target must accept the edge (it's unconstrained)
        register_constraints("specific_target", outbound=None, inbound=None)
        validate_edge("random_source_1", "specific_target", "WILD_SOURCE")
        validate_edge("random_source_2", "specific_target", "WILD_SOURCE")

    def test_edge_wildcard_target_allows_any_target(self) -> None:
        """Edge constraint with wildcard target allows any target type."""
        register_constraints("specific_source", outbound=None, inbound=None)
        validate_edge("specific_source", "random_target_1", "WILD_TARGET")
        validate_edge("specific_source", "random_target_2", "WILD_TARGET")

    def test_neither_allows_fails(self) -> None:
        """When neither node nor edge constraints allow, validation fails."""
        with pytest.raises(InvalidEdgeError):
            validate_edge("constrained_node", "wrong_target", "UNKNOWN_EDGE")

    def test_permission_union_both_allow(self) -> None:
        """When both node and edge constraints allow, edge is valid."""
        # NODE_ALLOWED is allowed by node, and we'll also register edge constraint
        register_edge_type_constraints(
            "NODE_ALLOWED",
            sources=[{"type": "constrained_node"}],
            targets=[{"type": "allowed_target"}],
        )
        validate_edge("constrained_node", "allowed_target", "NODE_ALLOWED")
