# Gryphon Multi-Hop and Aggregation Extension Specification

## Philosophy

Gryphon v1 is deliberately small: single-hop `MATCH` patterns, predicate `WHERE` clauses, projection-only `RETURN`. That floor fit the first wave of TAP searches — type scans, hub-and-spoke traversals, simple predicate filters — and left obvious escape valves (module-based Python runners) for anything more ambitious.

This spec extends gryphon along three axes to unlock a class of queries that are becoming idiomatic, not exotic: **multi-hop patterns**, **anti-join subqueries** (`NOT EXISTS`), and **count aggregation with implicit grouping**. The motivating query is the compliance alert-count traversal — "per entity, count open findings that have no active exception covering them" — but the same three extensions unblock many other shapes: cross-layer traversals, coverage audits, gap analysis, and most summary tiles that reduce graph structure to a tabular result.

The choice to extend the language, rather than push the query into a custom Python runner, is deliberate. Each custom runner is a chunk of code that bypasses the gryphon compilation pipeline and its validation, read-only guarantees, and backend-agnosticism. Runners are the right tool when semantics exceed what a declarative query can express; they are the wrong tool when the semantics *can* be declared and we're just missing language surface. This extension keeps semantics declarative wherever the query shape allows it.

The extension is scoped tight on purpose. `COUNT` is the only aggregate; `SUM`/`AVG`/`MIN`/`MAX` are not in scope. `NOT EXISTS` covers anti-joins but `EXISTS`, `OPTIONAL MATCH`, and `UNION` do not. Variable-length traversal (`-[*1..3]->`) remains rejected by the executor even though the grammar parses it. Each deferred item has a clear upgrade path when a real use case arrives.

## Goals

