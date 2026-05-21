# Gryphon Playground

The home for exercising and testing the **Gryphon** query language: a bespoke
playground node/edge vocabulary, the **Gridkin** scenario corpus, and the
pytest-discoverable Gridkin runner.

## What this plugin owns

- **Playground vocabulary** — four abstract node types (`pg_node`, `pg_hub`,
  `pg_leaf`, `pg_cycle_node`) and four edge types (`PG_LINKS`, `PG_NESTS`,
  `PG_LOOPS`, `PG_OPTIONAL`), used *only* by Gridkin fixtures. Decoupled from
  every real domain plugin so test graphs never constrain — and are never
  broken by — real-world graph evolution.
- **Gridkin scenario corpus** — `scenarios/*.gridkin.json`, their backing GRIFT
  `fixtures/`, and the `expected/` envelope + SQL side files.
- **The Gridkin runner** — discovers and drives the scenarios under pytest.

## What this plugin does NOT own

- The Gryphon executor / parser / grammar — that source lives in
  `tap_grid/gryphon/`. Gridkin *tests* the executor; it does not implement it.
- Any user-facing surface — no pages, panels, searches, or layouts.

## The playground vocabulary

| Node type | Intent |
| --- | --- |
| `pg_node` | Generic node — the default building block |
| `pg_hub` | A hub (one node, many neighbors) |
| `pg_leaf` | A leaf (terminal in a chain) |
| `pg_cycle_node` | Cycle / self-loop construction |

The four are deliberately near-identical — same typed-field set (`description`,
`kind`, `severity_score`, `is_open`, `observed_at`, `tags`), covering every
scalar predicate type the executor supports. The distinction is convention
carried by the `entity_type` slug, so a scenario can target a type to construct
an intended shape, and label / type-scan patterns have distinct labels to match.

| Edge type | Intent |
| --- | --- |
| `PG_LINKS` | Generic directional edge |
| `PG_NESTS` | Compound / nested shapes |
| `PG_LOOPS` | Self-loops and small cycles |
| `PG_OPTIONAL` | Sparse fan-outs (OPTIONAL MATCH testing) |

All edge types are wildcard (no source/target constraints) so fixtures can
build any topology — cycles, self-loops, multi-edges, cross-type links.

## Read first

- `specs/spec-gryphon-playground-v0.md` — this plugin: scope, the `pg_*` /
  `PG_*` vocabulary, the two-tier fixture structure.
- `specs/spec-gridkin-v0.md` — the Gridkin scenario file format, runner
  contract, oracle assertion discipline, snapshot regeneration discipline,
  requirement traceability, TCK-as-inspiration workflow, JSON Schema. Its
  **v0 Non-Goals** section is required reading before proposing scope expansion.
- `../../docs/doc-dev-gryphon-wishlist.md` — the operational companion:
  Gryphon's feature trajectory and the validation discipline every extension
  ships under.

## Status

v0 scaffold. The playground vocabulary (4 node types, 4 edge types) is in
place; the Gridkin runner, JSON Schema, fixtures, and scenario corpus land in
the following phases of this work.

The plugin **is** registered in `INSTALLED_APPS` — unlike a standalone-repo
plugin awaiting integration, its models must migrate and its runner must be
collected by pytest. Alongside `lotr` it is a load-bearing test-fixture plugin.

## Validate

    python -m tap_plugins.validate_plugin plugins/gryphon_playground
