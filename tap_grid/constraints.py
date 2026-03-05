"""
Edge constraint registry and validation.

TAP supports two complementary constraint systems:

1. NODE CONSTRAINTS (on domain models):
   Defined as OUTBOUND_EDGES/INBOUND_EDGES class attributes on BaseModel subclasses.
   These specify what edges a node type can create/receive.

2. EDGE CONSTRAINTS (on edge types):
   Defined as sources/targets in edge_types entries in TapPluginConfig.
   These specify what nodes an edge type can connect.

Validation uses Permission Union: an edge is allowed if EITHER node OR edge
constraints permit it, unless explicitly blocked.

Node constraint format:
    OUTBOUND_EDGES = [
        {"nodes": [{"type": "precept"}], "edges": [{"type": "APPLIES_TO"}]},
    ]

Edge constraint format (in TapPluginConfig.edge_types):
    edge_types = [
        {"slug": "MENTORS", "sources": [{"type": "character"}], "targets": [{"type": "character"}]},
    ]

Wildcard (any type allowed): omit the "nodes", "sources", or "targets" key.
"""

from dataclasses import dataclass
from typing import Any

import jsonschema

from tap_grid.exceptions import EdgePropertyValidationError, InvalidEdgeError

# Sentinel for wildcard (connects to any node type)
WILDCARD = object()

# Type aliases
ConstraintEntry = dict[str, Any]  # {"nodes": [...], "edges": [...]}
ConstraintList = list[ConstraintEntry]
# Parsed: edge_type -> {node_types} or WILDCARD sentinel
ParsedConstraints = dict[str, set[str] | object]


@dataclass
class NodeConstraints:
    """Parsed constraints for a node type (from OUTBOUND_EDGES/INBOUND_EDGES)."""

    # None = no restrictions, {} = block all
    # {"EDGE_TYPE": {nodes}} = allow listed, {"EDGE_TYPE": WILDCARD} = any node
    outbound: ParsedConstraints | None = None
    inbound: ParsedConstraints | None = None


@dataclass
class EdgeTypeConstraints:
    """Constraints for an edge type (from edge_types in TapPluginConfig).

    Specifies which source and target node types this edge can connect.
    """

    # None = no constraint defined (unconstrained)
    # WILDCARD = explicitly any type allowed
    # set() = no types allowed (edge cannot be used)
    # {types} = only listed types allowed
    sources: set[str] | object | None = None
    targets: set[str] | object | None = None


# Node constraint registry: entity_type -> NodeConstraints
_NODE_REGISTRY: dict[str, NodeConstraints] = {}

# Edge type constraint registry: edge_type -> EdgeTypeConstraints
_EDGE_TYPE_REGISTRY: dict[str, EdgeTypeConstraints] = {}

# Edge property schema registry: edge_type -> JSON Schema dict
# One schema per edge type. Duplicate registration is a configuration error.
_EDGE_PROPERTY_SCHEMA_REGISTRY: dict[str, dict[str, Any]] = {}

# Edge default dimensions registry: edge_type -> dimensions dict
# Declared via default_dimensions in TapPluginConfig.edge_types entries.
_EDGE_DEFAULT_DIMENSIONS_REGISTRY: dict[str, dict[str, str]] = {}

# Backwards compatibility alias
EdgeConstraints = NodeConstraints
_REGISTRY = _NODE_REGISTRY


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
    """Register node constraints for an entity type.

    Called automatically by BaseModel.__init_subclass__ when a domain model
    defines OUTBOUND_EDGES or INBOUND_EDGES.
    """
    _NODE_REGISTRY[entity_type] = NodeConstraints(
        outbound=_parse_constraint_list(outbound) if outbound is not None else None,
        inbound=_parse_constraint_list(inbound) if inbound is not None else None,
    )


def register_edge_type_constraints(
    edge_type: str,
    sources: list[dict[str, str]] | None,
    targets: list[dict[str, str]] | None,
) -> None:
    """Register constraints for an edge type.

    Called by TapPluginConfig._register_types() when a plugin defines
    sources/targets in its edge_types.

    Args:
        edge_type: The edge type slug (e.g., "MENTORS")
        sources: List of source node type dicts, or None for wildcard
        targets: List of target node type dicts, or None for wildcard
    """
    # Parse sources
    if sources is None:
        parsed_sources: set[str] | object | None = WILDCARD
    elif not sources:
        parsed_sources = set()  # Empty list = block
    else:
        parsed_sources = {s["type"] for s in sources}

    # Parse targets
    if targets is None:
        parsed_targets: set[str] | object | None = WILDCARD
    elif not targets:
        parsed_targets = set()
    else:
        parsed_targets = {t["type"] for t in targets}

    # Merge if already registered (multiple plugins may define same edge type)
    if edge_type in _EDGE_TYPE_REGISTRY:
        existing = _EDGE_TYPE_REGISTRY[edge_type]
        parsed_sources = _merge_constraint_sets(existing.sources, parsed_sources)
        parsed_targets = _merge_constraint_sets(existing.targets, parsed_targets)

    _EDGE_TYPE_REGISTRY[edge_type] = EdgeTypeConstraints(
        sources=parsed_sources,
        targets=parsed_targets,
    )