|    |              |                                                                          |
| :---: | ---       | ---                                                                      |
| 1. | Declarative     | Queries the language *can* express stay in the language, not in custom Python runners |
| 2. | Minimal-Surface | Only the constructs needed by the motivating class of queries; no speculative grammar |
| 3. | Safe            | Read-only, validation, and service-layer posture from v1 carry through unchanged |
| 4. | Compatible      | Every existing gryphon query continues to parse, execute, and return identical results |
| 5. | Extensible      | Grammar, AST, and executor changes leave clean seams for deferred work (other aggregates, EXISTS, variable-length, UNION) |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-grid-gryphon-multihop | [Multi-Hop Pattern Execution](#multi-hop-pattern-execution) | Proposed | Executor accepts N-hop chains that the grammar already parses |
| req-grid-gryphon-not-exists | [NOT EXISTS Subqueries](#not-exists-subqueries) | Proposed | New grammar production for correlated anti-join subqueries |
| req-grid-gryphon-count | [COUNT Aggregation and Implicit GROUP BY](#count-aggregation-and-implicit-group-by) | Proposed | `COUNT(var)` in RETURN, implicit GROUP BY on non-aggregated columns |
| req-grid-gryphon-rows | [Rows Result Envelope](#rows-result-envelope) | Proposed | Canonical envelope gains a `rows` key populated by aggregating queries |
| req-grid-gryphon-compat | [Backward Compatibility](#backward-compatibility) | Proposed | Existing queries parse, execute, and return identical results |

---

### Multi-Hop Pattern Execution
----
RID: `req-grid-gryphon-multihop`
Status: `Proposed`

The executor must accept `MATCH` patterns with more than one edge hop, producing results that join each declared hop by shared variable.

#### Implementation

- No grammar change required. The current `grammar.lark` already parses `pattern: node_pattern (edge_pattern node_pattern)*` as multi-hop. Today the executor rejects anything beyond one edge with the error `"Unsupported gryphon pattern: only single-hop patterns are supported."` This requirement is to remove that guard and implement the join path.
- Semantics: each additional edge pattern composes the query by joining on the shared node variable. `MATCH (a)-[:E1]->(b)-[:E2]->(c)` produces the set of `(a, b, c)` triples where `a -E1-> b` and `b -E2-> c` both hold.
- Directionality: each edge pattern's arrow is honored independently. `-[:E]->`, `<-[:E]-`, and `-[:E]-` each behave as in single-hop today.
- Node labels on intermediate nodes may be omitted (`(b)` with no label) or present (`(b:node_type)`). Labels act as type filters where present, wildcard where absent.
- Path variable binding (`path = MATCH (a)-[]->(b)`) remains parseable but out of scope for this requirement; queries using `path = ...` continue to be rejected by the executor with a targeted error message until a future iteration addresses path semantics.
- Variable-length edges (`-[:E*1..3]->`) remain rejected. The grammar parses them; the executor returns a clear unsupported-feature error referencing the variable-length requirement as deferred.
- Compilation targets Django ORM joins composed across `Edge` queryset filters; the existing ORM compiler (`orm_compiler.py`) gains N-hop join support. The compiler stays the single source of truth for translating AST → ORM plan.

#### Development

Multi-hop is the largest of the three language changes in this spec because it shifts the compiler from "one edge queryset" to "composed joins." The discipline here is to implement the simplest correct join path — one ORM join per hop, anchored by a WHERE predicate where one exists — and not reach for query-planner heuristics. Patterns with no WHERE anchor at all are expected to scan the full graph and should log an info-level warning in the result envelope; production callers should add a WHERE anchor or a LIMIT.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-gryphon-multihop-1 | N-Hop Chains | Proposed | The executor accepts and correctly joins MATCH patterns with two or more edge hops. | |
| req-grid-gryphon-multihop-2 | Directionality Per Hop | Proposed | Each hop's direction (`->`, `<-`, `-`) is respected independently. | |
| req-grid-gryphon-multihop-3 | Optional Intermediate Labels | Proposed | Intermediate node patterns with no label are treated as any-type and still bind their variable. | |
| req-grid-gryphon-multihop-4 | Variable-Length Still Rejected | Proposed | `-[:E*m..n]->` patterns continue to be rejected at the executor with an unsupported-feature error. | Grammar parses them; deferred to a future iteration |
| req-grid-gryphon-multihop-5 | Single-Hop Results Unchanged | Proposed | Queries with exactly one hop produce identical results to the pre-extension executor. | See `req-grid-gryphon-compat` |

#### Future

- Variable-length traversal with explicit bounds and cycle semantics.
- Path variable binding and path-level projections.
- Query planner heuristics for anchor selection when multiple WHERE clauses are equally viable.

---

### NOT EXISTS Subqueries
----
RID: `req-grid-gryphon-not-exists`
Status: `Proposed`

Gryphon gains a `NOT EXISTS { ... }` block that expresses correlated anti-join subqueries: "match the outer pattern where there *does not exist* a corresponding inner pattern."

#### Implementation

- Grammar addition: a new clause type `not_exists_clause` produced by:

  ```
  not_exists_clause: _NOT_KW _EXISTS_KW "{" match_clause where_clause? "}"
  _EXISTS_KW: /EXISTS/i
  ```

  and threaded into the top-level `clause` alternation.
- Placement: `NOT EXISTS` is a top-level clause sibling to `MATCH`, `WHERE`, and `RETURN`. A query may contain zero or more `NOT EXISTS` blocks; each is applied as an additional filter against the outer match set.
- Variable scope:
  - Variables declared in the outer query (in the outer `MATCH`) are in scope inside the `NOT EXISTS` block and may be used in its MATCH and WHERE.
  - Variables declared inside a `NOT EXISTS` block are scoped to that block and are not visible outside it or in sibling blocks.
  - This matches Cypher's `CALL { ... }` / `WHERE NOT EXISTS { ... }` subquery scope semantics.
- Semantic: the outer pattern row is included in the result iff the subquery pattern has zero matches under that row's variable bindings.
- `EXISTS { ... }` (without `NOT`) is not in scope. The executor rejects bare `EXISTS` with an unsupported-feature error. Most positive-existence cases can be expressed by adding another `MATCH` hop.
- Nesting: `NOT EXISTS` blocks themselves do not contain further `NOT EXISTS` blocks in v1. A clear parse-time error is surfaced if encountered.
- Compilation: the ORM compiler translates `NOT EXISTS { MATCH (x)-[:E]->(shared) WHERE ... }` into a Django `~Exists(Subquery(...))` clause composed against the outer queryset, with the correlation carried through the shared variable.

#### Development

The motivating query for this requirement — "findings not covered by an active exception" — is the cleanest test case. Implementation tests should exercise at least three cases: (1) the motivating correlated anti-join, (2) a `NOT EXISTS` where the correlated variable is mapped through a multi-hop outer pattern, (3) a `NOT EXISTS` where the inner pattern itself is multi-hop. Uncorrelated inner patterns (no shared variable with the outer) are valid but less useful; keep them on the happy path but do not optimize for them.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-gryphon-not-exists-1 | Grammar Support | Proposed | The parser accepts `NOT EXISTS { MATCH ... WHERE ... }` as a top-level clause. | |
| req-grid-gryphon-not-exists-2 | Variable Correlation | Proposed | Variables declared in the outer MATCH are in scope inside a `NOT EXISTS` block. | |
| req-grid-gryphon-not-exists-3 | Anti-Join Semantics | Proposed | Outer rows are excluded if the inner pattern has any match under their bindings. | |
| req-grid-gryphon-not-exists-4 | Bare EXISTS Rejected | Proposed | `EXISTS { ... }` without `NOT` is rejected at the executor with an unsupported-feature error. | Deferred to a future iteration |
| req-grid-gryphon-not-exists-5 | No Nested Anti-Joins | Proposed | `NOT EXISTS` blocks that themselves contain `NOT EXISTS` are rejected at parse with a clear error. | |
| req-grid-gryphon-not-exists-6 | Multiple Sibling Blocks | Proposed | A query may contain multiple sibling `NOT EXISTS` blocks; each is applied as an additional anti-join filter. | |

#### Future

- Positive `EXISTS { ... }` when a concrete use case justifies it over adding a hop to the outer MATCH.
- Nested `NOT EXISTS` for higher-order exclusions.
- `OPTIONAL MATCH` as a related but distinct construct (left-outer-join semantics).

---

### COUNT Aggregation and Implicit GROUP BY
----
RID: `req-grid-gryphon-count`
Status: `Proposed`

Gryphon gains a single aggregate function, `COUNT`, usable in `RETURN` projections. Non-aggregated RETURN items implicitly form the GROUP BY key set.

#### Implementation

- Grammar addition: `RETURN` items may be aggregate function calls in addition to field paths.

  ```
  return_item: aggregate_call _AS_KW NAME
             | field_path (_AS_KW NAME)?
  aggregate_call: _COUNT_KW "(" (NAME | field_path) ")"
  _COUNT_KW: /COUNT/i
  ```

  - `COUNT(var)` counts non-null occurrences of the variable across the match set.
  - `COUNT(field_path)` counts non-null occurrences of the projected field.
  - `COUNT(*)` is **not** in scope; every count expression names its counted variable or field. The executor rejects `COUNT(*)` with a clear error.
- `AS alias` is **required** on every aggregate RETURN item. The alias becomes the column key in the `rows` envelope field (see `req-grid-gryphon-rows`). Aliases on non-aggregate RETURN items remain optional; when omitted, the field path expression itself is the column key.
- `COUNT(DISTINCT var)` is not in scope. Callers who need distinct-count semantics should structure the outer pattern such that duplicates cannot occur. Defer to a future iteration when a concrete use case appears.
- Implicit GROUP BY: when at least one aggregate is present in RETURN, every non-aggregate RETURN item becomes a GROUP BY key. When all RETURN items are aggregates, the query produces a single-row result.
- Semantic example — motivating query:

  ```
  MATCH (e)-[:HAS_FINDING]->(f)
  WHERE f.status = "open"
  NOT EXISTS {
    MATCH (x)-[:COVERS_FINDING]->(f)
    WHERE x.status = "active"
  }
  RETURN e.entity_id AS entity_id, COUNT(f) AS count
  ```

  produces rows of the shape `{entity_id: "...", count: <int>}`, grouped by `e.entity_id`.
- Compilation: the ORM compiler emits `.values(*group_keys).annotate(**aggregates)` against the joined queryset. Each aggregate becomes a `Count(...)` annotation keyed by the RETURN alias.
- Counts are always integers. `NULL` / missing values are excluded from counts per SQL standard semantics.

#### Development

The scope of this requirement is deliberately narrow. Numeric aggregates (`SUM`, `AVG`, `MIN`, `MAX`) and `DISTINCT` are all straightforward grammar and compiler additions on top of this foundation — but adding them now introduces surface area we don't have real queries for. Wait for the first concrete use case, then pull the lever. The ACID set below includes "only COUNT is supported" as an explicit acceptance criterion so drift is caught at review time.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-gryphon-count-1 | COUNT In RETURN | Proposed | `COUNT(var)` and `COUNT(field_path)` are accepted in RETURN projections. | |
| req-grid-gryphon-count-2 | AS Alias Required For Aggregates | Proposed | Every aggregate RETURN item must carry an `AS alias`; parse fails otherwise. | |
| req-grid-gryphon-count-3 | Implicit GROUP BY | Proposed | Non-aggregate RETURN items become GROUP BY keys when any aggregate is present. | |
| req-grid-gryphon-count-4 | All-Aggregate Returns Single Row | Proposed | Queries whose RETURN contains only aggregates produce exactly one result row. | |
| req-grid-gryphon-count-5 | COUNT Is The Only Aggregate | Proposed | `SUM`, `AVG`, `MIN`, `MAX`, `COUNT(*)`, and `COUNT(DISTINCT ...)` are rejected with an unsupported-feature error. | Each has a future-iteration upgrade path |
| req-grid-gryphon-count-6 | Integer Result | Proposed | Count results are integers in the rows envelope. | |

#### Future

- Numeric aggregates: `SUM`, `AVG`, `MIN`, `MAX`.
- `COUNT(DISTINCT var)` and `COUNT(*)`.
- Post-aggregation `HAVING` clauses for filtering grouped results.
- `ORDER BY` over aggregated columns.

---

### Rows Result Envelope
----
RID: `req-grid-gryphon-rows`
Status: `Proposed`

The canonical search result envelope gains a `rows` field. Aggregating queries populate `rows` as their primary output.

#### Implementation

- Envelope shape becomes:

  ```json
  {
    "nodes": [...],
    "edges": [...],
    "rows": [
      {"entity_id": "019...", "count": 5},
      ...
    ],
    "info": [...],
    "warnings": [...]
  }
  ```

- `rows` is a JSON array. Each element is an object keyed by RETURN alias (or field-path expression where no alias is given for non-aggregate items). Values are primitives (strings, integers, numbers, booleans, nulls). Nested objects are not emitted in v1; queries that project a whole entity (`RETURN e`) continue to populate `nodes` for that variable rather than embedding the full entity into a row.
- Population rule:
  - **Aggregating queries** (any `COUNT(...)` in RETURN) populate `rows`. One row per GROUP BY key combination. `nodes` and `edges` remain populated only with distinct entities referenced by non-aggregate whole-entity RETURN items (e.g. `RETURN e, COUNT(f)` populates `nodes` with the distinct `e` entities and `rows` with `{e: <entity_id>, count: <n>}` per group).
  - **Non-aggregating queries** may also populate `rows`, but are not required to in v1 to preserve strict backward compatibility. If a future iteration decides non-aggregating queries should always populate `rows`, that change lands as a separate requirement after consumers have confirmed they can tolerate the additional field.
- The `rows` field is always present in the envelope even when empty (`[]`), so consumers can rely on its shape without null-checking.
- When `nodes` and `rows` both reference the same entity (e.g., `RETURN e, COUNT(f)`), the canonical form is: the row contains the entity's `entity_id` (not a nested entity object), and the full entity record lives in `nodes`. Consumers join by `entity_id`.

#### Development

The decision to *not* populate `rows` for non-aggregating queries in v1 is intentional backward-compatibility insurance. Existing consumers have been written against `{nodes, edges}` and have never seen `rows`. Adding a new optional field is safe; making a field appear on outputs it didn't appear on before invites surprises. Once the aggregating path is in use and stable, revisit the universal-population rule as a separate, opt-in change.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-gryphon-rows-1 | Envelope Key Added | Proposed | The result envelope contains a `rows` field alongside `nodes`, `edges`, `info`, `warnings`. | |
| req-grid-gryphon-rows-2 | Always Present | Proposed | `rows` is always present in the envelope, even when the value is `[]`. | |
| req-grid-gryphon-rows-3 | Aggregating Queries Populate `rows` | Proposed | Queries with any aggregate in RETURN populate `rows` with one object per GROUP BY key. | |
| req-grid-gryphon-rows-4 | Entity Reference By ID | Proposed | Whole-entity RETURN items referenced in aggregate queries appear in `rows` as `entity_id` values, with full entity records in `nodes`. | |
| req-grid-gryphon-rows-5 | Primitive Row Values | Proposed | Row object values are primitives only — no nested objects, no arrays — in v1. | |
| req-grid-gryphon-rows-6 | Non-Aggregating Queries Unchanged | Proposed | Non-aggregating queries preserve existing envelope behavior (empty `rows`, populated `nodes`/`edges`). | See `req-grid-gryphon-compat` |

#### Future

- Universal `rows` population for non-aggregating queries (behind an opt-in flag, eventually default).
- Nested object row values (e.g. full entity embedded) once a consumer needs it and we've decided how to reconcile with `nodes`.
- Pagination hints on aggregating queries that produce large result sets.

---

### Backward Compatibility
----
RID: `req-grid-gryphon-compat`
Status: `Proposed`

Every query that parses and executes before this extension lands continues to parse, execute, and return results with the same shape and content after.

#### Implementation

- Single-hop queries produce identical `nodes`/`edges` collections. The new `rows` field is present but empty for these queries (`req-grid-gryphon-rows-6`).
- `WHERE` predicate semantics, `RETURN` projection behavior for non-aggregate field paths, runtime input binding (`$var`), and error shapes are unchanged.
- The existing test suite for single-hop, hub-and-spoke, and edge-scan patterns must continue to pass without modification.
- Error messages previously emitted for unsupported features (multi-hop, aggregates) change content as those features land. Downstream callers that string-match against specific error messages are out of scope for backward compatibility; error codes (where present) remain stable.
- Variable-length edge syntax (`-[:E*m..n]->`), already rejected pre-extension, continues to be rejected with a targeted unsupported-feature error.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-gryphon-compat-1 | Single-Hop Parity | Proposed | Single-hop queries produce identical `nodes` and `edges` collections before and after the extension. | |
| req-grid-gryphon-compat-2 | Existing Test Suite Passes | Proposed | The pre-extension gryphon test suite passes unchanged. | |
| req-grid-gryphon-compat-3 | Envelope Additive | Proposed | New `rows` field is additive; existing envelope keys retain their shape and semantics. | |
| req-grid-gryphon-compat-4 | Error Codes Stable | Proposed | Structured error codes for existing rejection cases are unchanged. | Error message *strings* may be updated |

---

## Future Work

- **Positive `EXISTS { ... }`** subqueries.
- **Numeric aggregates** (`SUM`, `AVG`, `MIN`, `MAX`).
- **`COUNT(DISTINCT ...)`** and **`COUNT(*)`**.
- **`HAVING`** clause for post-aggregation filtering.
- **`ORDER BY`** over returned columns, including aggregates.
- **`OPTIONAL MATCH`** for left-outer-join semantics.
- **`UNION`** and **`UNION ALL`** across sibling queries.
- **Variable-length edge traversal** with cycle handling (`-[:E*1..3]->`).
- **Path variable binding** and path-level projections.
- **Nested `NOT EXISTS`** for higher-order anti-joins.
- **Query planner heuristics** once multiple anchor candidates are common.
- **Result pagination** for aggregating queries returning large result sets.

## Downstream Consumers

- **Compliance alert-count population** (`plugins/fedramp_20x_ksi`, cross-reference with `spec-fedramp-20x-ksi-finding.md`) — the motivating consumer. Uses all three new features in a single query.
- **`spec-viz-badges.md` search-backed population** — the `population.type: "search"` variant of status-badge configuration will consume aggregating-query envelopes with a `rows` field keyed `{entity_id, count}`.
- Any future summary/tile panels that reduce graph structure to tabular data.

## Status Vocabulary

| Status States |  |
| --- | --- |
| Proposed |  |
| Approved for Development | Requirement is accepted and ready to be implemented |
| In Development |  |
| Implemented |  |
| Verified |  |
| Refactoring |  |
| Deprecating |  |
| Deprecated | Not part of the current architecture and should not be implemented |

## RID Format

`req-<application>-<specification>-<feature>-<sub-feature>`

## Requirements Format

`RID: `...``
`Status: `...``

| Sub-Sections | (as needed) |
| --- | --- |
| Status Details |  |
| Implementation |  |
| Development |  |
| Acceptance Criteria |  |
| Future |  |
