"""
Edge constraint registry and validation.

Constraints are defined on domain models as OUTBOUND_EDGES and INBOUND_EDGES
class attributes. They are parsed at class definition time and stored in a
central registry for zero-DB-lookup validation.

Constraint format:
    OUTBOUND_EDGES = [
        {
            "nodes": [{"type": "precept"}, {"type": "concept"}],
            "edges": [{"type": "APPLIES_TO"}],
        },
    ]

Wildcard (any node type allowed):
    OUTBOUND_EDGES = [
        {
            # "nodes" key absent = wildcard
            "edges": [{"type": "REFERENCES"}],
        },
    ]
"""

from dataclasses import dataclass
from typing import Any

from tap_core.exceptions import InvalidEdgeError

# Sentinel for wildcard (connects to any node type)
WILDCARD = object()

# Type aliases
ConstraintEntry = dict[str, Any]  # {"nodes": [...], "edges": [...]}
ConstraintList = list[ConstraintEntry]
# Parsed: edge_type -> {node_types} or WILDCARD sentinel
ParsedConstraints = dict[str, set[str] | object]


@dataclass
class EdgeConstraints:
    """Parsed edge constraints for a single entity type."""

    # None = no restrictions, {} = block all
    # {"EDGE_TYPE": {nodes}} = allow listed, {"EDGE_TYPE": WILDCARD} = any node
    outbound: ParsedConstraints | None = None
    inbound: ParsedConstraints | None = None


# Central registry: entity_type -> EdgeConstraints
_REGISTRY: dict[str, EdgeConstraints] = {}


def _parse_constraint_list(constraint_list: ConstraintList) -> ParsedConstraints:
    """Parse [{nodes: [...], edges: [...]}] into {edge_type: {node_types} | WILDCARD}.

    Input:  [{"nodes": [{"type": "precept"}], "edges": [{"type": "APPLIES_TO"}]}]
    Output: {"APPLIES_TO": {"precept"}}

    If "nodes" key is absent, the edge type maps to WILDCARD (any node allowed).
    """
    result: ParsedConstraints = {}
    for entry in constraint_list:
        # Extract edge types from objects
        edge_types = [e["type"] for e in entry["edges"]]

        # Check for wildcard (nodes key absent)
        if "nodes" not in entry:
            for edge_type in edge_types:
                result[edge_type] = WILDCARD
        else:
            # Extract node types from objects
            nodes = {n["type"] for n in entry["nodes"]}
            for edge_type in edge_types:
                if edge_type in result:
                    if result[edge_type] is WILDCARD:
                        pass  # Wildcard already set, keep it
                    else:
                        result[edge_type] |= nodes  # type: ignore[operator]
                else:
                    result[edge_type] = nodes.copy()
    return result


def register_constraints(
    entity_type: str,
    outbound: ConstraintList | None,
    inbound: ConstraintList | None,
) -> None:
    """Register constraints for an entity type.

    Called automatically by BaseModel.__init_subclass__ when a domain model
    defines OUTBOUND_EDGES or INBOUND_EDGES.
    """
    _REGISTRY[entity_type] = EdgeConstraints(
        outbound=_parse_constraint_list(outbound) if outbound is not None else None,
        inbound=_parse_constraint_list(inbound) if inbound is not None else None,
    )


def get_constraints(entity_type: str) -> EdgeConstraints | None:
    """Get constraints for an entity type, if registered."""
    return _REGISTRY.get(entity_type)


def validate_edge(from_type: str, to_type: str, edge_type: str) -> None:
    """Validate edge creation against constraints.

    Raises InvalidEdgeError if the edge violates any constraint.
    """
    # Check outbound constraint on from_type
    if from_type in _REGISTRY:
        constraints = _REGISTRY[from_type]
        if constraints.outbound is not None:
            if not constraints.outbound:
                raise InvalidEdgeError(f"{from_type} cannot create any outbound edges")
            if edge_type not in constraints.outbound:
                raise InvalidEdgeError(
                    f"{from_type} cannot create '{edge_type}' edges. " f"Allowed: {set(constraints.outbound.keys())}"
                )
            allowed_targets = constraints.outbound[edge_type]
            if allowed_targets is not WILDCARD:
                assert isinstance(allowed_targets, set)  # for mypy
                if to_type not in allowed_targets:
                    raise InvalidEdgeError(
                        f"{from_type} cannot create '{edge_type}' edge to {to_type}. "
                        f"Allowed targets: {allowed_targets}"
                    )

    # Check inbound constraint on to_type
    if to_type in _REGISTRY:
        constraints = _REGISTRY[to_type]
        if constraints.inbound is not None:
            if not constraints.inbound:
                raise InvalidEdgeError(f"{to_type} cannot receive any inbound edges")
            if edge_type not in constraints.inbound:
                raise InvalidEdgeError(
                    f"{to_type} cannot receive '{edge_type}' edges. " f"Allowed: {set(constraints.inbound.keys())}"
                )
            allowed_sources = constraints.inbound[edge_type]
            if allowed_sources is not WILDCARD:
                assert isinstance(allowed_sources, set)  # for mypy
                if from_type not in allowed_sources:
                    raise InvalidEdgeError(
                        f"{to_type} cannot receive '{edge_type}' edge from {from_type}. "
                        f"Allowed sources: {allowed_sources}"
                    )
