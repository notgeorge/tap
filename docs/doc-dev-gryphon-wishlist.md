---
spec: ../plugins/gryphon_playground/specs/spec-gridkin-v0.md
audience: [llm, developer]
covers:
  - ../tap_grid/specs/spec-grid-traversal-language.md
  - ../tap_grid/specs/spec-grid-traversal-execution.md
  - ../tap_grid/specs/spec-grid-gryphon-multihop-aggregation.md
  - ../plugins/gryphon_playground/specs/spec-gryphon-playground-v0.md
  - ../plugins/gryphon_playground/specs/spec-gridkin-v0.md
update-triggers:
  - A Gryphon feature in this wishlist moves from extract-ahead / wait-for-signal into the executor
  - The validation contract here diverges from what is actually being done in Gryphon work
  - A new demand signal surfaces that argues for promoting a future-seam item
  - openCypher publishes major TCK changes that materially affect the "TCK as inspiration" workflow
  - The three-lane envelope spec (spec-grift-envelope.md) moves Proposed → Implemented and changes envelope shape
assumes:
  - Reader is an LLM (likely me, or another agent) loading context before extending Gryphon
  - Reader will have skimmed `tap_grid/specs/spec-grid-traversal-language.md` and `spec-grid-traversal-execution.md` before reading this doc, so deep ORM/Django mechanics are not re-explained here
  - Reader understands "Gryphon over ORM" is a canonical project rule (`feedback_gryphon_over_orm` in agent memory)
provides: |
  An expansive, front-loaded view of what Gryphon needs to grow into to remain
  feature-adequate for Rampart-era demand, organized by demand-shape rather than
  by Cypher's table of contents. Includes the validation discipline that should
  accompany every Gryphon extension (Gridkin scenarios, oracle expecteds, explain
  SQL snapshots, requirement traceability, openCypher TCK as inspiration). The
  doc is intentionally verbose because the reader is an LLM and saving keystrokes
  buys nothing, while front-loaded context buys real downstream leverage.
---

# Gryphon Wishlist & Validation Strategy

Spec: [spec-gryphon-playground-v0.md](../plugins/gryphon_playground/specs/spec-gryphon-playground-v0.md) (plugin) and [spec-gridkin-v0.md](../plugins/gryphon_playground/specs/spec-gridkin-v0.md) (validation contract / format)
Underlying language spec: [spec-grid-traversal-language.md](../tap_grid/specs/spec-grid-traversal-language.md)
Underlying execution spec: [spec-grid-traversal-execution.md](../tap_grid/specs/spec-grid-traversal-execution.md)
Multi-hop / aggregation extensions: [spec-grid-gryphon-multihop-aggregation.md](../tap_grid/specs/spec-grid-gryphon-multihop-aggregation.md)

## Why This Doc Exists

Gryphon is the canonical read path for TAP-managed graph data. The "Gryphon over ORM" rule is embedded in the canonical spec and at the code-level break-glass: graph reads go through Gryphon; raw ORM querying and bespoke search modules are last-ditch only, and the urge to reach for them is itself a demand signal that Gryphon needs to grow. That status — *load-bearing system that everything graph-shaped routes through* — makes Gryphon's feature trajectory and its validation discipline disproportionately important to get right.

This doc serves two related purposes:

1. **A prioritized wishlist of Gryphon features**, organized by the *demand-shape* that pulls each one in (e.g. "dashboard panels need ORDER BY + LIMIT to be writable as a single query"), not by the structure of any one external language's feature list. The framing matters: Gryphon does not aim for Cypher compatibility. It aims for *coverage of TAP's demand surface*, with Cypher available as a reference for shapes that are likely useful and conventions that improve readability.

2. **A validation strategy for Gryphon work** — the discipline that every feature on the wishlist should ship under, captured here so that future-me (or another agent, or another contributor) has a single place to read the contract before extending the executor. The discipline crystallizes around a new test format called Gridkin (specced in [spec-gridkin-v0.md](../plugins/gryphon_playground/specs/spec-gridkin-v0.md)) and a new dedicated plugin called `gryphon_playground` (specced in [spec-gryphon-playground-v0.md](../plugins/gryphon_playground/specs/spec-gryphon-playground-v0.md)) that hosts the scenarios and their backing fixtures.

The doc is expansive on purpose. The primary reader is an LLM loading context before doing Gryphon work, and verbosity costs nothing while front-loaded rationale buys real downstream leverage (per `feedback_explicit_over_brevity_llm_era`). A human reader would do well to skim section headers; an LLM is expected to read end-to-end and use the rationale to make judgment calls on edge cases the doc doesn't enumerate.

## Implementation Status (2026-05-21)

The **validation-strategy** half of this doc is now built. As of 2026-05-21, on `session/gryphon-playground`:

- The Gridkin scenario format, its JSON Schema, and a pytest-discoverable runner are implemented in `plugins/gryphon_playground/` — specced by [spec-gryphon-playground-v0.md](../plugins/gryphon_playground/specs/spec-gryphon-playground-v0.md) and [spec-gridkin-v0.md](../plugins/gryphon_playground/specs/spec-gridkin-v0.md), whose requirements are now `Implemented` (bar the Tier-2 canonical fixture).
- The SQL-capture seam is implemented — `tap_grid/gryphon/capture.py`, `explain_gryphon_raw()`, and `req-grid-traversal-exec-sql-capture` in `spec-grid-traversal-execution.md`. The Gridkin expected-SQL snapshot and the future `gryphon explain` command (H3) now share this real infrastructure.
- A first scenario corpus exists and is green. Expanding it to validate the whole current executor surface is in progress.

The **feature-wishlist** half (buckets A–H below) is unchanged: still forward-looking, still demand-gated. Where a bucket's "how it touches the executor today" note is overtaken by events, this status note is the correction of record until the bucket text itself is revised.

## What's Deliberately Not In This Doc (In-Flight Elsewhere)

Three Gryphon-adjacent workstreams are actively in flight on other sessions or recently landed. Each is excluded from this wishlist:

- **Three-lane envelope shape** (`spec-grift-envelope.md`). Unifies node and edge response shapes under a top-level spine surface + a `data` lane (per-model fields) + a `display` lane (consumer-namespaced rendering hints). It has since landed in the subgraph serializer — the three-lane shape is what Gridkin scenarios assert against today. `spec-grift-envelope.md` is `In Development`, with acceptance criteria still settling; if its remaining ACIDs change the envelope shape, affected Gridkin expected envelopes regenerate as a coordinated change under the snapshot discipline.

- **BaseModel field reach** — extending Gryphon's predicate and projection surface to reach into typed BaseModel fields (not just Entity envelope fields). Recent in-development requirement `req-grid-traversal-lang-envelope-paths` in the language spec.

- **JSON nested-object search** — predicate access into nested JSON structures on JSONField columns. Closely related to `req-grid-traversal-lang-filters-jsonpath` (Proposed); intended to put Gryphon one-up on Cypher's flat property model.

If a future reader finds that one of these has landed since this doc was last touched, the wishlist may need a corresponding compaction — items that depended on these in-flight pieces become available to plan against, and corresponding wishlist text may overlap with delivered behavior.

## Stance on Cypher

Gryphon takes Cypher seriously as a reference but rejects compatibility as a goal.

**What we borrow from Cypher**: notation that improves readability (the `MATCH ... WHERE ... RETURN` clause structure; the `(node)-[edge]->(node)` pattern syntax; the `(:label)` typing; the `$param` runtime input convention; the read-only-by-default posture). The familiarity tax for an engineer who has used Neo4j or Memgraph is low, which matters when those are the engineers we want to be productive.

