# grid_fixtures

Neutral, load-bearing test-fixture vocabulary for the TAP grid. Ships nothing but a
generic graph vocabulary the core suites (and the Gryphon playground) build fixtures
from. It has no corpus, no harness, and no dependencies.

This is the role `lotr` has historically filled ("test-fixture vocabulary the core
suites import"); `grid_fixtures` is the neutral version of it, extracted so the
`gryphon_playground` plugin can become a droppable leaf that merely *depends on* this
vocabulary. It ships two node families: **query-pattern** nodes (unconstrained, for
Gryphon executor tests) and **constraint-archetype** nodes (for edge-constraint +
validation tests) — documented in turn below.

## Node types — query-pattern (unconstrained)

Four deliberately near-identical, **unconstrained** node models — the semantic
distinction (generic / hub / leaf / cycle) is convention carried by the entity-type
slug, not by differing fields. None declares edge constraints, so a fixture is free
to build any topology (cycles, self-loops, multi-edges, fan-outs).

| entity type | class | intended shape |
|---|---|---|
| `grid_fixtures__node` | `PgNode` | generic building block |
| `grid_fixtures__hub` | `PgHub` | one node, many neighbors (hub-and-spoke) |
| `grid_fixtures__leaf` | `PgLeaf` | chain / fan-out terminal |
| `grid_fixtures__cycle_node` | `PgCycleNode` | cyclic topologies, self-loops |

Every type carries the same typed-field set so a scenario can exercise every scalar
predicate the executor supports:

`name` (string), `description` (string), `kind` (string, indexed),
`severity_score` (integer, indexed), `is_open` (boolean),
`observed_at` (datetime, nullable), `tags` (JSON object).

> The `Pg*` class names and `pg_*` module names are retained from the vocabulary's
> origin in `gryphon_playground`; renaming them would be pure churn. Only the
> entity-type / edge-type *namespace* moved (`gryphon_playground__pg_*` →
> `grid_fixtures__*`).

## Edge types — wildcard query-pattern

Four **wildcard-endpoint** edges (no source/target constraints), each namespaced
`…__grid_fixtures`:

| edge type | intended use |
|---|---|
| `PG_LINKS` | generic directional edge |
| `PG_NESTS` | compound / nested shapes |
| `PG_LOOPS` | self-loops and small cycles |
| `PG_OPTIONAL` | sparse fan-outs for OPTIONAL MATCH testing |

## Constraint-archetype node types

A second, deliberately-constrained family exists so the core suites can exercise
**edge-constraint validation** (typed edges, source/target restrictions, blocked
ends, wildcards, property schemas) against a neutral vocabulary — the role lotr's
Middle-earth types historically filled. Names describe each node's **testing
purpose**, not a domain (expressive clarity over cute names).

| entity type | class | constraint archetype it exercises |
|---|---|---|
| `grid_fixtures__unconstrained` | `Unconstrained` | NO constraints — accepts any edge, either direction (constraint absence) |
| `grid_fixtures__constrained_source` | `ConstrainedSource` | typed OUTBOUND edges to several target types + self-edges (outbound edge-type + target-type validation) |
| `grid_fixtures__constrained_target` | `ConstrainedTarget` | typed INBOUND edges from several source types + self-nesting (inbound edge-type + multi-source validation) |
| `grid_fixtures__dual_endpoint` | `DualEndpoint` | a node on BOTH ends of typed constrained edges |
| `grid_fixtures__peer_group` | `PeerGroup` | self-symmetric edges + an inbound member edge (symmetric self-edges + membership) |
| `grid_fixtures__outbound_blocked` | `OutboundBlocked` | `OUTBOUND_EDGES = []` — total outbound block (still accepts a typed inbound) |
| `grid_fixtures__inbound_blocked` | `InboundBlocked` | `INBOUND_EDGES = []` — total inbound block (still emits a typed outbound) |
| `grid_fixtures__nesting_container` | `NestingContainer` | self/other visual + edge nesting with constrained-target nodes |
| `grid_fixtures__wildcard_referencer` | `WildcardReferencer` | an outbound edge type with NO target restriction (wildcard target) + self inbound |

These carry the same 7-scalar field surface as the query-pattern nodes.
`ConstrainedSource` additionally declares a `DEFAULT_DISPLAY` (a non-default shape
plus a parent/child visual-nesting config) so the display/nesting resolvers have a
fixture too. Four types ship kebab-case SVG icons (`constrained-source`,
`constrained-target`, `dual-endpoint`, `outbound-blocked`); the rest are icon-less
on purpose (so the no-icon path has a fixture).

## Typed / constrained / schema-bearing edge types

Constraint is enforced two ways, and the edge set exercises **both**: some edges pin
`sources`/`targets` at the **edge-definition** level; others leave the edge open and
rely on the **node-level** `OUTBOUND_EDGES`/`INBOUND_EDGES` declarations. Two edges
carry a JSON Schema `property_schema` so edge-property validation has a fixture.

| edge type (`…__grid_fixtures`) | endpoints | notes |
|---|---|---|
| `CONSTRAINED_LINK` | constrained_source → constrained_target | primary edge-def-constrained edge |
| `ALT_LINK` | (node-level) source → target | second edge type over the same endpoints |
| `SCHEMA_LINK` | constrained_source → dual_endpoint | **property_schema** (proficiency enum + primary bool) |
| `REQUIRED_SCHEMA_LINK` | constrained_source → constrained_source (self) | **property_schema** with required fields + `duration_years` (int ≥ 0), `additionalProperties: false` |
| `REVERSE_CONSTRAINED_LINK` | dual_endpoint → constrained_target | reverse-direction constrained edge |
| `SYMMETRIC_LINK` | (node-level) source ↔ source | bidirectional (declared OUTBOUND *and* INBOUND) |
| `RIVAL_LINK` | (node-level) source ↔ source | second bidirectional edge type |
| `CATEGORY_LINK` | (node-level) source → outbound_blocked | edge INTO a total-outbound-block node |
| `MEMBER_LINK` | (node-level) source → peer_group | membership edge |
| `GUARD_LINK` | (node-level) | guard/protect archetype |
| `NESTING_LINK` | (node-level) nesting_container → target | containment / nesting |
| `WILDCARD_LINK` | (node-level) wildcard_referencer → * | no target-type restriction (wildcard) |

## Consumers

- **Core suites** (`tap_grid`, `tap_api`, `tap_web`, …) build fixtures from this
  vocabulary — the query-pattern nodes for Gryphon executor tests, the
  constraint-archetype nodes/edges for edge-constraint + validation tests. Feature
  tests that need a *typed editor* etc. own their fixture in the consuming app (e.g.
  `tap_web/tests/conftest.py` registers a tap_web-owned editor over the neutral
  `constrained_source` node) rather than reaching into a plugin.
- **`gryphon_playground`** declares a `depends_on` edge to `grid_fixtures` and ships
  the Gridkin scenario corpus + harness that exercise these types. See that plugin's
  `specs/spec-gryphon-playground-v0.md` for how the corpus uses the vocabulary.
