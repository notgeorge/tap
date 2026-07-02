"""grid_fixtures plugin — neutral graph-node vocabulary for grid test fixtures.

Ships four near-identical, unconstrained node types (`grid_fixtures__node` / `__hub`
/ `__leaf` / `__cycle_node`) and four wildcard-endpoint edge types (`PG_LINKS` /
`PG_NESTS` / `PG_LOOPS` / `PG_OPTIONAL`, each namespaced `…__grid_fixtures`) whose
only job is to let a test build any graph topology it needs.

This is the load-bearing test-fixture vocabulary the core suites import (the role
`lotr` has historically played). It carries no corpus, no harness, and no
dependencies — the Gridkin scenario corpus that exercises this vocabulary lives in
the `gryphon_playground` plugin, which depends on this one.

See plugins/grid_fixtures/README.md for the vocabulary reference.
"""
