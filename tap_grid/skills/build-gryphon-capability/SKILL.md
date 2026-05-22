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

- **[`docs/misc/doc-dev-gryphon-wishlist.md`](../../../docs/misc/doc-dev-gryphon-wishlist.md)** —
  the prioritized wishlist (organized by demand-shape, not Cypher's TOC) and the
  validation contract. Read the bucket for your feature. Trust `git log` over its
  "Implementation Status" section if they disagree.
- **[`tap_grid/specs/spec-grid-traversal-language.md`](../../specs/spec-grid-traversal-language.md)** —
  the language surface: clause shape, predicate semantics, field paths, params,
  returns. Home for predicate-power requirements.
- **[`tap_grid/specs/spec-grid-traversal-execution.md`](../../specs/spec-grid-traversal-execution.md)** —
  the execution pipeline, compiler strategy, the SQL-capture seam, and the **lowering
  ladder** (`req-grid-traversal-exec-lowering`) — the rung discipline Step 6 must obey.
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

The spec requirement is written **before** any grammar, AST, or executor code — the
v0 scope agreed in Step 1 *is* this requirement. The spec is the canonical source of
truth; the implementation is downstream of it, never the reverse. Writing the
requirement first also forces the scope to be concrete before code makes it
accidentally concrete.

### Which spec owns it

- A new predicate, operator, or field-path capability — something that extends what a
  `WHERE` clause or a projection can *say* — belongs in
  `spec-grid-traversal-language.md`.
- A new clause or a new execution shape — `ORDER BY`, `LIMIT`, `OPTIONAL MATCH`, an
  aggregate — belongs in `spec-grid-gryphon-multihop-aggregation.md`.

If unsure, find the nearest sibling capability and put the new requirement where it
lives.

### The requirement, part by part

This is the trodden path: almost every Gryphon capability is a rung-1 feature (pure
ORM lowering — see Step 6) and follows exactly these six steps.

1. **Requirements-table row.** Add a row to the owning spec's `## Requirements`
   table — the `RID` (`req-grid-traversal-lang-<x>` for the language spec,
   `req-grid-gryphon-<x>` for the multihop-aggregation spec), a linked name, a
   `Status`, and a one-line Notes summary.

2. **The requirement section — match the owning spec's local conventions.** Do not
   invent a section the sibling requirements do not use. The multihop-aggregation
   spec uses `Implementation` / `Development` / `Acceptance Criteria` / `Future`.
   The language spec uses `Background` / `Implementation` / `Examples` /
   `Acceptance Criteria` / `Future`, sometimes with a `Status Details` subsection.
   Read a neighbouring requirement in the same file and mirror its shape.

3. **`Implementation`** states three things concretely: the grammar addition (the
   rule, in grammar syntax), the AST shape (the new dataclass(es)), and **which
   executor path the feature lands in and which lowering rung it uses**. State the
   rung explicitly *even when it is rung 1* — "lowers to rung 1: ORM `QuerySet`
   composition" is one sentence, and it turns the lowering choice into a reviewed,
   recorded fact rather than a silent default. Per `req-grid-traversal-exec-lowering`,
   rung 1 is the expectation; saying so out loud is the cheap half of keeping it the
   expectation.

4. **The scope rationale** — `Development` in the multihop-aggregation spec,
   `Background` in the language spec — explains *why the v0 scope is what it is*:
   what was deliberately left out, and what demand signal would pull it in. This is
   where Step 1's scoping decision is written down, so a future reader cannot mistake
   a deliberate omission for an oversight.

5. **`Acceptance Criteria`** — an ACID table with **one ACID per testable behavior,
   including every rejection case**. If the executor rejects an out-of-scope shape
   with an error (Step 6), there is an ACID for that rejection. The ACID table is
   what the Gridkin `covers` arrays and the `test_gryphon.py` tests trace back to.

6. **`Future`** — a bullet list naming **every** deferred shape, so the v0 boundary
   is legible. If the feature was previously a bullet under another requirement's
   `Future`, update that bullet to point at the new RID rather than leaving a
   now-stale "this is future work" note.

### When the feature needs a rung above 1

Most do not — rung 1 is the default and covers essentially every foreseeable
capability. But if Step 6 will lower to rung 2 or higher — a `Func`/`Expression`
subclass, a `RawSQL` fragment, a hand-written SQL template, a stored function — that
escalation is surfaced to the user *before* building (Step 6), and it puts extra
weight on this requirement:

- **State the rung and justify it in the spec text itself.** The requirement must say
  which rung the feature lowers to and why each lower rung cannot express the query.
  This justification is spec prose, not a PR comment — it is the durable record of an
  architectural decision.
- **Rung 4 (a hand-written SQL template):** document the per-construct lowering rule —
  which gryphon shape compiles to which SQL shape — so the emitted raw SQL is
  auditable from the spec, per the `req-grid-traversal-exec-lowering` Future note.
- **Rung 5 (a stored function):** the function is its own first-class tracked artifact
  and gets its **own** spec requirement plus a migration — it is not a footnote on the
  capability's requirement. Check the rung-5 preconditions in
  `req-grid-traversal-exec-lowering` (cross-query reuse, tracked-artifact management,
  explicit cost acceptance).
- Confirm the requirement records that the five rung invariants
  (`req-grid-traversal-exec-lowering`) still hold at the chosen rung.

### When the feature reconciles an existing requirement

Not every feature adds a new RID. A capability sometimes closes the gap on a
requirement that already *claims* the behavior — the executor was simply behind
the spec. The OR / NOT combinators feature is the worked example: the
capability-docs slice found that `req-grid-traversal-lang-combinators` was
`Implemented` and claimed AND / OR / NOT, but the executor ran only AND.

When that is the shape, Step 2 **updates the existing requirement** instead of
adding a Requirements-table row:

- Do not mint a new RID. Bring the requirement's Implementation prose and ACID
  statuses into line with what the feature now actually delivers — so the spec
  stops overclaiming.
- The capability block for the affordance is *updated*, not created — typically
  dropping a now-false `:limitations:` line (see Step 6).

The capability-docs gap report (`spec-sphinx-capability-docs.md`,
`req-sphinx-docs-gap-tracking`) is the clean way to surface these: a block whose
`:status:` / `:limitations:` disagree with its `:implements:` requirement is
exactly this case.

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

- **Lower to the lowest rung of the lowering ladder** (`req-grid-traversal-exec-lowering`
  in the execution spec) that expresses the query. The executor is rung 1 — ORM
  `QuerySet` composition — throughout, and staying there is the default and the
  expectation. Climbing (a `Func`/`Expression` subclass, `RawSQL`, a hand-written SQL
  template, a stored function) is a deliberate escalation, never a convenience: justify
  it in the spec requirement and the PR, and confirm the five rung invariants still hold
  at the new rung — read-only alias, bind-parameterized values, dimension scoping,
  canonical-envelope normalization, capture-seam visibility. If a feature appears to need
  a rung above 1, that is a design signal — surface it to the user before building it,
  do not quietly reach for raw SQL.
- Identify the dispatch path(s): the simple `_execute_ast` (type scan,
  hub-and-spoke, edge-type scan), the advanced `_execute_advanced` (multi-hop,
  NOT EXISTS, COUNT), or a new dedicated path. A genuinely new shape (e.g. OPTIONAL
  MATCH) gets its own `_execute_<feature>` and an early route in
  `execute_gryphon_raw`, wrapped in a `gryphon_stage("<label>")`.
- Apply the feature in **every** path that can reach it. ORDER BY / LIMIT had to
  land in both the type-scan projection and the aggregation path; a new predicate
  leaf must be handled in `_predicate_to_q` (the WHERE-tree-to-`Q` compiler),
  `_comparison_to_q`, `_flatten_conjunction` (the OPTIONAL MATCH AND-only split),
  and `_filter_predicate_for_bindings`, plus `_collect_params_from_predicate` in
  `ast_nodes.py`.
- **Reject out-of-scope shapes with a clear, actionable error** that names the
  supported form. Never silently ignore a clause.
- **Keep the emitted SQL deterministic.** Append a unique tiebreaker
  (`entity_id` / the group-by columns) to any `ORDER BY`; sort `pk__in` lists.
  Non-deterministic SQL makes the Gridkin snapshot flap.

### Capability block

A load-bearing affordance gets a `.. tap:capability::` block in a docstring at
its closest code anchor — per `spec-sphinx-capability-docs.md`
(`req-sphinx-docs-capability-blocks`). For a Gryphon feature:

- Author the block — or, for a reconciled requirement (Step 2), **update** the
  existing one — at the feature's anchor: the executor dispatch function, the
  AST node, whichever code site owns the claim.
- Carry the required metadata (`id`, `status`, `audience`, `affordance`,
  `implements`), a one-line affordance description, a worked `Example::` literal
  block, and a `:limitations:` line for any material caveat. Directive option
  values stay single-line within the 120-character limit.
- `covered-by` and the `Example::` query are sourced from the Gridkin scenario
  authored in Step 7 — fill them in once that scenario exists.
- A feature that reconciles an existing requirement updates that requirement's
  block: drop a now-false `:limitations:` line, refresh the body and example.
  The OR / NOT feature did exactly this to `cap-grid-gryphon-where`.

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
- **Climbing the lowering ladder when a lower rung expresses the query** — reaching for
  `RawSQL` or a hand-written SQL template where an ORM `QuerySet` or a `Func` subclass
  would do. Each rung up sheds an ORM-provided guarantee you must then re-earn by hand
  (`req-grid-traversal-exec-lowering`).
- **Copying TCK query text, data, or expecteds.** Inspire from the corner-case
  intent; re-author everything in TAP vocabulary.
- **A scenario file with no `covers` array** — the loader rejects it.
- **Shipping the executor change without the spec requirement and Gridkin
  scenarios in the same commit.**
