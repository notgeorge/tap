---
name: build-gryphon-capability
description: Add a new capability (clause, predicate, operator) to the Gryphon graph query language. Use when extending Gryphon's grammar/AST/executor — e.g. a new WHERE operator, a new clause like SKIP, a new aggregate.
allowed-tools: Read Write Edit Bash(scripts/dc *) Bash(grep *) Bash(find *) Bash(ls *) Bash(git *) Glob Grep
argument-hint: <feature-name>
---

# Build a New Gryphon Capability

You are extending Gryphon — TAP's canonical graph query language and the read path
that all graph-shaped queries route through. A Gryphon capability touches four
artifacts in a fixed order (grammar -> AST -> parser -> executor) and ships under
a validation contract (a spec requirement, Gridkin scenarios with oracle
expecteds, openCypher-TCK-mined corner cases, and `test_gryphon.py` tests).

This skill is the end-to-end process, distilled from the ORDER BY / LIMIT,
IN-list, and OPTIONAL MATCH features. Follow it in order. Each feature is **one
commit** — the full cycle (spec + grammar + AST + parser + executor + scenarios +
tests) lands together, never as a follow-up.

## Authoritative Sources (read these first; do not guess from memory)

- **[`docs/doc-dev-gryphon-wishlist.md`](../../../docs/doc-dev-gryphon-wishlist.md)** —
  the prioritized wishlist (organized by demand-shape, not Cypher's TOC) and the
  validation contract. Read the bucket for your feature. Trust `git log` over its
  "Implementation Status" section if they disagree.
- **[`tap_grid/specs/spec-grid-traversal-language.md`](../../specs/spec-grid-traversal-language.md)** —
  the language surface: clause shape, predicate semantics, field paths, params,
  returns. Home for predicate-power requirements.
- **[`tap_grid/specs/spec-grid-traversal-execution.md`](../../specs/spec-grid-traversal-execution.md)** —
  the execution pipeline, compiler strategy, and the SQL-capture seam.
- **[`tap_grid/specs/spec-grid-gryphon-multihop-aggregation.md`](../../specs/spec-grid-gryphon-multihop-aggregation.md)** —
  the extension clauses (multi-hop, NOT EXISTS, COUNT, ORDER BY, LIMIT, OPTIONAL
  MATCH). Home for new extension-clause requirements.
- **[`plugins/gryphon_playground/specs/spec-gridkin-v0.md`](../../../plugins/gryphon_playground/specs/spec-gridkin-v0.md)** —
  the Gridkin scenario format, runner contract, and oracle discipline.

If a spec contradicts the code, flag it to the user — do not silently work around it.

## Step 1: Orient and Scope

1. Find your feature's bucket in the wishlist. Read its *What / Why / What pulls
   it in / Status flag*.
2. **Scope v0 tight.** Implement the demand-shape and nothing wider. The wishlist
   and the existing extension specs model this: ship the shape a real dashboard
   needs, reject everything else *with a clear error*, and name each rejected
   shape as a `Future` bullet. A silently-ignored construct is a bug; a clearly
   rejected one is a contract.
3. Decide which spec owns the requirement: language-surface predicates ->
   `spec-grid-traversal-language.md`; extension clauses -> the multihop-aggregation
   spec.
4. Note the openCypher TCK feature folder you will mine in Step 7 (e.g.
   `tck/features/clauses/optional-match/`).

State the agreed v0 scope before writing code — it becomes the spec requirement.

## Step 2: Spec First

Add the requirement to the owning spec **before** implementing:

- A new `RID` (`req-grid-traversal-lang-<x>` or `req-grid-gryphon-<x>`) row in the
  Requirements table.
- A requirement section: `Implementation`, `Development` (why the scope is what it
  is), an `Acceptance Criteria` ACID table (one ACID per testable behavior,
  including the rejection cases), and a `Future` list naming every deferred shape.
- If the feature was listed under another requirement's `Future`, update that list
  to point at the new RID instead.

## Step 3: Grammar (`tap_grid/gryphon/grammar.lark`)

- Add the rule(s). New top-level clauses join the `clause` alternation; new
  predicate forms extend `comparison`.
- Keyword terminals are underscore-prefixed (`_ORDER_KW: /ORDER/i`) so lark
  discards them from the parse tree — the transformer then receives only data
  tokens. A non-underscore inline regex (`/null/i`) is **kept** as a child.
- Gryphon strings are **double-quoted** (`ESCAPED_STRING`); single quotes do not
  parse. Write `["a", "b"]`, never `['a', 'b']`.

## Step 4: AST (`tap_grid/gryphon/ast_nodes.py`)

- Add frozen dataclasses for the new nodes.
- If you add a clause: add a field to `GryphonAST` (default `None`/`()` so existing
  construction sites keep working) and extend `required_params()` to walk it for
  `$param` references.
- If you add a predicate leaf: add it to the `Predicate` union **and** handle it in
  `_collect_params_from_predicate`. Then audit every predicate walker in the
  executor (Step 5) — a new leaf type that a walker does not recognize is silently
  dropped.

## Step 5: Parser (`tap_grid/gryphon/parser.py`)

- Add a transformer method per new rule; collect new clauses in `start()`.
- **Reject duplicate single-clauses at parse time** (`Only one ORDER BY ...`) — do
  not silently keep the first, which is the documented multiple-WHERE footgun.
- **`@v_args(inline=True)` token gotcha.** The transformer runs under
  `@v_args(inline=True)`. A rule whose grammar body is a bare inline regex
  alias (`value: /null/i -> null_val`) passes the matched token as a child, so the
  method **must** accept it: `def null_val(self, _token): ...`. Omitting the arg is
  the Finding-G class of bug — it parses fine in isolation and crashes only when
  that literal is used. Methods for underscore-prefixed terminals take no token.

## Step 6: Executor (`tap_grid/gryphon/executor.py`)

- Identify the dispatch path(s): the simple `_execute_ast` (type scan,
  hub-and-spoke, edge-type scan), the advanced `_execute_advanced` (multi-hop,
  NOT EXISTS, COUNT), or a new dedicated path. A genuinely new shape (e.g. OPTIONAL
  MATCH) gets its own `_execute_<feature>` and an early route in
  `execute_gryphon_raw`, wrapped in a `gryphon_stage("<label>")`.
- Apply the feature in **every** path that can reach it. ORDER BY / LIMIT had to
  land in both the type-scan projection and the aggregation path; a new predicate
  leaf must be handled in `_flatten_conjunction`, `_apply_comparison`,
  `_apply_typescan_predicate`, and `_filter_predicate_for_bindings`.
- **Reject out-of-scope shapes with a clear, actionable error** that names the
  supported form. Never silently ignore a clause.
- **Keep the emitted SQL deterministic.** Append a unique tiebreaker
  (`entity_id` / the group-by columns) to any `ORDER BY`; sort `pk__in` lists.
  Non-deterministic SQL makes the Gridkin snapshot flap.

## Step 7: Gridkin Scenarios + Oracle Discipline

Author scenarios in `plugins/gryphon_playground/scenarios/<feature>.gridkin.json`
against a Tier-1 fixture. Use the `pg_*` / `PG_*` playground vocabulary only.

The **oracle discipline** is the point of Gridkin — do it exactly:

1. Hand-author the expected envelope JSON files by **computing the result yourself
   from the fixture data**, before running the executor. The expected file is an
   oracle, not a capture.
2. Run the runner in **assert mode** and read *every* failure:
   ```bash
   scripts/dc exec web uv run pytest plugins/gryphon_playground/tests/test_gridkin.py -k <feature>
   ```
   A scenario whose only failure is `SQL: expected file missing` has a
   **content-correct** envelope. A scenario reporting `ENVELOPE MISMATCH` does not
   — fix your oracle (or the executor) and re-run. Do not proceed past Step 7.2
   until every failure is missing-SQL only.
3. Only then regenerate the SQL snapshots:
   ```bash
   scripts/dc exec -e GRIDKIN_UPDATE_SNAPSHOTS=1 web uv run pytest \
     plugins/gryphon_playground/tests/test_gridkin.py -k <feature>
   ```
   Update mode rewrites the envelope files into canonical (indent-2) form and
   generates the `.sql.txt` snapshots.
4. **Eyeball every generated `.sql.txt`.** Confirm the JOINs, predicates, GROUP BY,
   ORDER BY, and LIMIT are what the query means — this is the second independent
   correctness check beyond the envelope oracle.

Pitfall: `git diff` does **not** show untracked files, so it cannot confirm an
oracle survived snapshot regeneration. Verify correctness in step 7.2 (assert mode,
before the files are tracked), never by diffing after update mode.

Every scenario needs a non-empty `covers` array of the RIDs/ACIDs it exercises;
the loader rejects a scenario file without it.

## Step 8: Mine the openCypher TCK

The TCK is a scenario **mine**, never a source. Per the wishlist's TCK workflow and
`feedback_borrow_from_oss_prior_art` (inspire, never copy):

1. Read the TCK feature folder for the corner-case *intents* — "what historically
   broke graph engines here" (empty list, single element, ties, NULL membership,
   zero-match rows, the WHERE filter-placement gotcha).
