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
| req-grid-traversal-lang-shape | [Traversal Language Shape](#traversal-language-shape) | Approved for Development | MATCH/WHERE/RETURN clause structure |
| req-grid-traversal-lang-storage | [Traversal Storage Form](#traversal-storage-form) | Approved for Development | String and list[str] storage forms |
| req-grid-traversal-lang-patterns | [Pattern And Binding Syntax](#pattern-and-binding-syntax) | Approved for Development | Node/edge/path patterns, direction, bounded traversal |
| req-grid-traversal-lang-filters | [Field And Predicate Semantics](#field-and-predicate-semantics) | Approved for Development | Inline filters and WHERE predicates over model and JSON fields |
| req-grid-traversal-lang-combinators | [Predicate Combinators](#predicate-combinators) | Approved for Development | AND/OR/NOT in WHERE predicates |
| req-grid-traversal-lang-params | [Runtime Inputs And Variables](#runtime-inputs-and-variables) | Approved for Development | $var runtime inputs and named pattern bindings |
| req-grid-traversal-lang-returns | [Return Semantics](#return-semantics) | Approved for Development | RETURN projection and graph envelope default |


### gryphon Language Shape
----
RID: `req-grid-traversal-lang-shape`
Status: `Approved for Development`

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
| req-grid-traversal-lang-shape-1 | Supports Match Clause | Approved for Development | gryphon text supports `MATCH` as the primary pattern-binding clause. | |
| req-grid-traversal-lang-shape-2 | Supports Where Clause | Approved for Development | gryphon text supports `WHERE` predicates over bound variables and fields. | |
| req-grid-traversal-lang-shape-3 | Supports Return Clause | Approved for Development | gryphon text supports `RETURN` for named variables and projected fields. | |
| req-grid-traversal-lang-shape-4 | Read-Only Surface Only | Approved for Development | V1 gryphon text excludes graph mutation clauses; they are rejected at parse time. | |
| req-grid-traversal-lang-shape-5 | Multiple Match Compositional | Approved for Development | Multiple `MATCH` clauses extend the binding scope; earlier bindings are in scope for later clauses. | |

#### Future
Consider whether `OPTIONAL MATCH`, `WITH`, and aggregation are needed after the first round of
graph and naming use cases is implemented.


### gryphon Storage Form
----
RID: `req-grid-traversal-lang-storage`
Status: `Approved for Development`

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
| req-grid-traversal-lang-storage-1 | Single-Line String Allowed | Approved for Development | gryphon definitions may be stored as a single string. | |
| req-grid-traversal-lang-storage-2 | Multi-Line List Allowed | Approved for Development | gryphon definitions may be stored as an ordered list of strings. | |
| req-grid-traversal-lang-storage-3 | Forms Normalize Equivalently | Approved for Development | TAP normalizes string and list forms into the same executable gryphon meaning. | |

#### Future
If authoring tools later need per-line metadata such as comments or diagnostics, TAP may add an
enriched editor format while keeping these two storage forms valid.


### Pattern And Binding Syntax
----
RID: `req-grid-traversal-lang-patterns`
Status: `Approved for Development`

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
| req-grid-traversal-lang-patterns-1 | Supports Node Variables And Labels | Approved for Development | Node patterns may declare a variable and label. | |
| req-grid-traversal-lang-patterns-2 | Supports Edge Variables And Types | Approved for Development | Edge patterns may declare a variable and edge type. | |
| req-grid-traversal-lang-patterns-3 | Supports Directed And Undirected Edges | Approved for Development | gryphon patterns support `out`, `in`, and undirected graph shape. | |
| req-grid-traversal-lang-patterns-4 | Supports Path Variables | Approved for Development | Entire matched paths may be bound to named variables. | |
| req-grid-traversal-lang-patterns-5 | Supports Bounded Repetition | Approved for Development | gryphon patterns support bounded hop repetition such as `*1..3`. | |
| req-grid-traversal-lang-patterns-6 | Supports Anonymous Repeated Edges | Approved for Development | Bounded traversal may omit edge variable and edge type. | |
| req-grid-traversal-lang-patterns-7 | Supports Wildcards By Omission | Approved for Development | Unspecified node labels or edge types behave as wildcards within TAP scope. | |

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
Status: `Approved for Development`

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
| req-grid-traversal-lang-filters-1 | Inline Property Maps Supported | Approved for Development | Node and edge patterns may include inline property filters. | |
| req-grid-traversal-lang-filters-2 | Where Predicates Supported | Approved for Development | gryphon text supports `WHERE` predicates over bound variables. | |
| req-grid-traversal-lang-filters-3 | Dot Field Access Supported | Approved for Development | Predicates may access object-model fields with dot notation. | |
| req-grid-traversal-lang-filters-4 | Keyed Json Access Supported | Approved for Development | Predicates may access JSON keys using bracket notation. | |
| req-grid-traversal-lang-filters-5 | Positional Array Access Supported | Approved for Development | Predicates may address array members by numeric index. | |
| req-grid-traversal-lang-filters-6 | Array Wildcard Access Supported | Approved for Development | Predicates may use `[*]` to mean "any array member". | |

#### Future
Consider adding `IN`, `EXISTS`, and collection functions once enough real queries demonstrate
the need.


### Predicate Combinators
----
RID: `req-grid-traversal-lang-combinators`
Status: `Approved for Development`

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
| req-grid-traversal-lang-combinators-1 | AND Supported | Approved for Development | `WHERE` predicates support `AND` to require both operands. | |
| req-grid-traversal-lang-combinators-2 | OR Supported | Approved for Development | `WHERE` predicates support `OR` to accept either operand. | |
| req-grid-traversal-lang-combinators-3 | NOT Supported | Approved for Development | `WHERE` predicates support `NOT` to negate a single predicate. | |
| req-grid-traversal-lang-combinators-4 | Grouping With Parens | Approved for Development | Parentheses may be used to override default precedence. | |

#### Future
Add `XOR` if a concrete use case demonstrates the need.


### Runtime Inputs And Variables
----
RID: `req-grid-traversal-lang-params`
Status: `Approved for Development`

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
| req-grid-traversal-lang-params-1 | Supports Dollar Variables | Approved for Development | Runtime inputs use `$var` syntax within gryphon text. | |
| req-grid-traversal-lang-params-2 | Supports Node Edge And Path Variables | Approved for Development | Traversal matching may bind names for nodes, edges, and entire paths. | |
| req-grid-traversal-lang-params-3 | Inputs Are Supplied Separately | Approved for Development | Runtime values are provided separately from stored traversal text. | |

#### Future
If TAP later needs default parameter values or parameter typing inline in gryphon text,
define that separately rather than overloading `$var`.


### Return Semantics
----
RID: `req-grid-traversal-lang-returns`
Status: `Approved for Development`

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
| req-grid-traversal-lang-returns-1 | Omitted Return Is Graph Envelope | Approved for Development | When `RETURN` is omitted, TAP returns a graph envelope of all matched nodes and edges. | |
| req-grid-traversal-lang-returns-2 | Explicit Return Signals Row Projection | Approved for Development | Including `RETURN` signals that the caller wants projected row results rather than a full graph envelope. | |
| req-grid-traversal-lang-returns-3 | Supports Variable Returns | Approved for Development | `RETURN` may include node, edge, and path variables. | |
| req-grid-traversal-lang-returns-4 | Supports Field Projection | Approved for Development | `RETURN` may include specific fields from bound variables. | |
| req-grid-traversal-lang-returns-5 | Supports Named Return Aliases | Approved for Development | `RETURN` may rename returned values using `AS`. | |
| req-grid-traversal-lang-returns-6 | Packaging Remains Tap-Controlled | Approved for Development | Traversal text does not redefine TAP's canonical execution packaging contract. | |

#### Future
Aggregation and ordering within `RETURN` should be considered only after base traversal
execution semantics are stable.


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