**What we deliberately diverge from**: Cypher's null semantics, Cypher's property-bag node model, Cypher's ~150 built-in functions, Cypher's mutation surface (CREATE/MERGE/SET/DELETE — Gryphon is read-only), Cypher's variable-length path semantics in their full generality, and Cypher's quirky type coercions. These divergences are not accidents; they reflect TAP's strict service-layer + typed-BaseModel data model and our preference for a small, predictable surface over a large familiar one.

**What we don't pre-commit to**: any specific subset of Cypher we claim to implement. Compatibility claims invite a maintenance burden (conformance kits, version tracking, edge-case parity) that is below the bar until external demand signals it (e.g. the eventual satellite system might want plugin authors to write portable queries).

The TCK — openCypher's Technology Compatibility Kit — *is* useful to us, but as a **scenario mine**, not a test suite to port. The hard-won knowledge in the TCK is "these corner cases historically broke real graph engines"; the queries themselves are downstream of that knowledge. The TCK-as-inspiration workflow is captured in detail under [Validation Contract for Gryphon Work](#validation-contract-for-gryphon-work) below and formally in `req-gridkin-tck-inspiration` of [spec-gridkin-v0.md](../plugins/gryphon_playground/specs/spec-gridkin-v0.md).

## Validation Posture: Why We're Investing Here Specifically

Gryphon is being authored largely by AI. The user (the one human in this loop) is reasonably uncomfortable with a load-bearing system being extended without him reading every line — and the audit done in conversation that produced this doc surfaced several quality-discipline gaps that justify the discomfort. The findings, in priority order:

1. **Almost every existing Gryphon test asserts on a derived fact, not against an independent oracle.** Tests look like: seed Frodo and the Ring, run the query, assert `count == 2`. Where did the `2` come from? From the same mental model that wrote the executor. A consistent JOIN-inflation bug — where the executor overcounts by exactly the same factor every time — would pass every current test. The tests prove internal consistency, not correctness.

2. **Roughly 38 of 65 spec requirements have no traceable test.** Most untraced requirements are language-surface (JSONPath syntax variants, parameter scoping, return variants) and the trace-gap is partly bookkeeping rather than coverage absence — but the bookkeeping absence means nobody can confidently audit which requirements are actually covered.

3. **The NOT EXISTS executor path has an explicit comment about "fix for multi-hop COUNT inflation" with no corresponding test that verifies inflation does not happen.** Of the existing tested-but-fragile execution paths, this is the most concerning — it's the one the executor author *noticed* could be wrong, but didn't pin down.

4. **Graph topology corners are absent from tests entirely**: cycles, self-loops, multi-edges between the same node pair, soft-deleted entities, NULL property values, dimension-scoped queries. Each one is a one-line graph change away from blowing up correctness silently.

5. **No HTTP-layer integration tests.** The `tap_api/routers/gryphon.py` endpoint has no end-to-end coverage. Bugs in envelope marshaling, layer parameter propagation, or error-to-HTTP-status mapping would not be caught by any current test.

6. **No way to see the SQL Gryphon emits without instrumenting the test.** This is a tooling gap — the executor compiles to Django ORM `QuerySet`s whose `.query` attribute holds the compiled SQL, but there's no developer-facing surface that exposes it. This particularly matters for the human-in-the-loop verifiability problem: a developer who wants to spot-check correctness without reading executor source has no leverage today.

The validation contract below addresses each of these gaps in proportion to its severity. Notably absent from the contract: building a Cypher-style differential-testing harness, generating random queries via sqlsmith-style tooling, or building a full performance benchmark suite. Those are powerful techniques used by mature query-engine teams (SQLite, PostgreSQL, DuckDB) but are premature for the solo dog-food window TAP is currently in (per `project_solo_dogfood_window`). They are named as [Future Seams](#future-seams-appendix) so we don't reinvent them by accident later.

## Wishlist: Features Organized by Demand-Shape

Each bucket below collects features that get pulled in by the same kind of demand — table-panel demand, predicate-power demand, dashboard-summary demand, etc. The buckets are deliberately not "Cypher clauses" because that framing produces a feature list whose priorities are set by Cypher's evolution, not TAP's.

Each item carries:

- **What** — what the feature looks like in Gryphon syntax (with one or two short examples)
- **Why we'd want it** — the demand-shape rationale; what makes it hurt to be without
- **What pulls it in** — the concrete demand signal that would promote it from "future" to "now": which Rampart roadmap step, which panel type, which kind of dashboard query
- **How it touches the executor today** — which existing dispatch branch or scaffolding it builds on; what's already half-built
- **Status flag** — `extract-ahead` (recommended to ship before specific demand because the shape is shared by many anticipated queries), `wait-for-signal` (the value is real but committing engineering now is premature), or `future-seam` (named for vocabulary consistency; building deferred until demand)
- **Validation contract size** — a rough sense of how many Gridkin scenarios and fixtures the feature would require, to help with sequencing

### Bucket A — Table & Panel Ergonomics

The pull here is from `tap_web` panel demand, not from Cypher envy. Pagination, sorting, and limiting are wrapped *outside* Gryphon today (in the Search service layer). That worked when every query produced a graph envelope to render in Cytoscape, but breaks down as table panels (`panel-table.js`) become the dominant view shape for compliance dashboards, KSI scoreboards, and finding lists. A table panel that shows the top 20 failing controls cannot construct that result without `ORDER BY` and `LIMIT` inside the query — outside-the-query pagination over an unsorted result is incoherent.

#### A1. `ORDER BY`

**What.** `RETURN entity, COUNT(finding) AS findings ORDER BY findings DESC`. Order rows in the result envelope (or graph envelope, with consistent node order) by one or more projected columns, ascending or descending.

**Why we'd want it.** Without it, the order of rows in any Gryphon response is implementation-defined (whatever the ORM produced). Table panels paging across results need stable, defined ordering. Aggregation results without ordering are useless ("top N" is the most common dashboard verb).

**What pulls it in.** The first table-panel-driven dashboard. KSI scoreboard, finding lists, compliance status tables — all wait on this.

**How it touches the executor today.** Maps to Django ORM `.order_by(...)`. Cleanly. The compiler's `_apply_aggregation` and `_apply_projection` stages would gain an order-by stage between projection and final materialization.

**Status flag.** `extract-ahead` — heavily anticipated, low cost, no half-built scaffolding to worry about. Worth shipping before the first table-panel dashboard demands it.

**Validation contract size.** ~3-5 Gridkin scenarios. One fixture (`sparse_dense.grift.json`). Corners: stable ordering with ties, ordering by aggregated column, ordering by projected expression, ordering across multiple columns, descending vs. ascending.

#### A2. `LIMIT`

**What.** `RETURN entity ORDER BY entity.name LIMIT 20`. Cap the number of rows returned.

**Why we'd want it.** Same demand source as `ORDER BY`. Today the Search service wraps Gryphon with an external limit, but that's a hack — the ORM ends up materializing all matching rows and then slicing in Python, which is the opposite of what `LIMIT` exists for. In-query `LIMIT` translates to SQL `LIMIT` and lets the database short-circuit.

**What pulls it in.** Same as `ORDER BY` — table panels, "top N" queries. Also useful for the `gryphon explain` demo surface where a developer wants to see a small representative sample of a large query result.

**How it touches the executor today.** Django ORM slicing — `qs[:N]` compiles to SQL `LIMIT`. Trivial wiring.

**Status flag.** `extract-ahead`. Pair with `ORDER BY`.

**Validation contract size.** ~2-3 Gridkin scenarios. Corners: LIMIT with and without ORDER BY (the latter explicitly documents the ordering is undefined), LIMIT 0, LIMIT larger than result set.

#### A3. `SKIP` / `OFFSET`

**What.** `RETURN entity ORDER BY entity.name SKIP 20 LIMIT 20`. Skip the first N rows.

**Why we'd want it.** Pagination at the query level for table panels. Today the Search service wraps with an outer offset; same Python-slicing issue as LIMIT.

**What pulls it in.** A multi-page table panel.

**How it touches the executor today.** Same path as LIMIT (Django ORM slicing).

**Status flag.** `extract-ahead`, but lower priority than ORDER BY + LIMIT — single-page table panels are useful well before multi-page ones become a need.

**Validation contract size.** ~2 Gridkin scenarios. Corners: SKIP beyond the result set, SKIP without ORDER BY (documented undefined behavior).

#### A4. `DISTINCT`

**What.** `RETURN DISTINCT entity_type`. Deduplicate rows.

**Why we'd want it.** Common verb in summary queries: "what distinct entity types do we have in this dimension?" Today expressible with COUNT and implicit GROUP BY, but `DISTINCT` is the readable form and is what people reach for.

**What pulls it in.** Summary tiles, filter dropdowns ("which dimensions exist?"), any "what kinds of X do we have" query.

**How it touches the executor today.** Django ORM `.distinct()`. Composes cleanly with aggregation.

**Status flag.** `extract-ahead`, paired with the rest of bucket A.

**Validation contract size.** ~2 Gridkin scenarios.

### Bucket B — Predicate Power

The pull here is from dashboard filter intent. A panel that lets a user say "show me only the aws_lambda *and* aws_ec2_instance entities tagged with environment=prod *or* environment=staging" produces a Gryphon query whose `WHERE` clause needs more than equality and AND/OR/NOT over single-step field paths.

Today's predicate surface supports `=`, `!=`, `<`, `>`, `<=`, `>=`, `AND`, `OR`, `NOT` over single-dot-step field paths plus single-level JSON bracket access (`node.tags["env"]`). That's a useful core. The gaps below are the predicate vocabulary that dashboard filters routinely demand.

#### B1. `IN` lists

**What.** `WHERE n.entity_type IN ['aws_lambda', 'aws_ec2_instance']`. Match against a list of values.

**Why we'd want it.** The single most common shape of dashboard filter ("type is X or Y or Z") is currently written as `n.entity_type = $a OR n.entity_type = $b OR n.entity_type = $c`, which scales poorly past two values and is awkward for parameterization (a filter that lets the user pick any subset of N options can't be expressed without query rewriting).

