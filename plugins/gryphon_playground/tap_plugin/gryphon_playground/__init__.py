"""Gryphon Playground plugin — the Gridkin scenario corpus + harness.

Owns no node/edge vocabulary of its own: it builds fixtures from the neutral
grid_fixtures__* vocabulary (the `grid_fixtures` plugin it depends on) and ships the
Gridkin scenario corpus that exercises the Gryphon query language against it.

See specs/spec-gryphon-playground-v0.md (plugin scope; the grid_fixtures `pg_*` /
`PG_*` vocabulary the corpus targets) and specs/spec-gridkin-v0.md (the Gridkin
scenario file format).
"""