2. Author Gridkin scenarios in TAP vocabulary covering each retained intent. Skip
   Cypher-specific quirks that are not Gryphon's contract.
3. Set the scenario's `inspired_by` to the TCK folder path — an attribution
   breadcrumb. **No TCK query text, graph data, or expected results are copied** —
   everything is re-authored in `pg_*` vocabulary against hand-built fixtures.

## Step 9: `test_gryphon.py` Tests

Add to `tap_grid/tests/test_gryphon.py`:

- A **parser** test class — pure AST assertions, no DB: the feature parses,
  variants parse, duplicates/bad forms raise `GryphonParseError`.
- An **executor** test class (`@pytest.mark.django_db(transaction=True,
  databases=["default", "search_readonly"])`) — the **rejection cases** Gridkin
  cannot express (every out-of-scope shape from Step 1 raising
  `SearchExecutionError`), plus a positive smoke test. Gridkin covers the positive
  execution surface; `test_gryphon.py` covers parse-level and error-path behavior.

Executor tests that scan a typed model (e.g. `MATCH (c:character)`) must create the
**backing model rows** (`Character.objects.create(...)`), not just `Entity` rows —
a type scan queries the typed model.

## Step 10: Lint, Test, Commit

```bash
scripts/dc exec web uv run black tap_grid/gryphon/ tap_grid/tests/test_gryphon.py
scripts/dc exec web uv run ruff check --fix tap_grid/gryphon/ tap_grid/tests/test_gryphon.py
```