def _merge_constraint_sets(
    existing: set[str] | object | None,
    new: set[str] | object | None,
) -> set[str] | object | None:
    """Merge two constraint sets. Wildcard takes precedence."""
    if existing is WILDCARD or new is WILDCARD:
        return WILDCARD
    if existing is None:
        return new
    if new is None:
        return existing
    # Both are sets, union them
    assert isinstance(existing, set) and isinstance(new, set)
    return existing | new


def get_constraints(entity_type: str) -> NodeConstraints | None:
    """Get node constraints for an entity type, if registered."""
    return _NODE_REGISTRY.get(entity_type)


def get_edge_type_constraints(edge_type: str) -> EdgeTypeConstraints | None:
    """Get constraints for an edge type, if registered."""
    return _EDGE_TYPE_REGISTRY.get(edge_type)


def register_edge_property_schema(edge_type: str, schema: dict[str, Any]) -> None:
    """Register a JSON Schema for an edge type's properties.

    Called by TapPluginConfig._register_edge_constraints() when a plugin defines
    property_schema on an edge_types entry.

    Raises ValueError if a schema is already registered for this edge_type.
    No merge behavior: property schemas must be unique per edge type to prevent
    silent drift between plugins that share an edge type slug.

    Args:
        edge_type: The edge type slug (e.g., "USES_PANEL").
        schema: A JSON Schema dict used to validate Edge.properties.
    """
    if edge_type in _EDGE_PROPERTY_SCHEMA_REGISTRY:
        raise ValueError(
            f"A property_schema is already registered for edge type '{edge_type}'. "
            "Each edge type may have at most one property schema."
        )
    _EDGE_PROPERTY_SCHEMA_REGISTRY[edge_type] = schema


def get_edge_property_schema(edge_type: str) -> dict[str, Any] | None:
    """Return the registered JSON Schema for an edge type, or None if not defined."""
    return _EDGE_PROPERTY_SCHEMA_REGISTRY.get(edge_type)


def register_edge_default_dimensions(edge_type: str, dimensions: dict[str, str]) -> None:
    """Register default dimensions for an edge type.

    Called by TapPluginConfig._register_edge_constraints() when a plugin declares
    default_dimensions on an edge_types entry.

    Raises ValueError if dimensions are already registered for this edge_type.
    No merge behavior: default dimension declarations must be unique per edge type.

    Args:
        edge_type: The edge type slug (e.g., "USES_PANEL").
        dimensions: A dict of dimension key/value pairs to apply to the edge's backing Entity.
    """
    if edge_type in _EDGE_DEFAULT_DIMENSIONS_REGISTRY:
        raise ValueError(
            f"Default dimensions are already registered for edge type '{edge_type}'. "
            "Each edge type may have at most one default_dimensions declaration."
        )
    _EDGE_DEFAULT_DIMENSIONS_REGISTRY[edge_type] = dict(dimensions)


def get_edge_default_dimensions(edge_type: str) -> dict[str, str]:
    """Return the registered default dimensions for an edge type, or {} if not defined."""
    return dict(_EDGE_DEFAULT_DIMENSIONS_REGISTRY.get(edge_type, {}))


def validate_edge_properties(edge_type: str, properties: Any) -> None:
    """Validate edge properties against the registered schema for an edge type.

    No-ops when no schema is registered for the edge type. Schema strictness
    (e.g., additionalProperties) is fully controlled by the schema author.

    Raises EdgePropertyValidationError if properties fail schema validation.

    Args:
        edge_type: The edge type slug.
        properties: The Edge.properties value to validate.
    """
    schema = _EDGE_PROPERTY_SCHEMA_REGISTRY.get(edge_type)
    if schema is None:
        return
    try:
        jsonschema.validate(instance=properties, schema=schema)
    except jsonschema.ValidationError as exc:
        raise EdgePropertyValidationError(
            f"Edge properties for '{edge_type}' failed schema validation: {exc.message}"
        ) from exc


def _is_explicitly_blocked_outbound(node_type: str) -> bool:
    """Check if node has OUTBOUND_EDGES = [] (explicit block all)."""
    if node_type not in _NODE_REGISTRY:
        return False
    constraints = _NODE_REGISTRY[node_type]
    return constraints.outbound is not None and constraints.outbound == {}


def _is_explicitly_blocked_inbound(node_type: str) -> bool:
    """Check if node has INBOUND_EDGES = [] (explicit block all)."""
    if node_type not in _NODE_REGISTRY:
        return False
    constraints = _NODE_REGISTRY[node_type]
    return constraints.inbound is not None and constraints.inbound == {}


