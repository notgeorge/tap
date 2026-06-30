# Handoff — Gryphon single-hop relationship ENVELOPE silently drops its WHERE

**Status:** open defect, recorded but not fixed. Reserved for a fresh session.
**Found:** 2026-06-30, while authoring a two-node-AND gridkin scenario (caught by oracle discipline — a wrong row leaked into the regenerated oracle).
**Severity:** silent wrong results (too many rows) for a common query shape. Same bug *class* as the coercion defect (`req-grid-traversal-lang-type-strictness`) that was just fixed: the engine returns plausible-but-wrong data rather than erroring.
**Ledger:** recorded in `plugins/gryphon_playground/scenarios/tck-coverage.json` under `clauses/match-where`, `kind: feature`.

---

## The bug in one sentence

A single-hop relationship **envelope** query (a `MATCH (a)-[:T]->(b)` with **no `RETURN`**) honors **only an `entity_id` anchor** from its `WHERE`; every other predicate — data-lane comparisons, `IN`, `IS NULL`, a second variable's condition, anything `AND`-ed on — is **silently dropped**, so the query returns every structurally-matching edge instead of the filtered subset.

## Reproduction

```
MATCH (h:pg_hub)-[:PG_LINKS]->(n:pg_node)
WHERE h.data.severity_score = 0 AND n.data.severity_score > 15
```
Fixture `sparse_dense.grift.json`: Dense Hub (sev 0) → Neighbor One (10), Neighbor Two (20), Neighbor Three (30).

- **Expected:** hub + {Neighbor Two, Neighbor Three} (those with sev > 15).
- **Actual:** hub + {Neighbor One, Two, Three} — **Neighbor One leaks in**; the `n.data.severity_score > 15` (and the `h` predicate) are absent from the SQL entirely. The generated SQL filters only `edge_type` + endpoint `entity_type`s; there is no `severity_score` clause and no params for it.

The matching aggregation/row-projection form is **correct** and is the reference for the fix:
```
MATCH (h:pg_hub)-[:PG_LINKS]->(n:pg_node)
WHERE h.data.severity_score = 0 AND n.data.severity_score > 15
RETURN h.entity_id AS hub_id, COUNT(n) AS high_neighbors
```
→ SQL contains `... AND pg_hub.severity_score = 0 AND pg_node.severity_score > 15` (params `Int4(0), Int4(15)`), result `high_neighbors: 2`. This is the committed scenario `aggregation: one AND constrains two different bound nodes …` (`aggregation__two_node_and`).

## Root cause (exact locations — line numbers approximate, will drift)

All in `tap_grid/gryphon/executor.py`:

- **`_dispatch_pattern` (~line 344)** receives `where_clause=ast.where_clause`, extracts the `entity_id` anchor (`anchor_var` / `entity_id_value`), then routes the single-hop case:
  - **~line 402:** if there's an `entity_id` anchor matching the pattern → `_execute_hub_and_spoke(entity_id=…, edge_pattern=…)` — note it passes the *anchor value only*, **not** `where_clause`. Any non-anchor remainder of the WHERE is discarded.
  - **~line 418:** otherwise → `_execute_edge_type_scan(left_node, right_node, edge_pattern, …)` — **`where_clause` is never passed in at all.**
- **`_execute_edge_type_scan` (~line 1223)** builds an `Edge.objects` queryset filtered by `edge_type` + endpoint `entity_type`s + inline edge-property map only. It has no `where_clause` parameter and applies no WHERE. Its docstring even says "where there is no WHERE anchor" — but the dispatcher routes patterns that *do* carry a (non-anchor) WHERE here, so the WHERE is lost.
- **`_execute_hub_and_spoke` (~line 1108)** applies only the `entity_id` anchor (as `from_entity_id` / `to_entity_id`).

So the WHERE clause is only ever honored to the extent it is an `entity_id` anchor.

## Why the aggregation path is correct (the reference implementation to mirror)

Row-projection / aggregation single-hop and multi-hop queries go through the **chain executor**, which *does* apply the full WHERE:

- **`_build_chain_queryset` (~line 1748)** builds the joined edge queryset with per-variable bindings.
- **`_apply_predicate_to_qs` (~line 1835)** compiles the WHERE into a `Q` via `_predicate_to_q` using a per-variable resolver (`bindings[var]` → ORM path) — it resolves `h.data.severity_score` and `n.data.severity_score` to the correct endpoint per-model columns and filters on both.
- It also already threads **type-strictness** (`declared_types` → `_declared_data_types`/`_enforce_type_strictness`, the `req-grid-traversal-lang-type-strictness` work). **Whatever fix is chosen must thread strictness through the envelope path too**, so the envelope path rejects cross-type predicates the same way the chain path does. (Today the envelope path skips strictness because it skips the WHERE entirely.)