**What pulls it in.** Any multi-value filter on a categorical field. Samsite's landing-page panel already filters by `entity_type__startswith='aws_'` — once any panel filters by an explicit subset of types, this lands.

**How it touches the executor today.** Django ORM `__in=[...]`. Direct map.

**Status flag.** `extract-ahead`. Heavy demand, low cost.

**Validation contract size.** ~3-4 Gridkin scenarios. Corners: empty list, list with one element, list with NULL (does Gryphon match NULL membership? Per our null semantics, this should be a defined choice and Gridkin pins it).

#### B2. `STARTS_WITH` / `ENDS_WITH` / `CONTAINS`

**What.** `WHERE n.entity_type STARTS_WITH 'aws_'`. Substring matching on string fields.

**Why we'd want it.** Samsite's current ORM-based search uses `entity_type__startswith='aws_'` directly. The fact that we needed to reach for the ORM there is the Gryphon-over-ORM rule firing — a demand signal that Gryphon should grow this predicate. Useful broadly for type-prefix filters, name searches in finders, log-grep-style dashboard search boxes.

**What pulls it in.** Already pulled in by samsite's current pass-1 ORM query, but the demand signal hasn't been formalized into a feature pull yet — samsite is deliberately pass-1 and unfiltered. When a samsite-style dashboard wants user-typed search, this is the predicate.

**How it touches the executor today.** Django ORM `__startswith`, `__endswith`, `__contains`. Direct map. Case sensitivity is a design choice — Cypher has both `STARTS WITH` (case-sensitive) and `STARTS WITH ... CASE INSENSITIVE` (Memgraph extension); Gridkin scenarios should pin which we choose.

**Status flag.** `extract-ahead`. The demand signal is already detected.

**Validation contract size.** ~4-5 Gridkin scenarios. Corners: case sensitivity, empty needle, special characters in needle (regex-like characters in non-regex predicate).

#### B3. `IS NULL` / `IS NOT NULL`

**What.** `WHERE n.deleted_at IS NULL`, `WHERE n.description IS NOT NULL`.

**Why we'd want it.** Becomes important once the BaseModel reach work (in flight on another session) lands, because many BaseModel fields are nullable. Also useful for soft-delete-aware queries (`WHERE n.deleted_at IS NULL` is the standard "live entities only" filter).

**What pulls it in.** The BaseModel reach landing. After that, every dashboard that queries typed model fields will benefit.

**How it touches the executor today.** Django ORM `__isnull=True/False`. Direct map.

**Status flag.** `extract-ahead`, but probably ordered after the BaseModel reach lands so the demand signal is concrete.

**Validation contract size.** ~3 Gridkin scenarios. Tied to soft-delete corner cases in `fixtures/soft_deletes.grift.json`.

#### B4. Label-union node patterns: `(n:type1|type2)`

**What.** `MATCH (n:aws_lambda|aws_ec2_instance)`. A node pattern that matches if any of the listed labels apply.

**Why we'd want it.** Polymorphic queries — "anything that runs compute" includes Lambdas, EC2, ECS tasks. Today this is written as multiple MATCH clauses (which already UNION) or as `WHERE n.entity_type IN [...]`, both of which separate the label-typing from the pattern, hurting readability and indexing.

**What pulls it in.** Polymorphic dashboards. "Show all compute resources and their findings" needs this.

**How it touches the executor today.** Multi-MATCH-with-UNION semantics already exist; this is sugar for that pattern with the difference that the union is at the pattern level (single QuerySet with `__in` on entity_type) rather than the result level (multiple QuerySets unioned).

**Status flag.** `extract-ahead`. Polymorphism is real and recurring.

**Validation contract size.** ~3 Gridkin scenarios. Corners: union of two types, union of three types, union with a label that has zero entities in the fixture.

### Bucket C — Aggregation Beyond `COUNT`

Today Gryphon supports `COUNT(...)` with implicit GROUP BY. That's the entry-level aggregate. The pull for additional aggregates comes from compliance and KSI scoreboards: "average remediation time per resource type," "max severity per resource," "total cost-impact per finding category," "the list of finding IDs per resource so the panel can drill in without a second query."

#### C1. `SUM` / `MIN` / `MAX` / `AVG`

**What.** `RETURN resource, SUM(finding.cost_impact) AS impact ORDER BY impact DESC LIMIT 10`. Standard numeric aggregates.

**Why we'd want it.** The "top N by some quantitative score" query shape is core to dashboards. Without these, every quantitative summary becomes a multi-pass: Gryphon returns the rows, Python sums them. That defeats most of Gryphon-over-ORM's value.

**What pulls it in.** The KSI scoreboard (sum of weighted findings per resource); any cost or risk roll-up panel; first paid assessment's "tell me what to fix first" view.

**How it touches the executor today.** Maps to Django ORM `Sum/Min/Max/Avg` annotation. The existing aggregation path in `_compute_rows` already handles `Count`; extending to the other aggregates is parallel work, not a new dispatch path.