Run the two suites **separately** — running them together hits a pre-existing
test-isolation quirk (transaction-mode DB reuse) that errors out unrelated tests:

```bash
scripts/dc exec web uv run pytest tap_grid/tests/test_gryphon.py -q
scripts/dc exec web uv run pytest plugins/gryphon_playground/tests/ -q
```

Then flip the spec requirement Status to `Implemented`, and follow the doc-spec
sync rules in [`specs/spec-docs.md`](../../../specs/spec-docs.md) if any doc
references the RIDs you changed (`grep -r <RID> docs/`).

Commit the whole cycle as **one commit**. Keep terminal output ASCII-only.

## Common Mistakes (do not commit any of these)

- **Capturing the oracle instead of authoring it.** Running update-snapshots first
  and committing whatever the executor produced cannot catch a systematic
  executor bug — a consistent COUNT inflation produces consistent expecteds that
  all pass on rerun. Hand-compute, then verify in assert mode (Step 7.2).
- **Single-quoted strings in a query.** Gryphon strings are double-quoted.
- **A new `Predicate` leaf that a walker silently drops.** Adding to the union is
  not enough — audit `_flatten_conjunction`, `_apply_comparison`,
  `_apply_typescan_predicate`, `_filter_predicate_for_bindings`,
  `_collect_params_from_predicate`.
- **A transformer method missing the `@v_args(inline=True)` token argument** for an
  inline-regex value rule (the `null_val` bug).
- **Silently ignoring an out-of-scope clause** instead of raising a clear error.
- **Non-deterministic emitted SQL** — no tiebreaker on ORDER BY, unsorted `pk__in`.
- **Copying TCK query text, data, or expecteds.** Inspire from the corner-case
  intent; re-author everything in TAP vocabulary.
- **A scenario file with no `covers` array** — the loader rejects it.
- **Shipping the executor change without the spec requirement and Gridkin
  scenarios in the same commit.**