def _node_allows_outbound(from_type: str, to_type: str, edge_type: str) -> bool:
    """Check if node's OUTBOUND_EDGES allows this edge.

    Returns True if:
    - Node has no constraints (unconstrained)
    - Node's constraints allow this edge_type to this to_type
    - Node's constraints have wildcard for this edge_type
    """
    if from_type not in _NODE_REGISTRY:
        return True  # Unconstrained node allows everything

    constraints = _NODE_REGISTRY[from_type]
    if constraints.outbound is None:
        return True  # No outbound constraints = allow all

    if not constraints.outbound:
        return False  # Empty dict = block all

    if edge_type not in constraints.outbound:
        return False  # Edge type not in allowed list

    allowed_targets = constraints.outbound[edge_type]
    if allowed_targets is WILDCARD:
        return True

    assert isinstance(allowed_targets, set)
    return to_type in allowed_targets


def _node_allows_inbound(to_type: str, from_type: str, edge_type: str) -> bool:
    """Check if node's INBOUND_EDGES allows this edge."""
    if to_type not in _NODE_REGISTRY:
        return True  # Unconstrained node allows everything

    constraints = _NODE_REGISTRY[to_type]
    if constraints.inbound is None:
        return True

    if not constraints.inbound:
        return False  # Empty dict = block all

    if edge_type not in constraints.inbound:
        return False

    allowed_sources = constraints.inbound[edge_type]
    if allowed_sources is WILDCARD:
        return True

    assert isinstance(allowed_sources, set)
    return from_type in allowed_sources


def _edge_allows_source(from_type: str, edge_type: str) -> bool:
    """Check if edge type constraint allows this source node type."""
    if edge_type not in _EDGE_TYPE_REGISTRY:
        return False  # No edge constraint = no additional permission

    constraints = _EDGE_TYPE_REGISTRY[edge_type]
    if constraints.sources is None:
        return False  # None = not defined, no permission granted

    if constraints.sources is WILDCARD:
        return True

    assert isinstance(constraints.sources, set)
    return from_type in constraints.sources


def _edge_allows_target(to_type: str, edge_type: str) -> bool:
    """Check if edge type constraint allows this target node type."""
    if edge_type not in _EDGE_TYPE_REGISTRY:
        return False

    constraints = _EDGE_TYPE_REGISTRY[edge_type]
    if constraints.targets is None:
        return False

    if constraints.targets is WILDCARD:
        return True

    assert isinstance(constraints.targets, set)
    return to_type in constraints.targets


def validate_edge(from_type: str, to_type: str, edge_type: str) -> None:
    """Validate edge creation against node and edge type constraints.

    Uses Permission Union: an edge is allowed if EITHER node OR edge type
    constraints permit it, unless explicitly blocked by the node.

    Raises InvalidEdgeError if the edge violates constraints.
    """
    # Phase 1: Check explicit blocks (these always fail, edge constraints can't override)
    if _is_explicitly_blocked_outbound(from_type):
        raise InvalidEdgeError(f"{from_type} cannot create any outbound edges")
    if _is_explicitly_blocked_inbound(to_type):
        raise InvalidEdgeError(f"{to_type} cannot receive any inbound edges")

    # Phase 2: Check source permission (node OR edge constraint)
    source_allowed_by_node = _node_allows_outbound(from_type, to_type, edge_type)
    source_allowed_by_edge = _edge_allows_source(from_type, edge_type)

    if not (source_allowed_by_node or source_allowed_by_edge):
        # Build helpful error message
        if from_type in _NODE_REGISTRY:
            constraints = _NODE_REGISTRY[from_type]
            if constraints.outbound and edge_type in constraints.outbound:
                allowed_targets = constraints.outbound[edge_type]
                raise InvalidEdgeError(
                    f"{from_type} cannot create '{edge_type}' edge to {to_type}. " f"Allowed targets: {allowed_targets}"
                )
            elif constraints.outbound:
                raise InvalidEdgeError(
                    f"{from_type} cannot create '{edge_type}' edges. " f"Allowed: {set(constraints.outbound.keys())}"
                )
        raise InvalidEdgeError(f"{from_type} cannot create '{edge_type}' edge to {to_type}")

    # Phase 3: Check target permission (node OR edge constraint)
    target_allowed_by_node = _node_allows_inbound(to_type, from_type, edge_type)
    target_allowed_by_edge = _edge_allows_target(to_type, edge_type)

    if not (target_allowed_by_node or target_allowed_by_edge):
        # Build helpful error message
        if to_type in _NODE_REGISTRY:
            constraints = _NODE_REGISTRY[to_type]
            if constraints.inbound and edge_type in constraints.inbound:
                allowed_sources = constraints.inbound[edge_type]
                raise InvalidEdgeError(
                    f"{to_type} cannot receive '{edge_type}' edge from {from_type}. "
                    f"Allowed sources: {allowed_sources}"
                )
            elif constraints.inbound:
                raise InvalidEdgeError(
                    f"{to_type} cannot receive '{edge_type}' edges. " f"Allowed: {set(constraints.inbound.keys())}"
                )
        raise InvalidEdgeError(f"{to_type} cannot receive '{edge_type}' edge from {from_type}")