**Status flag.** `extract-ahead` once the BaseModel reach lands (because these aggregates apply to typed numeric fields, which today aren't reachable from Gryphon predicates). Until then, `wait-for-signal`.

**Validation contract size.** ~5-6 Gridkin scenarios (one per aggregate, plus interaction with GROUP BY, plus NULL handling).

#### C2. `COLLECT`

**What.** `RETURN resource, COLLECT(finding.entity_id) AS findings`. Collect the values of the aggregated column into a list, one list per group.

**Why we'd want it.** Massive N+1 defeater. A panel that shows "each resource with its findings" today either runs N queries (one per resource) or runs one query and reassembles in Python. `COLLECT` lets the SQL do the grouping and the Python code receives `{resource: [finding_ids]}` directly.

**What pulls it in.** Any drilldown panel where the parent row needs to know its children's IDs to construct expand-handlers. Common in tap_web table panels.

**How it touches the executor today.** Django ORM `ArrayAgg` (PostgreSQL-specific, which we are). Maps cleanly; preserves order via `ordering=...` argument.

**Status flag.** `extract-ahead`. Distinct from the numeric aggregates because it has different downstream consumers and unlocks UI shapes that don't yet exist.

**Validation contract size.** ~4 Gridkin scenarios. Corners: empty collect (group with zero rows), ordering inside the collected list, distinct vs. non-distinct collection.

#### C3. Post-aggregate filtering (`HAVING`-equivalent)

**What.** `RETURN resource, COUNT(finding) AS f WHERE f > 5 ORDER BY f DESC`. Filter on aggregated columns.

**Why we'd want it.** "Show resources with at least N findings" is a common scoreboard shape. Today expressible by post-Python-filtering, which leaks aggregation results into the application layer.

**What pulls it in.** Threshold-driven dashboards ("which resources have more than X findings?"). Comes naturally with bucket A's table-panel demand.

**How it touches the executor today.** Two implementation choices: (a) a literal `HAVING` keyword, which parallels SQL semantics, or (b) the `WITH` clause from bucket F, where post-aggregate filtering is expressed as a pipelined `WHERE` after the aggregate. Cypher chose (b) — `WITH` subsumes `HAVING`. We probably should too, because the broader pipelining value of `WITH` exceeds the narrower value of `HAVING`. **See bucket F1.**

**Status flag.** Folded into `WITH` (F1). Don't ship as a separate feature.

**Validation contract size.** Subsumed by F1.

### Bucket D — Outer-Join Shapes

This is the bucket where the headline missing feature lives. The single most under-served query shape in current Gryphon is "show me every X, and *if* it has a related Y show me that too" — the left-outer-join shape. Without it, every dashboard that wants to surface entities-with-and-without-related-things becomes a UNION of two queries (one with the relationship, one with `NOT EXISTS` for the absence), which is unwieldy and impossible to aggregate cleanly.

#### D1. `OPTIONAL MATCH` 🌟

**What.**

```
MATCH (l:aws_lambda)
OPTIONAL MATCH (l)-[:HAS_FINDING]->(f:finding)
RETURN l, COUNT(f) AS findings
```

A second MATCH pattern that, if it doesn't bind, leaves its variables as NULL rather than dropping the row.

**Why we'd want it.** This is the load-bearing missing primitive for compliance dashboards. The worked example from conversation: "show me every aws_lambda and how many findings each has." Written with regular MATCH:

```
MATCH (l:aws_lambda)-[:HAS_FINDING]->(f:finding)
RETURN l, COUNT(f) AS findings
```

This silently drops every Lambda with zero findings. The clean Lambdas vanish from the scoreboard — exactly the opposite of what a scoreboard should do.

With OPTIONAL MATCH, every Lambda appears; `f` is NULL where there's no finding; `COUNT(f)` correctly returns 0 (because COUNT ignores NULLs — the one place Cypher's null semantics actually help).

Generalize: every "per-entity score" panel — KSI scoreboard, "resources with their compliance status," "Lambdas and their attached role (where the role might not be attached)" — has this shape. Without OPTIONAL MATCH, every such query becomes a UNION ("entities with finding" UNION "entities without finding"), which is awkward to write and impossible to aggregate over cleanly.

**What pulls it in.** Already pulled in by the first compliance dashboard, the KSI scoreboard, and effectively every Rampart-step demand. The single biggest extract-ahead win in this entire wishlist.

**How it touches the executor today.** Maps to a `LEFT OUTER JOIN` in the ORM-compiled SQL. The multi-hop join composer in `tap_grid/gryphon/executor.py` already builds joins; OPTIONAL MATCH is a per-hop flag (left-outer instead of inner) plus a NULL-aware result projection. It's not a new execution path; it's an annotation on the existing one.

**Status flag.** `extract-ahead` 🌟 — the highest-priority extract-ahead item in the entire wishlist.

**Validation contract size.** ~6-8 Gridkin scenarios. Corners explicitly mined from the openCypher TCK's `tck/features/clauses/optional-match/` folder. Likely intents to cover (subject to the TCK pass): basic optional pattern doesn't drop rows, OPTIONAL MATCH after MATCH inherits prior bindings, OPTIONAL MATCH inside a chain, OPTIONAL MATCH with WHERE inside vs. outside (a notorious Cypher gotcha — `OPTIONAL MATCH (a)-[r]->(b) WHERE b.x = 1` and `OPTIONAL MATCH (a)-[r]->(b) WHERE r.x = 1` behave differently depending on filter placement), COUNT over optional matches returning 0 not NULL, chained OPTIONAL MATCH where the second optional depends on the first.

#### D2. Positive `EXISTS { ... }`

**What.** `WHERE EXISTS { MATCH (n)-[:HAS_FINDING]->(f) WHERE f.severity = 'critical' }`. Mirror of the existing `NOT EXISTS` clause, for positive presence tests.

**Why we'd want it.** Symmetric to NOT EXISTS, which Gryphon already supports. The asymmetry today is uncomfortable — you can express "X has no Y" but the natural opposite "X has at least one Y" requires either an existing MATCH that may inflate row counts or a NOT NOT EXISTS workaround.

**What pulls it in.** Any "show only entities with at least one of X" filter. Common in compliance contexts — "show me only the resources that have an active finding."

**How it touches the executor today.** Mirror of the existing NOT EXISTS path. The correlated-subquery infrastructure is already in place; positive EXISTS is the same machinery with a sign flip.

**Status flag.** `extract-ahead`. Cheap to add given NOT EXISTS exists, valuable for vocabulary symmetry.

**Validation contract size.** ~3-4 Gridkin scenarios. Most TCK scenarios for positive EXISTS will translate intent cleanly.

### Bucket E — Reachability & Topology

The pull here is from Sam-demo-style zoom and from "blast radius" dashboards: "show me everything reachable from this account," "what depends on this role," "which resources can route traffic to this S3 bucket via any path of length up to 3." These are graph queries in the most graph-flavored sense — they're not really expressible in row-relational terms without ugly recursion.

#### E1. Variable-length paths `-[:EDGE*1..3]->`

**What.** `MATCH (a:aws_account)-[:CONTAINS*1..3]->(r) RETURN r`. Match a path of between 1 and 3 hops along the given edge type.

**Why we'd want it.** "Blast radius from this entity" is a classic graph query. Without variable-length paths, expressing "anything reachable in 1-3 hops" requires manually unrolling: `MATCH (a)-[:CONTAINS]->(r) RETURN r UNION MATCH (a)-[:CONTAINS]->(x)-[:CONTAINS]->(r) ...`. The unrolling gets worse the deeper you go and is impossible without an explicit upper bound. Hosted graph engines support this natively because it's the dominant graph-flavored use case.

**What pulls it in.** The Sam-demo "click to see reachability" interaction. Any dashboard that asks "what's affected if X breaks?". The "blast radius" mind-blower in the Rampart roadmap explicitly cites this shape.

**How it touches the executor today.** The grammar *already parses* `-[*1..3]->` syntax — this work is half-done at the grammar level. The executor explicitly rejects it. The implementation would compile to a recursive Common Table Expression (CTE) in PostgreSQL (`WITH RECURSIVE`). This is the heaviest engineering item in the wishlist by a meaningful margin; CTE composition with the existing JOIN-based executor is a real planner-level change, not a hop-level annotation.

**Status flag.** `wait-for-signal`. The user has explicitly stated they're waiting for a demand signal here — the parser scaffolding is half-done by design (it parses to indicate the language anticipates the feature; it rejects to surface the absence). When the first dashboard demand for reachability lands, the half-done grammar is the foothold; until then, holding.

