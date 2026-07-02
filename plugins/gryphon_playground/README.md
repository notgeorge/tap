# Gryphon Playground

The home for exercising and testing the **Gryphon** query language: the **Gridkin**
scenario corpus and the pytest-discoverable Gridkin runner, built on the neutral
graph vocabulary the [`grid_fixtures`](../grid_fixtures/README.md) plugin provides.

## What this plugin owns

- **Gridkin scenario corpus** — `scenarios/*.gridkin.json`, their backing GRIFT
  `fixtures/`, and the `expected/` envelope + SQL side files.
- **The Gridkin runner** — discovers and drives the scenarios under pytest.
- **The harness** — the loader, model oracle, coverage/stage-coverage gates,
  metamorphic (TLP) probes, the differential fuzzer, and the findings ledger
  (`gridkin/`).

## What this plugin does NOT own

- **Node or edge types** — the abstract vocabulary its fixtures use lives in the
  `grid_fixtures` plugin, declared as a `depends_on`. This plugin registers none of
  its own. (Extracted so the core suites can share it and so this plugin is a
  droppable leaf.)
- The Gryphon executor / parser / grammar — that source lives in
  `tap_grid/gryphon/`. Gridkin *tests* the executor; it does not implement it.
- Any user-facing surface — no pages, panels, searches, or layouts.

## The vocabulary the corpus targets

Owned by the `grid_fixtures` plugin; listed here as the scenario-author reference.

| Node type (entity-type slug) | Intent |
| --- | --- |
| `grid_fixtures__node` | Generic node — the default building block |
| `grid_fixtures__hub` | A hub (one node, many neighbors) |
| `grid_fixtures__leaf` | A leaf (terminal in a chain) |
| `grid_fixtures__cycle_node` | Cycle / self-loop construction |

The four are deliberately near-identical — same typed-field set (`description`,
`kind`, `severity_score`, `is_open`, `observed_at`, `tags`), covering every
scalar predicate type the executor supports. The distinction is convention
carried by the `entity_type` slug, so a scenario can target a type to construct
an intended shape, and label / type-scan patterns have distinct labels to match.
(The backing Python classes keep their origin names `PgNode` / `PgHub` / `PgLeaf`
/ `PgCycleNode`.)

| Edge type (registered `<TYPE>__grid_fixtures`) | Intent |
| --- | --- |
| `PG_LINKS` | Generic directional edge |
| `PG_NESTS` | Compound / nested shapes |
| `PG_LOOPS` | Self-loops and small cycles |
| `PG_OPTIONAL` | Sparse fan-outs (OPTIONAL MATCH testing) |

All edge types are wildcard (no source/target constraints) so fixtures can
build any topology — cycles, self-loops, multi-edges, cross-type links.

## Read first

- `specs/spec-gryphon-playground-v0.md` — this plugin: scope, the `grid_fixtures`
  vocabulary it consumes, the two-tier fixture structure.
- `../grid_fixtures/README.md` — the vocabulary reference (node/edge types).
- `specs/spec-gridkin-v0.md` — the Gridkin scenario file format, runner
  contract, oracle assertion discipline, snapshot regeneration discipline,
  requirement traceability, TCK-as-inspiration workflow, JSON Schema. Its
  **v0 Non-Goals** section is required reading before proposing scope expansion.
- `../../docs/misc/doc-dev-gryphon-wishlist.md` — the operational companion:
  Gryphon's feature trajectory and the validation discipline every extension
  ships under.

## Status

v0. The Gridkin runner and JSON Schema, and a broad scenario corpus over the
`grid_fixtures` vocabulary, are in place and green. Growing the Tier-1 fixture set
and the scenario corpus, and adding a Tier-2 canonical playground fixture, is
ongoing demand-driven work.

The plugin **is** installed (editable) + registered in `INSTALLED_APPS` in any env
that runs the Gridkin lane, so its runner is collected by pytest. But it is now a
pure **leaf**: it carries no models of its own, nothing outside it imports it, and
dropping it from a profile reds only the Gridkin lane — the core suites reach for
`grid_fixtures`, not this plugin.

## Validate

    python -m tap_plugins.validate_plugin plugins/gryphon_playground
