"""grid_fixtures plugin models — the neutral core-test node vocabulary.

Two families, both re-exported here:

- **Query-pattern nodes** (`pg_*` → `grid_fixtures__node`/`__hub`/`__leaf`/`__cycle_node`):
  near-identical, unconstrained, full scalar-field surface — for exercising the Gryphon
  query executor's predicate/topology corners. The semantic distinction is convention
  carried by the `entity_type` slug, not by differing fields.
- **Constraint nodes** (`Unconstrained`/`ConstrainedSource`/…): each a distinct
  edge-constraint archetype (typed outbound/inbound, blocked-inbound, blocked-outbound,
  wildcard-target, self-nesting) for exercising the grid's edge-constraint validation.
  They share the same uniform scalar field surface and differ ONLY by their
  `OUTBOUND_EDGES` / `INBOUND_EDGES` declarations.

See plugins/grid_fixtures/README.md.
"""

from tap_plugin.grid_fixtures.models.constrained_source import ConstrainedSource
from tap_plugin.grid_fixtures.models.constrained_target import ConstrainedTarget
from tap_plugin.grid_fixtures.models.dual_endpoint import DualEndpoint
from tap_plugin.grid_fixtures.models.inbound_blocked import InboundBlocked
from tap_plugin.grid_fixtures.models.nesting_container import NestingContainer
from tap_plugin.grid_fixtures.models.outbound_blocked import OutboundBlocked
from tap_plugin.grid_fixtures.models.peer_group import PeerGroup
from tap_plugin.grid_fixtures.models.pg_cycle_node import PgCycleNode
from tap_plugin.grid_fixtures.models.pg_hub import PgHub
from tap_plugin.grid_fixtures.models.pg_leaf import PgLeaf
from tap_plugin.grid_fixtures.models.pg_node import PgNode
from tap_plugin.grid_fixtures.models.unconstrained import Unconstrained
from tap_plugin.grid_fixtures.models.wildcard_referencer import WildcardReferencer

__all__ = [
    "ConstrainedSource",
    "ConstrainedTarget",
    "DualEndpoint",
    "InboundBlocked",
    "NestingContainer",
    "OutboundBlocked",
    "PeerGroup",
    "PgCycleNode",
    "PgHub",
    "PgLeaf",
    "PgNode",
    "Unconstrained",
    "WildcardReferencer",
]