**Validation contract size.** ~10-12 Gridkin scenarios (when promoted). Cycles, bounded vs. unbounded depth, zero-length matches, multi-edge interactions, performance behavior on deep graphs. The TCK has substantial coverage here under `tck/features/expressions/path/` and `tck/features/patterns/variable-length-paths/`.

#### E2. Path variables + path functions

**What.** `MATCH p = (a:aws_account)-[:CONTAINS*]->(r) RETURN length(p), nodes(p), relationships(p)`. Bind a path to a variable; functions to decompose paths.

**Why we'd want it.** Goes hand-in-hand with E1 — once you can express variable-length paths, you usually want to ask things *about* the path (how long? what nodes are on it? what edge types?). The grammar already supports binding `p =` at the pattern level; the executor rejects it.

**What pulls it in.** Same as E1 — usually demanded together. Drill-down UIs that want to render the path between two entities want `nodes(p)` and `relationships(p)`.

**How it touches the executor today.** Tied to E1's implementation. Path functions are additions to the projection surface that read the executor's internal path representation.

**Status flag.** `wait-for-signal`, paired with E1.

**Validation contract size.** ~4-5 Gridkin scenarios on top of E1's fixtures.

#### E3. `shortestPath((a)-[*]-(b))` and related

**What.** Cypher's syntax for shortest-path queries.

**Why we'd want it.** Less common than variable-length paths but specific shapes demand it (least-cost route between two services; closest compliance ancestor).

**What pulls it in.** Probably not until well after E1 lands and we have demand experience with reachability queries.

**How it touches the executor today.** Substantial — Postgres recursive CTE doesn't natively express shortest-path; would likely require a different execution strategy (multi-pass with cost tracking, or a dedicated graph extension if/when we add one).

**Status flag.** `future-seam`. Named so we don't reinvent the syntax. Hold until well after E1 has been in production for a while.

**Validation contract size.** Substantial when promoted; not estimated here.

### Bucket F — Pipeline / Composition

This bucket is where the second headline missing feature lives. Once we have aggregation beyond COUNT (bucket C) and outer joins (bucket D), the lack of pipelining becomes the binding constraint. Cypher's `WITH` is the keystone — it's the operator that lets you express "do this query, then filter on the result, then do another query."

#### F1. `WITH` 🌟

**What.**

```
MATCH (l:aws_lambda)
OPTIONAL MATCH (l)-[:HAS_FINDING]->(f:finding)
WITH l, COUNT(f) AS findings
WHERE findings > 0
RETURN l, findings
ORDER BY findings DESC
```

A pipeline operator. The output rows of one stage become the input scope of the next. The variables listed after `WITH` are the only ones visible downstream — earlier bindings get dropped.

**Why we'd want it.** Two jobs `WITH` does and nothing else does:

1. **Filter or transform after aggregation.** Today you can compute `COUNT(f) AS findings` but not say "and only keep groups where findings > 5" — you've already exited the query. `WITH` lets the count happen, then `WHERE` filters the post-count rows. (Subsumes the `HAVING`-equivalent from bucket C3.)

2. **Narrow scope between stages.** The variables you list after `WITH` are the *only* ones visible downstream. Useful for "find the top-N hubs, then traverse from just those":

   ```
   MATCH (a:aws_account)-[:CONTAINS]->(r)
   WITH a, COUNT(r) AS resource_count
   ORDER BY resource_count DESC
   LIMIT 5
   MATCH (a)-[:CONTAINS]->(top_r)
   RETURN a, top_r
   ```

   Two passes, but the second pass only runs for the top 5 accounts. Without `WITH`, this requires running the full traversal then post-filtering in Python, which loses the cost benefit entirely.

Once OPTIONAL MATCH and the additional aggregates are in, the lack of WITH is the next pain point. Any query that wants to "compute, filter, then traverse again" or "compute, then sort+limit, then continue" runs into the wall.

**What pulls it in.** Effectively pulled in by bucket C and bucket D landing — every advanced dashboard query becomes WITH-shaped.

**How it touches the executor today.** This is the heaviest planner-level change in the wishlist after E1/variable-length. The executor today compiles to a single Django QuerySet. `WITH` is a query-stage boundary: each `WITH` is a checkpoint where intermediate results need to exist as rows (in memory, in a CTE, or in a temp table). The executor moves from "compile one ORM query" to "compile a pipeline of stages with intermediate materialization." This is why naming it early matters — the seam needs to be visible in the planner before too much downstream code assumes single-query compilation.

**Status flag.** `extract-ahead` 🌟 — second-highest-priority extract-ahead item, after OPTIONAL MATCH. Worth designing the planner with WITH in mind even if we ship single-stage queries only at first; the planner shape change is what hurts to retrofit.

**Validation contract size.** ~8-10 Gridkin scenarios. Corners explicitly mined from `tck/features/clauses/with/`. Variable scope across stages, scoping by alias rename, multi-WITH chains, WITH followed by OPTIONAL MATCH, aggregation followed by WITH followed by aggregation.

#### F2. Explicit `UNION` / `UNION ALL`

**What.** `MATCH (a) WHERE ... RETURN a UNION MATCH (b) WHERE ... RETURN b`. Combine results of two queries.

**Why we'd want it.** Today, multiple `MATCH` clauses in the same query produce an implicit UNION at the result-envelope level (with entity_id deduplication). That's useful as far as it goes, but it conflates two patterns: "match these things and also those things" (truly union) and "match this complex pattern that has alternative shapes" (the implicit-union surface). Explicit UNION lets the latter be expressed unambiguously and lets UNION ALL (no dedup) be expressed at all.

**What pulls it in.** Compound dashboard queries with structurally different sub-queries.

**How it touches the executor today.** Compose two existing-shape queries; union the results. The dedup vs. ALL choice is a known SQL pattern.

**Status flag.** `wait-for-signal`. The implicit-union via multiple MATCH clauses is sufficient for current demand. Promote when an actual case requires explicit UNION semantics.

**Validation contract size.** ~3-4 Gridkin scenarios.

#### F3. `UNWIND`

**What.** `UNWIND $entity_ids AS id MATCH (n) WHERE n.entity_id = id RETURN n`. Iterate over a parameter list.

**Why we'd want it.** Lets parameters carry lists in a structured way. Today a parameter is a scalar; passing a list requires writing the query as `WHERE n.entity_id IN $ids`. UNWIND is more general — it can drive subsequent MATCH bindings as if the loop were unrolled.

**What pulls it in.** Batch query patterns where the application has a list of entities and wants to run a structured per-entity query in one call. Possibly tap_ai or batch tooling.

**How it touches the executor today.** Compiles to UNION over the unrolled list or to a join against a literal-rows VALUES expression.

**Status flag.** `wait-for-signal`. The current `IN`-list shape (once B1 lands) covers most demand; UNWIND is for when IN-list is insufficient.

**Validation contract size.** ~3 Gridkin scenarios when promoted.

### Bucket G — Edge-Side Parity

Today's Gryphon supports inline edge property filters (`-[e {cost: 5}]->`) but edge properties cannot appear in `WHERE` clauses or `RETURN` projections. This is an asymmetry between node and edge handling — for nodes, properties are first-class everywhere; for edges, they're first-class only in the inline pattern. The pull comes from edges that carry meaningful state (cost, type, weight, timestamp) that dashboards want to filter and project on.

#### G1. Edge properties in `WHERE`

**What.** `MATCH (a)-[e:DEPENDS_ON]->(b) WHERE e.criticality = 'high' RETURN a, b`. Reference an edge variable's properties in WHERE predicates the same way as node properties.

**Why we'd want it.** Inline filtering on edges works (`(a)-[e:DEPENDS_ON {criticality: 'high'}]->(b)`) but is awkward for more complex predicates (ranges, NULL checks, combinators). WHERE is where complex predicates live for nodes — edges should be symmetric.

