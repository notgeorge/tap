# grid_fixtures

Neutral, load-bearing test-fixture vocabulary for the TAP grid. Ships nothing but a
generic graph vocabulary the core suites (and the Gryphon playground) build fixtures
from. It has no corpus, no harness, and no dependencies.

This is the role `lotr` has historically filled ("test-fixture vocabulary the core
suites import"); `grid_fixtures` is the neutral version of it, extracted so the
`gryphon_playground` plugin can become a droppable leaf that merely *depends on* this
vocabulary.

## Node types

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

## Edge types

Four **wildcard-endpoint** edges (no source/target constraints), each namespaced
`…__grid_fixtures`:

| edge type | intended use |
|---|---|
| `PG_LINKS` | generic directional edge |
| `PG_NESTS` | compound / nested shapes |
| `PG_LOOPS` | self-loops and small cycles |
| `PG_OPTIONAL` | sparse fan-outs for OPTIONAL MATCH testing |

## Consumers

- **Core suites** (`tap_grid`, `tap_api`, …) build fixtures from this vocabulary.
- **`gryphon_playground`** declares a `depends_on` edge to `grid_fixtures` and ships
  the Gridkin scenario corpus + harness that exercise these types. See that plugin's
  `specs/spec-gryphon-playground-v0.md` for how the corpus uses the vocabulary.
