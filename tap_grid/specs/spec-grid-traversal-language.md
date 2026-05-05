# Grid gryphon Language Specification

## Philosophy

gryphon should be pleasant to read in strings while still being structured enough to parse into
a predictable AST. Familiarity with Cypher improves readability for engineers who have used
graph databases, but TAP does not aim for Cypher compatibility — only for a language narrow
enough to compile safely into TAP-controlled execution plans.

## Goals

|    |              |                                                                          |
| :---: | ---       | ---                                                                      |
| 1. | Compact       | Common graph traversals fit in a short gryphon string                    |
| 2. | Familiar      | Cypher-like notation where it improves readability                       |
| 3. | Reusable      | Storable on Search objects, alias rules, panel config, naming policies   |
| 4. | Parameterized | Runtime inputs via $var without rewriting gryphon text                   |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-grid-traversal-lang-shape | [Traversal Language Shape](#traversal-language-shape) | Implemented | MATCH/WHERE/RETURN clause structure |
| req-grid-traversal-lang-storage | [Traversal Storage Form](#traversal-storage-form) | Implemented | String and list[str] storage forms |
| req-grid-traversal-lang-patterns | [Pattern And Binding Syntax](#pattern-and-binding-syntax) | Implemented | Node/edge/path patterns, direction, bounded traversal |
| req-grid-traversal-lang-filters | [Field And Predicate Semantics](#field-and-predicate-semantics) | Implemented | Inline filters and WHERE predicates over model fields; multi-step JSON paths deferred to `req-grid-traversal-lang-filters-jsonpath` |
| req-grid-traversal-lang-filters-jsonpath | [JSONPath For JSON Field Predicates](#jsonpath-for-json-field-predicates) | Proposed | Adopt RFC 9535 JSONPath for `WHERE` predicates over JSON-backed fields; replace in-house dot/bracket grammar |
| req-grid-traversal-lang-combinators | [Predicate Combinators](#predicate-combinators) | Implemented | AND/OR/NOT in WHERE predicates |
| req-grid-traversal-lang-params | [Runtime Inputs And Variables](#runtime-inputs-and-variables) | Implemented | $var runtime inputs and named pattern bindings |
| req-grid-traversal-lang-returns | [Return Semantics](#return-semantics) | Implemented | RETURN projection and graph envelope default |


### gryphon Language Shape
----
RID: `req-grid-traversal-lang-shape`
Status: `Implemented`

gryphon uses Cypher-compatible clause style for the core read/traversal surface.

#### Implementation

The v1 gryphon language supports these top-level clauses:

- `MATCH` — pattern-binding clause (one or more allowed)
- `WHERE` — predicate clause over bound variables
- `RETURN` — projection clause

Multiple `MATCH` clauses are allowed and are compositional: bindings from earlier `MATCH` clauses
are in scope for later ones, exactly as in Cypher.

The first version is intentionally read-only. It does not include write clauses such as `CREATE`,
`MERGE`, `SET`, or `DELETE`. These are rejected at parse time rather than at runtime.

```text
MATCH p = (port:port)-[:ON_INTERFACE]->(iface:interface)-[:ON_HOST]->(host:host)
WHERE port.name = $port_name
RETURN p, host.entity_id, host.name
```

```text
MATCH (hub)-[edge]-(neighbor)
WHERE hub.entity_id = $entity_id
RETURN hub, edge, neighbor
```

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-traversal-lang-shape-1 | Supports Match Clause | Implemented | gryphon text supports `MATCH` as the primary pattern-binding clause. | |
| req-grid-traversal-lang-shape-2 | Supports Where Clause | Implemented | gryphon text supports `WHERE` predicates over bound variables and fields. | |
| req-grid-traversal-lang-shape-3 | Supports Return Clause | Implemented | gryphon text supports `RETURN` for named variables and projected fields. | |
| req-grid-traversal-lang-shape-4 | Read-Only Surface Only | Implemented | V1 gryphon text excludes graph mutation clauses; they are rejected at parse time. | |
| req-grid-traversal-lang-shape-5 | Multiple Match Compositional | Implemented | Multiple `MATCH` clauses extend the binding scope; earlier bindings are in scope for later clauses. | |

#### Future
Consider whether `OPTIONAL MATCH`, `WITH`, and aggregation are needed after the first round of
graph and naming use cases is implemented.


### gryphon Storage Form
----
RID: `req-grid-traversal-lang-storage`
Status: `Implemented`

gryphon text should be easy to store in JSON-backed definitions without requiring embedded
newlines when they are inconvenient.

#### Implementation

The canonical storage surface allows either:

- a single `string` for single-line gryphon expressions
- a `list[str]` for multi-line gryphon expressions, preserving clause order line by line

Equivalent examples:

```json
{
  "query": "MATCH (hub)-[e]-(neighbor) WHERE hub.entity_id = $entity_id RETURN hub, e, neighbor"
}
```

```json
{
  "query": [
    "MATCH (hub)-[e]-(neighbor)",
    "WHERE hub.entity_id = $entity_id",
    "RETURN hub, e, neighbor"
  ]
}
```

Execution normalizes both forms into one canonical string before parsing.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-traversal-lang-storage-1 | Single-Line String Allowed | Implemented | gryphon definitions may be stored as a single string. | |
| req-grid-traversal-lang-storage-2 | Multi-Line List Allowed | Implemented | gryphon definitions may be stored as an ordered list of strings. | |
| req-grid-traversal-lang-storage-3 | Forms Normalize Equivalently | Implemented | TAP normalizes string and list forms into the same executable gryphon meaning. | |

#### Future
If authoring tools later need per-line metadata such as comments or diagnostics, TAP may add an
enriched editor format while keeping these two storage forms valid.


### Pattern And Binding Syntax
----
RID: `req-grid-traversal-lang-patterns`
Status: `Implemented`

gryphon patterns describe node and edge shape, direction, repetition, and named bindings using
Cypher-like syntax.

#### Implementation

V1 pattern syntax supports:

- node patterns: `(n)` or `(n:host)`
- edge patterns: `-[e]->`, `<-[e]-`, `-[e]-`
- typed edges: `-[e:ON_HOST]->`
- anonymous edges: `-[]->` or `-->`
- inline property maps on nodes and edges: `(n:host {name: "web01"})`
- path bindings: `p = (a)-[:EDGE]->(b)`
- bounded traversal: `-[e:EDGE_TYPE*1..3]->`
- anonymous bounded traversal: `-[*1..3]-`
- wildcard matching by omission of label, type, variable, or direction constraint

```text
MATCH (port:port)-[:ON_INTERFACE]->(iface:interface)-[:ON_HOST]->(host:host)
```

```text
MATCH p = (src)-[rel*1..2]-(dst)
```

```text
MATCH (server:host)<-[edge:ON_HOST]-(iface:interface)
```

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-traversal-lang-patterns-1 | Supports Node Variables And Labels | Implemented | Node patterns may declare a variable and label. | |
| req-grid-traversal-lang-patterns-2 | Supports Edge Variables And Types | Implemented | Edge patterns may declare a variable and edge type. | |
| req-grid-traversal-lang-patterns-3 | Supports Directed And Undirected Edges | Implemented | gryphon patterns support `out`, `in`, and undirected graph shape. | |
| req-grid-traversal-lang-patterns-4 | Supports Path Variables | Implemented | Entire matched paths may be bound to named variables. | |
| req-grid-traversal-lang-patterns-5 | Supports Bounded Repetition | Implemented | gryphon patterns support bounded hop repetition such as `*1..3`. | |
| req-grid-traversal-lang-patterns-6 | Supports Anonymous Repeated Edges | Implemented | Bounded traversal may omit edge variable and edge type. | |
| req-grid-traversal-lang-patterns-7 | Supports Wildcards By Omission | Implemented | Unspecified node labels or edge types behave as wildcards within TAP scope. | |

#### Future
Consider subgraph-scoped gryphon composition, where one gryphon result becomes the graph
scope for a later gryphon expression. Defer until a concrete use case appears — this expands planner
and result-scope semantics significantly.

Consider a compile-time maximum hop depth cap for safety and performance. Unbounded depth on a
production graph is potentially expensive. Defer until operational experience defines an
appropriate limit.


### Field And Predicate Semantics
----
RID: `req-grid-traversal-lang-filters`
Status: `Implemented`

gryphon text must support matching and filtering on TAP object-model fields, including
JSON-backed structures.

#### Implementation

Filtering is available in two places:

- inline property maps on node and edge patterns: `(n:host {name: "web01"})`
- explicit `WHERE` predicates over bound variables

Dot notation accesses model fields from a bound variable:

- `host.name`
- `host.entity_id`
- `edge.properties.kind`

JSON-friendly access patterns:

- keyed lookup: `node.dimensions["tap.graph"]`
- positional lookup: `node.properties.aliases[0].name`
- array wildcard: `node.properties.aliases[*].name`

Array wildcard semantics: `[*]` means "any member of this array"; a comparison against a `[*]`
path is true when at least one member satisfies the predicate.

```text
MATCH (n:host)
WHERE n.dimensions["tap.graph"] = "web"
RETURN n
```

```text
MATCH (n:host)
WHERE n.properties.aliases[*].name = $alias
RETURN n.entity_id, n.name
```

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-traversal-lang-filters-1 | Inline Property Maps Supported | Implemented | Node and edge patterns may include inline property filters; values are AND'd into the queryset for the bound pattern. | Edge-side filter implementation at `tap_grid/gryphon/executor.py::_apply_inline_edge_property_filters` (closes Gap 1). Verified by tests in `tap_grid/tests/test_gryphon_inline_edge_filter.py`. |
| req-grid-traversal-lang-filters-2 | Where Predicates Supported | Implemented | gryphon text supports `WHERE` predicates over bound variables. | |
| req-grid-traversal-lang-filters-3 | Dot Field Access Supported | Implemented | Predicates may access object-model fields with dot notation (single step). | Multi-step paths into JSON fields are deferred to `req-grid-traversal-lang-filters-jsonpath`. |
| req-grid-traversal-lang-filters-4 | Keyed Json Access Supported | Backlog | Predicates may access JSON keys using bracket notation. | Subsumed by [JSONPath For JSON Field Predicates](#jsonpath-for-json-field-predicates) (`req-grid-traversal-lang-filters-jsonpath`). The executor currently rejects multi-step paths with a clear `WHERE predicates support single dot-step field paths only.` error. |
| req-grid-traversal-lang-filters-5 | Positional Array Access Supported | Backlog | Predicates may address array members by numeric index. | Subsumed by [JSONPath For JSON Field Predicates](#jsonpath-for-json-field-predicates). |
| req-grid-traversal-lang-filters-6 | Array Wildcard Access Supported | Backlog | Predicates may use `[*]` to mean "any array member". | Subsumed by [JSONPath For JSON Field Predicates](#jsonpath-for-json-field-predicates). |

#### Future
Consider adding `IN`, `EXISTS`, and collection functions once enough real queries demonstrate
the need.


### JSONPath For JSON Field Predicates
----
RID: `req-grid-traversal-lang-filters-jsonpath`
Status: `Proposed`

`WHERE` predicates that need to reach into JSON-backed fields (`Edge.properties`, `BaseModel.dimensions`, model-level JSON columns like `configuration` / `properties`) should adopt **JSONPath ([RFC 9535](https://www.rfc-editor.org/rfc/rfc9535.html))** as the canonical path syntax rather than continue evolving an in-house dot/bracket grammar.

#### Background And Motivation

The currently-shipping executor enforces "single dot-step field paths only" in `WHERE` (`tap_grid/gryphon/executor.py::_apply_comparison`). Multi-step paths into JSON fields — `r.properties.relationship_type`, `n.properties.aliases[*].name`, `n.dimensions["tap.graph"]` — all error out, even though three of them are listed as `Implemented` in the ACID table above. That status discrepancy was discovered during Gap 1 mop-up; this requirement realigns the spec with reality and proposes a path forward that does not require us to invent and maintain a JSONPath equivalent.

JSONPath is preferred over the alternatives because:

- **First-class Postgres support.** Postgres has had `jsonb_path_query`, `jsonb_path_match`, and the `@?` / `@@` operators since version 12. They take a JSONPath string verbatim and evaluate it server-side. We do not need to compile, translate, or interpret the path expression in Python — we thread it through to the database.
- **IETF-standardized.** RFC 9535 (2024) settled what had been a defacto standard for ~15 years. Multiple mature implementations exist in every language we'd plausibly target.
- **Spec gets shorter, not longer.** Instead of documenting our half-working dot/bracket grammar (filters-4/5/6 above), we cite RFC 9535 once and inherit its semantics, including filter expressions like `[?(@.kind == "primary")]` that would otherwise be a year of additional grammar work.

The candidates considered and rejected:

- **JMESPath** (used by AWS CLI, Ansible) — clean grammar but no Postgres native support; we'd be writing the same compiler we're trying to avoid.
- **JSON Pointer** (RFC 6901) — path-only, no filter or wildcard capability; too limited.

#### Implementation

The implementation surface is the `WHERE` compiler in `tap_grid/gryphon/executor.py`. The work is:

1. **Recognize JSON-field paths.** When the first step of a dot/bracket path resolves to a `JSONField` on the bound model (`Edge.properties`, `Entity.dimensions`, `BaseModel.<json_column>`), do not attempt native column traversal. Capture the remainder of the path.
2. **Translate to JSONPath.** Map the captured remainder onto a JSONPath expression rooted at `$`. Examples:
   - `r.properties.relationship_type` → `$.relationship_type`
   - `n.dimensions["tap.graph"]` → `$["tap.graph"]`
   - `n.properties.aliases[0].name` → `$.aliases[0].name`
   - `n.properties.aliases[*].name = $alias` → `$.aliases[*].name == "<value>"` inside `jsonb_path_match`
3. **Emit the SQL.** Use Django's `RawSQL` or a custom queryset annotation that calls `properties @@ '<path expr>'::jsonpath` (or `@?` for existence-only). Bind `$alias` parameters into the JSONPath expression safely, not via string interpolation.
4. **Backend gate.** Behind a backend-detection check so future non-Postgres backends fall through to a Python-side evaluator using a JSONPath library (e.g. `jsonpath-ng`) rather than failing.

The dotted gryphon syntax that authors already write (`r.properties.relationship_type`) stays valid — the compiler maps it to JSONPath under the hood. Authors who prefer JSONPath directly can write `r @@ "$.relationship_type == \"violation\""` once that surface is added.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-traversal-lang-filters-jsonpath-1 | JSON Field Detection | Proposed | The compiler identifies JSON-field paths by inspecting the bound model's field types and routes them to JSONPath translation. | |
| req-grid-traversal-lang-filters-jsonpath-2 | Dotted Path Translates To JSONPath | Proposed | Existing `properties.<key>` and `properties.<key>.<key>` dotted forms compile to equivalent JSONPath expressions and are evaluated by Postgres `jsonb_path_match`. | Subsumes filters-4. |
| req-grid-traversal-lang-filters-jsonpath-3 | Bracketed Keys Supported | Proposed | `dimensions["tap.graph"]` and similar bracket-key forms compile to `$["tap.graph"]`. | Subsumes filters-4. |
| req-grid-traversal-lang-filters-jsonpath-4 | Positional Array Access | Proposed | `properties.aliases[0].name` compiles to `$.aliases[0].name`. | Subsumes filters-5. |
| req-grid-traversal-lang-filters-jsonpath-5 | Array Wildcard Access | Proposed | `properties.aliases[*].name = $alias` compiles to a JSONPath expression evaluated server-side; semantics: predicate is true when at least one array member satisfies the comparison. | Subsumes filters-6. |
| req-grid-traversal-lang-filters-jsonpath-6 | Bind Params Are Quoted Safely | Proposed | `$param` references in gryphon `WHERE` are inlined into JSONPath expressions through parameterized placeholders, not string concatenation. | Security-relevant; prevents jsonpath injection. |
| req-grid-traversal-lang-filters-jsonpath-7 | Spec References RFC 9535 | Proposed | The spec text replaces the in-house dot/bracket grammar prose with a citation to RFC 9535 as the authority for path syntax. | |

#### Future

- A second surface that lets authors write JSONPath directly in `WHERE` (e.g. `r @@ "$.relationship_type == \"violation\""`) once the translation path is stable.
- Support for non-Postgres backends via a Python-side JSONPath evaluator. Out of scope until a second backend exists.
- Expanding `[*]` semantics to support `ALL` (all members satisfy) in addition to the default `ANY` (at least one satisfies). Worth a separate ACID once a real query demands it.


### Predicate Combinators
----
RID: `req-grid-traversal-lang-combinators`
Status: `Implemented`

gryphon `WHERE` predicates may be combined using `AND`, `OR`, and `NOT`. Parentheses may be used to
control grouping explicitly.

#### Implementation

Supported combinators:

- `AND` — both operands must be true
- `OR` — either operand must be true
- `NOT` — negates a single predicate
- Parentheses for explicit grouping: `(a AND b) OR c`

All keywords are case-insensitive.

```text
MATCH (n:host)
WHERE n.entity_id = $entity_id AND n.dimensions["tap.graph"] = "web"
RETURN n
```

```text
MATCH (n:host)
WHERE NOT n.name = "excluded" OR n.entity_id = $entity_id
RETURN n
```

Precedence (highest to lowest): `NOT` > `AND` > `OR`. Parentheses override precedence.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-traversal-lang-combinators-1 | AND Supported | Implemented | `WHERE` predicates support `AND` to require both operands. | |
| req-grid-traversal-lang-combinators-2 | OR Supported | Implemented | `WHERE` predicates support `OR` to accept either operand. | |
| req-grid-traversal-lang-combinators-3 | NOT Supported | Implemented | `WHERE` predicates support `NOT` to negate a single predicate. | |
| req-grid-traversal-lang-combinators-4 | Grouping With Parens | Implemented | Parentheses may be used to override default precedence. | |

#### Future
Add `XOR` if a concrete use case demonstrates the need.


### Runtime Inputs And Variables
----
RID: `req-grid-traversal-lang-params`
Status: `Implemented`

gryphon text should be parameterizable and bind reusable names for nodes, edges, and paths.

#### Implementation

Runtime inputs use `$var` syntax:

- `$entity_id`
- `$port_name`
- `$alias`

Bound names may be introduced for nodes, edges, and paths within `MATCH` patterns. gryphon
storage and execution treat runtime inputs separately from the gryphon text itself. Input values
are provided by the search service or another TAP-controlled caller and validated against an
input schema when one is declared on the Search object.

```text
MATCH p = (port:port)-[:ON_INTERFACE]->(iface:interface)-[:ON_HOST]->(host:host)
WHERE port.name = $port_name
RETURN p, host
```

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-traversal-lang-params-1 | Supports Dollar Variables | Implemented | Runtime inputs use `$var` syntax within gryphon text. | |
| req-grid-traversal-lang-params-2 | Supports Node Edge And Path Variables | Implemented | Traversal matching may bind names for nodes, edges, and entire paths. | |
| req-grid-traversal-lang-params-3 | Inputs Are Supplied Separately | Implemented | Runtime values are provided separately from stored traversal text. | |

#### Future
If TAP later needs default parameter values or parameter typing inline in gryphon text,
define that separately rather than overloading `$var`.


### Return Semantics
----
RID: `req-grid-traversal-lang-returns`
Status: `Implemented`

gryphon supports projection of matched bindings. The default result packaging is a graph envelope
of matched nodes and edges. Including an explicit `RETURN` clause signals that the caller wants
row projection rather than a graph envelope.

#### Implementation

**Default (RETURN omitted):** TAP returns a graph envelope: `{"nodes": [...], "edges": [...]}`.
All matched node and edge variables are included. This is the standard result for graph panels,
neighborhood lookups, and any consumer that drives Cytoscape or a graph visualization.

**Explicit RETURN:** Signals row projection mode. `RETURN` may reference:

- node variables
- edge variables
- path variables
- field projections: `host.name`, `host.entity_id`
- aliased return expressions: `host.name AS accepted_name`

```text
RETURN host
```

```text
RETURN p, host.entity_id, host.name
```

```text
RETURN host.name AS accepted_name, iface.entity_id AS source_interface
```

Execution packaging (graph envelope vs row projection vs other shapes) remains TAP-controlled.
The `RETURN` clause describes what values are requested from the match; it does not define the
wire format.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-traversal-lang-returns-1 | Omitted Return Is Graph Envelope | Implemented | When `RETURN` is omitted, TAP returns a graph envelope of all matched nodes and edges. | |
| req-grid-traversal-lang-returns-2 | Explicit Return Signals Row Projection | Implemented | Including `RETURN` signals that the caller wants projected row results rather than a full graph envelope. | |
| req-grid-traversal-lang-returns-3 | Supports Variable Returns | Implemented | `RETURN` may include node, edge, and path variables. | |
| req-grid-traversal-lang-returns-4 | Supports Field Projection | Implemented | `RETURN` may include specific fields from bound variables. | |
| req-grid-traversal-lang-returns-5 | Supports Named Return Aliases | Implemented | `RETURN` may rename returned values using `AS`. | |
| req-grid-traversal-lang-returns-6 | Packaging Remains Tap-Controlled | Implemented | Traversal text does not redefine TAP's canonical execution packaging contract. | |

#### Future
Aggregation and ordering within `RETURN` should be considered only after base traversal
execution semantics are stable.


## Status Vocabulary

| Status States |  |
| --- | --- |
| Proposed |  |
| Implemented | Requirement is accepted and ready to be implemented |
| In Development |  |
| Implemented |  |
| Verified |  |
| Refactoring |  |
| Deprecating |  |
| Deprecated | Not part of the current architecture and should not be implemented |