**What pulls it in.** The first edge type that carries meaningful property state beyond the few used today. AWS edges (`DEPENDS_ON`, `PROTECTS`, `ROUTES_TRAFFIC`) plausibly grow properties; finding-to-evidence edges might carry confidence or timestamps.

**How it touches the executor today.** Existing predicate-resolution path for nodes — the field-path resolver needs to dispatch to edge variables, which means tracking edge-variable bindings (today the executor binds edges but doesn't resolve edge fields in WHERE).

**Status flag.** `extract-ahead`, low priority within the bucket. The mechanism is small but it's symmetry, not headline value.

**Validation contract size.** ~3 Gridkin scenarios. Pair with G2.

#### G2. Edge properties in `RETURN`

**What.** `MATCH (a)-[e:DEPENDS_ON]->(b) RETURN a, e.criticality, b`. Project edge properties as scalar output columns.

**Why we'd want it.** Symmetric to G1. Today edges are returned as full envelope objects only; you cannot project a single property of an edge into a row column. A table panel that wants "from, edge-type, criticality, to" as columns can't get there from here.

**What pulls it in.** Edge-centric table panels — "show me the dependencies and their criticality."

**How it touches the executor today.** Same field-path-resolution work as G1, plus extending the projection surface to handle edge field paths.

**Status flag.** `extract-ahead`, paired with G1.

**Validation contract size.** Subsumed under G1's scenarios — same fixtures, similar corners.

### Bucket H — Future Seams

Items in this bucket are named to keep the language's vocabulary internally consistent and to prevent us from reinventing them by accident later. None are built in v0; each is held until a demand signal arrives.

#### H1. `CASE WHEN ... THEN ... END` / `COALESCE(a, b)`

Conditional expressions for derived columns. Useful for synthesizing classification fields in RETURN projections ("CASE WHEN findings > 10 THEN 'critical' WHEN findings > 5 THEN 'high' ELSE 'normal' END"). Status: `future-seam`. Promotable once a dashboard demand wants in-query classification.

#### H2. String / numeric / list functions

Cypher has ~150 built-in functions. We don't and don't aim to. When demand surfaces for a specific function (`UPPER`, `SUBSTRING`, `SIZE`, `ROUND`), it lands as a one-off extension. Building a function library ahead of demand is a textbook over-engineering trap. Status: `future-seam`, with the explicit posture of "one function at a time, by demand signal."

#### H3. `gryphon explain` developer surface

**What.** A CLI / Django management command (and possibly an API endpoint) that takes a Gryphon query and returns the ORM-compiled SQL the executor would emit. No execution.

**Why we'd want it.** Already named in the validation contract below as the eyeball-friendly correctness check. Lifted here separately because it's a *feature* of Gryphon's developer ergonomics, not just a test artifact. A developer building a panel can paste a Gryphon query, see the SQL it would emit against the canonical playground graph, and judge whether the plan looks reasonable before writing a test.

Status: `extract-ahead`, partially landed. The shared capture infrastructure now exists — `tap_grid/gryphon/capture.py` (`capture_sql`, `explain_gryphon_raw`, `req-grid-traversal-exec-sql-capture`), which already backs the Gridkin SQL-snapshot. What remains for H3 is the developer-facing CLI / management command. One correction to *What* above: the "No execution" goal is not literally reachable — a multi-stage query builds each stage from the prior stage's results, so the capture runs *during* execution; against the small playground graph this is immaterial.

#### H4. Default values for `$params`

**What.** Parameters with a fallback default if not supplied at execute time.

**Why.** Quality-of-life. Common parameters (`$dimension`, `$layer`) often have a sensible default. Today every required parameter must be supplied or the query fails to load.

Status: `future-seam`. Low priority; current behavior is acceptable.

#### H5. Result-layer hint in the query

**What.** Express "give me the lite envelope" / "extended envelope" inside the Gryphon query, rather than as a parameter to the API surface.

**Why.** Cleaner caller surface; the query expresses its own envelope intent. Today the layer is a parameter to `execute_gryphon(..., layer="full")`.

Status: `future-seam`. Holds until envelope spec moves to Implemented and the layer mechanic stabilizes.

#### H6. Explicit cross-dimension queries

**What.** Syntax for "search across dimensions" rather than today's implicit dimension scoping.

**Why.** Today, dimension is implicit (queries operate within the caller's dimension context). Explicit cross-dimension queries would let dashboards aggregate across dimension partitions — useful for multi-tenant-aware admin views.

Status: `future-seam`. Big design question wrapped in a small syntax — defer until the dimension model itself stabilizes.

#### H7. `NOT EXISTS` correctness audit

**What.** Targeted audit of the existing NOT EXISTS executor path. The path carries an explicit comment about "fix for multi-hop COUNT inflation" with no corresponding test that verifies inflation does not happen. The audit would author Gridkin scenarios that explicitly exercise inflation-prone shapes (multi-hop outer, multi-hop inner, shared variable correlations across hop counts) and pin down behavior.

**Why.** This is the one place in Gryphon's current implementation where the executor author explicitly noticed a potential bug and patched it without a test. That's higher risk than untested-but-not-flagged behavior.

Status: `wait-for-signal`, with the signal being any movement that touches NOT EXISTS executor code. When that happens, the audit goes first.

## Validation Contract for Gryphon Work

Every Gryphon feature that lands ships under the following contract. The contract exists because the audit findings above documented gaps that, left unaddressed, will compound as the executor surface grows. The contract is calibrated to TAP's solo dog-food window (per `project_solo_dogfood_window`) — it is not the validation surface a mature query-engine team would invest in (no SQLancer, no sqlsmith, no differential testing against another engine), but it is the bar below which a Gryphon feature should not be considered shippable.

### 1. Gridkin scenarios are authored alongside the feature

Every new Gryphon feature ships with Gridkin scenarios in `plugins/gryphon_playground/scenarios/`. The scenarios are not a follow-up commit; they are part of the same change that lands the executor work. The format and runner are specified in [spec-gridkin-v0.md](../plugins/gryphon_playground/specs/spec-gridkin-v0.md).

The scenarios use TAP's playground vocabulary (`pg_*` node types, `PG_*` edge types) — never real domain models. This keeps the test surface decoupled from real-world graph evolution.

### 2. Two-tier fixtures

Scenarios load from Tier 1 fixtures — small, shape-targeted GRIFT files that each seed one topology corner (cycles, self-loops, multi-edges, sparse/dense, soft-deletes, polymorphic typing, nested compounds, optional relations, dimension partitions, JSON-rich payloads). The list is opinionated and growable: when a new feature reveals a topology corner that no Tier 1 fixture covers, the same change adds the fixture.

Tier 2 — a single canonical playground fixture combining representative samples from every shape — is the demo / tutorial / `gryphon explain` graph. It is *not* used by scenario assertions; that separation lets the playground evolve for clarity without breaking tests.

### 3. Oracle assertion discipline

Expected envelopes and expected SQL snapshots are *oracles*, not derivations. The author writes (or independently computes via raw ORM, or hand-enumerates) the expected result *before* observing the implementation's output for new scenarios. When implementation and expected disagree, the implementation is not assumed correct; both are reviewed.

The canonical anti-pattern (do not do this): run the implementation, capture its output, commit the output as the expected. That technique catches regressions but cannot catch systematic bugs the implementation already has — a consistent COUNT inflation by a factor of 2 produces consistent expecteds that all pass on rerun.

The discipline is enforced workflow-side (we do it because we know why) more than runtime-side (no automated lint catches violations).

### 4. Explain SQL snapshot per scenario

Each Gridkin scenario commits the exact ORM-compiled SQL the Gryphon executor produces for its query, whitespace-normalized, in a side file alongside the expected envelope. The runner asserts the SQL match as a *distinct failure mode* from envelope mismatch.

The value of this is twofold:

- **Eyeball-friendly correctness.** A developer (or the user) can read the committed SQL and judge whether it makes sense for the query, without reading executor source. This directly addresses the "I'm not reading the executor code, but I need to validate it" tension that motivates this whole contract.
- **Query-plan regression detection.** Refactors that change the executor's compilation strategy (different JOIN order, reverse-FK vs. explicit ID list, etc.) show up as SQL diffs even when the response envelope is byte-identical. Sometimes that's intended (performance work); sometimes it's a latent bug (different JOIN shape that will cause future inflation under different graph shapes).

### 5. Requirement traceability via `covers`

Every Gridkin scenario carries a `covers` array listing the spec RIDs and ACIDs it exercises. The Gridkin runner emits a derived coverage matrix on demand, mapping RID → covering scenarios. This produces the requirement-traceability matrix the audit identified as missing today.

`covers` is **binding for new scenarios** — scenario files that omit it fail to load. It is **not retroactively required** for existing Gryphon tests (in `tap_grid/tests/test_gryphon.py`); the traceability investment starts at the Gridkin boundary going forward.

### 6. Snapshot regeneration is opt-in and reviewed

When implementation changes legitimately invalidate expecteds, the runner supports a `--update-snapshots` flag (or equivalent) that regenerates expected files. The flag is **never invoked automatically**: no CI step regenerates snapshots; no pre-commit hook regenerates snapshots. A human runs it intentionally, reviews the `git diff` line-by-line, and commits expected changes in the same change as the implementation change.

The runner prints an oracle-discipline reminder when regenerating, because automated regeneration without review is the exact anti-pattern the discipline exists to prevent.

### 7. TCK as scenario inspiration (never as scenario source)

When authoring Gridkin scenarios for a new feature, the workflow includes a pass over the openCypher TCK's corresponding feature folder for *corner-case intent extraction*. The TCK is a 10-year accumulation of "things that historically broke real graph engines" — that knowledge is what we want, not the queries themselves.

The workflow:

1. Identify the TCK feature folder for the feature being implemented (e.g. `tck/features/clauses/optional-match/` for OPTIONAL MATCH).
2. Read each scenario for its *intent* — what corner case does it pin down? What historical confusion does it guard against?
3. Notes-list the corner-case intents that apply to Gryphon's semantics. Skip Cypher-specific quirks (null comparison weirdness, type coercion edge cases) — those are not Gryphon's contract.
4. Author Gridkin scenarios in TAP vocabulary covering each retained intent. Queries are written in Gryphon syntax against `pg_*` playground types; fixtures are hand-authored; expecteds are hand-authored per the oracle discipline.
5. Set the scenario's `inspired_by` field to the TCK feature folder path — an attribution breadcrumb so future-us can trace which corner-case taxonomies have been mined.

Hard constraints (per `feedback_borrow_from_oss_prior_art`: inspire, never copy):

- **No TCK query text appears in any Gridkin scenario.** Even verbatim-equivalent Cypher is rewritten in TAP vocabulary. Apache 2.0 licensing permits port; project rule forbids it; the breadcrumb is honesty, not legal cover.
- **No TCK graph data is reused.** TCK graphs are property-bag Cypher data; playground fixtures use playground BaseModel-backed entity types.
- **No TCK expected results are reused.** TCK expecteds reflect Cypher semantics; Gridkin asserts against Gryphon semantics.

### 8. What's explicitly *not* in the validation contract

The contract is calibrated to solo dog-food. Things deliberately omitted (named so we don't reinvent them):

- **Performance / scale testing.** Deferred until a real perf issue or a customer-hosted inflection.
- **Property-based / fuzz testing** (SQLancer-style TLP/NoREC, sqlsmith-style query generation). Powerful but premature.
- **Full HTTP-layer E2E suite.** Deferred to minimal smoke testing per `project_solo_dogfood_window`.
- **CI integration of the Gridkin runner.** Wiring into the multi-session promote-gate happens after the runner exists and CI is set up — not part of v0.
- **Retroactive migration of `tap_grid/tests/test_gryphon.py`.** Existing tests stay where they are; Gridkin complements rather than replaces them.

## Future Seams Appendix

Items named here are deliberate non-goals for v0 but tagged for vocabulary consistency, so we don't reinvent them by accident when demand finally arrives. Each item includes the demand signal that would promote it.

### Public conformance kit (Gridkin as satellite contract)

When the satellite system arrives (per `project_satellite_system_vision` — sandboxed plugins/agents/collectors as "satellites" calling back via a versioned wire protocol), satellite query authors will need a way to verify their queries against the grid. Gridkin's structure (committed graph + query + expected envelope + expected SQL, in a stable file format) is exactly that contract. Promotion path: when the first satellite needs to author Gryphon queries against a remote grid, the existing Gridkin format becomes the public conformance surface with minimal change. The scenario format being JSON (not Cucumber/Gherkin) is deliberate: it survives the eventual transition to a public contract more cleanly than a BDD-DSL would.

### Full TCK adoption

If Gryphon's surface ever grows to where ~70%+ of the openCypher TCK translates to Gryphon, *and* there's external demand for a Cypher-subset compatibility claim, mechanical TCK porting becomes worth considering. Promotion path: a customer (post first paid assessment) asks "does your query language implement Cypher?" and the answer needs to be precise. Until then: TCK-as-inspiration only.

### Property-based / fuzz testing

SQLancer-style invariants (Q1 UNION Q2 ≡ Q2 UNION Q1; aggregation invariants under permutation) and sqlsmith-style query generation are powerful in mature query-engine teams. Promotion path: Gryphon's surface stabilizes enough that defending it against adversarial inputs becomes valuable, or a real bug shipped to a customer is traceable to a class of input that property-based testing would have surfaced.

### HTTP-layer E2E suite

Per the audit, the `tap_api/routers/gryphon.py` endpoint has no end-to-end coverage today. Promotion path: a bug surfaces in envelope marshaling, layer parameter propagation, or error-to-HTTP-status mapping that the Gridkin scenarios (which assert at the executor level) don't catch. Until then, minimal smoke per solo dog-food window.

### NOT EXISTS inflation audit

Carried over from the validation findings: the executor's NOT EXISTS path carries an explicit "fix for multi-hop COUNT inflation" comment with no corresponding test. This is the single most concerning legacy correctness concern. Promotion path: any change that touches NOT EXISTS executor code triggers the audit first — author Gridkin scenarios explicitly designed to exercise inflation-prone NOT EXISTS shapes, then pin down behavior, then proceed with the original change.

### Variable-length paths (E1) and path variables (E2)

The grammar parses; the executor rejects. The half-done grammar is the foothold. Promotion path: the first dashboard demand for blast-radius / reachability queries — most likely the Sam-demo zoom interaction or the "what depends on this?" panel in a paid assessment.

### Performance & observability

Performance is not a current concern — nothing in the architecture is structurally slow, and the choices that matter (single PostgreSQL, read-only, ORM-compiled rather than custom executor, batched envelope serialization) are all on the right side of the speed/simplicity trade. The cliffs are the predictable ones any graph-on-relational system hits: edge-table hotspot, deep-traversal plan quality, recursive CTE behavior under variable-length paths, result-set hydration at scale.

When speed becomes a real concern, the following five investments are listed in the order they should land. They are grouped here as a single future-seam unit because they are interdependent and should not be pursued piecemeal.

#### P1. Executor-level timing instrumentation (cheap-now, valuable-later)

Add timing logs at the executor entry point capturing query string, params, compile-time, execute-time, and serialize-time. Five lines of code. This is the only one of the five with a "cheap-now" character — worth doing well before speed becomes a question, because the day "is this slow?" gets asked, the answer arrives the next day instead of after a week of instrumentation work. Promotion path: the next executor-touching change is a natural place to add it; no demand signal required.

#### P2. `gryphon explain` integrated with `EXPLAIN ANALYZE`

The `gryphon explain` developer surface (named in bucket H3) emits the ORM-compiled SQL. Extending it to optionally run that SQL through PostgreSQL's `EXPLAIN ANALYZE` against a test grid surfaces PG's actual query plan and timing — the single highest-leverage debugging tool for query-engine work. Shares infrastructure with the Gridkin SQL-snapshot capture, so the marginal cost when explain itself lands is small.

#### P3. Gridkin "perf scenario" subset

A handful of Gridkin scenarios that run against a larger fixture (~10k entities) with timing assertions. Not for CI gating — for monitoring trends over time. When refactors regress performance, the perf subset surfaces it before users notice. Shares the Gridkin runner; the only new piece is a larger fixture and a timing assertion mode.

#### P4. Advanced executor profiling

The advanced executor path (`tap_grid/gryphon/executor.py:1224-1413` at time of writing — multi-hop chains, NOT EXISTS, COUNT aggregation) is the heaviest code, the least-tested, and the most likely to have quadratic-ish behavior hiding. When perf work begins, this is where it starts. The NOT EXISTS inflation audit (above) is the correctness-flavored sibling of this profiling work — they share fixtures and likely share fixes.

#### P5. Index work driven by observed data

Composite indexes on the edge table (`(edge_type, from_entity_id)`, `(edge_type, to_entity_id)`); GIN indexes on dimensions and JSONB fields where predicate access concentrates; partial indexes on hot entity types. Index work is the hardest to predict in advance and the easiest to apply in response to `EXPLAIN ANALYZE` output. Hence its position at the end of this list — driven by data from P1-P4, not by speculation.

**The honest summary the list serves**: don't optimize Gryphon on speculation. The Gridkin scenarios will tell you which shapes are slow as they accumulate, and PG's `EXPLAIN ANALYZE` will tell you why. P1 buys the visibility cheaply; everything else follows from what P1 surfaces.

## Cross-Reference Index

Every spec, doc, and plan this wishlist references, with a one-line description of what's in each — so a future agent loading this doc can navigate without re-discovering the geography.

### Specs

- [`tap_grid/specs/spec-grid-traversal-language.md`](../tap_grid/specs/spec-grid-traversal-language.md) — The Gryphon language: MATCH/WHERE/RETURN clause shape, predicate combinators, parameters, return semantics. The v1 surface is Implemented; JSONPath and envelope-aware field paths are Proposed / In Development.
- [`tap_grid/specs/spec-grid-traversal-execution.md`](../tap_grid/specs/spec-grid-traversal-execution.md) — The Gryphon executor: pattern dispatch (type scan, hub-and-spoke, edge-type scan), ORM composition, supported and unsupported patterns. Implemented.
- [`tap_grid/specs/spec-grid-gryphon-multihop-aggregation.md`](../tap_grid/specs/spec-grid-gryphon-multihop-aggregation.md) — Multi-hop chains, NOT EXISTS anti-joins, COUNT with implicit GROUP BY. Implemented. The "fix for multi-hop COUNT inflation" comment in executor code is the audit-flagged concern.
- [`tap_grid/specs/spec-grift-envelope.md`](../tap_grid/specs/spec-grift-envelope.md) — The three-lane envelope shape (spine surface + data lane + display lane). Proposed; being implemented on a parallel session. Gridkin scenario expecteds will regenerate when this lands.
- [`tap_grid/specs/spec-grift-subgraph.md`](../tap_grid/specs/spec-grift-subgraph.md) — Canonical subgraph response shape (`{nodes, edges}` with lite / full / extended layers). Implemented; partially superseded by spec-grift-envelope when that moves to Implemented.
- [`plugins/gryphon_playground/specs/spec-gryphon-playground-v0.md`](../plugins/gryphon_playground/specs/spec-gryphon-playground-v0.md) — The Gryphon Playground plugin: scope, the `pg_*` / `PG_*` playground vocabulary, and the two-tier fixture structure. Top-level plugin spec; delegates the file format to the Gridkin spec below. Proposed.
- [`plugins/gryphon_playground/specs/spec-gridkin-v0.md`](../plugins/gryphon_playground/specs/spec-gridkin-v0.md) — The Gridkin scenario format, runner contract, oracle discipline, snapshot regeneration discipline, explain-SQL snapshot, requirement traceability, TCK-as-inspiration workflow, and JSON Schema requirement. Proposed; this doc is its operational companion.

### Plans / Roadmap

- [`plan/road-rampart.md`](../plan/road-rampart.md) — The Rampart roadmap. Active step is `step-rampart-sam-demo` (target 2026-06-01: Sam sees Rampart assess a faithful live reproduction of samaydlette.com). Next step `step-rampart-first-paid-assessment` (target 2026-07-07). The Doctrine section is the standing strategic filter against which wishlist promotions get evaluated.
- [`specs/spec-roadmap.md`](../specs/spec-roadmap.md) — Roadmap conventions (step IDs, status vocabulary, timeline table).

### Memory entries that govern this work

(Auto-memory under `/Users/george/.claude/projects/-Users-george-tap-sessions-main/memory/`.)

- `feedback_gryphon_over_orm` — Graph reads go through Gryphon; raw ORM is break-glass. The urge to reach for ORM is itself a demand signal that Gryphon needs to grow.
- `feedback_borrow_from_oss_prior_art` — Inspire from OSS; never copy. The TCK-as-inspiration workflow above is the operationalization of this rule for the query-engine domain.
- `feedback_future_seam_discipline` — Clever-but-premature ideas: name as future seam + "wait for demand signal." The status flags throughout this doc operationalize this discipline.
- `feedback_explicit_over_brevity_llm_era` — LLMs author the code; the writer doesn't care about brevity; the reader (an LLM) benefits from explicit rationale. This doc's verbosity is policy, not accident.
- `feedback_json_formats_need_schema` — Every new structured-data format needs a JSON Schema authored same-change and validated on load. Drives `req-gridkin-json-schema` in the Gridkin spec.
- `project_solo_dogfood_window` — Through ~2026-07-17 solo, dog-fooding on laptop; testing = minimal smoke + pre-push gate only. Calibrates the validation contract's scope.
- `project_satellite_system_vision` — Long-term: sandboxed plugins/agents/collectors as "satellites." Drives the Gridkin-as-future-public-contract framing.
- `feedback_spec_before_mirroring_rules` — Design architectural principles in the canonical spec first; mirror to memory only once settled. Why this doc references existing specs as authoritative rather than restating their rules.
- `project_spec_before_plugin_init_workflow_gap` — Open question (2026-05-20): the create-plugin skill assumes init → spec; the Gridkin work hit a case for spec → init. User thinking overnight.

### Existing Gryphon test code

- `tap_grid/tests/test_gryphon.py` — ~1,350 lines, ~60 tests across nine test classes. Comprehensive at the parser level; integration-shaped at the executor level; oracle-light. Audit findings about derived-fact-vs-oracle assertions, missing topology corners, missing HTTP-layer coverage, and the NOT EXISTS-inflation-comment-without-test all originate from inspection of this file.
- `tap_grid/grift/subgraph.py` — Envelope serializers (lite / full / extended). Recently modified for the three-lane envelope work.
- `tap_grid/gryphon/executor.py` — ~1,440 lines, five major dispatch branches. The advanced executor path (lines 1224-1413) is the heaviest unit of code and the most fragile under refactor; Gridkin scenarios will give it explicit oracle coverage when wishlist items in buckets C, D, F land.

### Related dev docs (style reference)

- [`docs/doc-dev-multisession-onboarding.md`](doc-dev-multisession-onboarding.md) — Onboarding a new multi-session dev environment. Style/frontmatter reference.
- [`docs/doc-dev-playwright-refresh.md`](doc-dev-playwright-refresh.md) — Playwright MCP refresh. Style/frontmatter reference.