## Fix options

1. **Route envelope-with-WHERE through the chain machinery (preferred).** When a single-hop pattern has a non-anchor WHERE and no RETURN, build the chain queryset (`_build_chain_queryset`), apply `_apply_predicate_to_qs`, then serialize as a graph envelope instead of rows. Reuses the already-correct, strictness-aware WHERE path; the only new work is envelope serialization off the chain queryset (a serializer for nodes+edges from the joined edge rows). Keep the fast `_execute_edge_type_scan` path for the genuinely-WHERE-less case.
2. **Apply the WHERE inside `_execute_edge_type_scan`.** Pass `where_clause` + bindings in and apply `_predicate_to_q` (with the per-variable resolver + `declared_types`) as a `.filter()` on the `Edge` queryset. More localized but duplicates the binding-resolution logic the chain path already has.

Either way, also fix `_execute_hub_and_spoke` to apply the **AND-ed remainder** beyond the `entity_id` anchor (e.g. `WHERE h.entity_id = $x AND n.data.kind = "neighbor"`).

**Decide apply-vs-reject:** applying the WHERE is the right behavior. If any predicate shape genuinely can't be supported on the envelope path, it must **reject** (raise `SearchExecutionError`), never silently drop — silent-drop is the defect.

### Gotchas

- **Direction fan-out.** `_execute_edge_type_scan` handles `out` / `in` / `any`; the undirected (`any`) case runs **two queries and unions** them — the WHERE filter must be applied to **both** arms.
- **Endpoint joins.** A data-lane predicate on `h` (e.g. `h.data.severity_score`) lives on the per-model table, reached from `Edge` via `from_entity` → per-model. The chain bindings already encode these paths; reuse them rather than hand-rolling join strings.
- **Type-strictness composition.** Thread `declared_types` (per-variable model from the binding `label`) so the envelope path rejects cross-type predicates identically to the chain path.
- **SQL capture.** Gridkin snapshots the SQL; the envelope path emits multi-statement SQL (`gryphon_stage(...)`). New/changed statements will change the snapshots — regenerate and review per oracle discipline.

## Test approach

- The reproduction above is the regression test. Add **envelope-form** gridkin scenarios for single-hop relationship + non-anchor WHERE (data-lane comparison, `IN`, `IS NULL`, anchor `AND` data-lane remainder), under `hub_and_spoke` / `edge_type_scan`. Predict results by hand, regenerate, and **verify the oracle** (this bug was caught precisely because a wrong node leaked into the regenerated oracle — do not trust a captured oracle you didn't read).
- Keep the existing `aggregation__two_node_and` scenario as the "this shape already works" anchor.
- After the fix, the `clauses/match-where` defect gap in `tck-coverage.json` flips from `feature` to covered — strike it and add the new envelope scenarios' folder cites.

## Validation commands

```
# regenerate oracles for new/changed scenarios (seeds actor + fixture)
./scripts/dc exec -T -e GRIDKIN_UPDATE_SNAPSHOTS=1 web uv run pytest \
  plugins/gryphon_playground/tests/test_gridkin.py -k "<slug>" -q

# full gridkin + internals + gryphon unit (run as ONE invocation; never overlap
# two pytest runs — concurrent runs deadlock the test DB)
./scripts/dc exec -T web uv run pytest \
  plugins/gryphon_playground/tests/test_gridkin.py \
  plugins/gryphon_playground/tests/test_gridkin_internals.py \
  tap_grid/tests/test_gryphon.py tap_grid/tests/test_gryphon_sql_capture.py -q -p no:randomly

# lint/type
./scripts/dc exec -T web bash -c "uv run black tap_grid/gryphon/executor.py -q && uv run ruff check tap_grid/gryphon/executor.py && uv run mypy tap_grid/gryphon/executor.py"
```

## Pointers

- Spec: `tap_grid/specs/spec-grid-traversal-language.md` — the WHERE / pattern requirements; add the envelope-WHERE behavior to the relevant requirement's Background once fixed.
- Strictness machinery (mirror it): `req-grid-traversal-lang-type-strictness` in the same spec; `_declared_data_types` / `_enforce_type_strictness` in the executor.
- Divergence ledger: `docs/misc/doc-dev-gryphon-vs-cypher.md`.
