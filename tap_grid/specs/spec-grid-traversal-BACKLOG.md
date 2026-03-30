# Grid Traversal Specification -DRAFT

## Philosophy

TAP needs a compact, graph-native language for describing traversals as durable configuration rather than scattering ad hoc Python, ORM fragments, or SQL across panels, alias rules, and future AI-generated query definitions.

This language should feel familiar to anyone who has seen Cypher while remaining intentionally smaller and easier to reason about. The goal is not full Cypher compatibility. The goal is a TAP-native traversal representation that is concise enough to store as strings, expressive enough to describe real graph walks, and constrained enough to compile safely into TAP-controlled execution plans.

Traversal expressions are meant to describe graph shape, binding, filtering, and projection. They are not the same thing as execution packaging. A traversal may later be executed in graph-envelope mode, projected row mode, or another TAP-defined result mode without changing the traversal text itself.

## Goals

|    |              |                                                                                      |
| :---: | ---       | ---                                                                                  |
| 1. | Compact       | Represent common graph traversals in a short string-friendly form                    |
| 2. | Familiar      | Reuse Cypher-like shape and notation where it improves readability                   |
| 3. | Reusable      | Support storage on Search objects, alias rules, naming policies, and panel config    |
| 4. | Safe          | Keep the language narrow enough to compile into TAP-controlled read-only execution    |
| 5. | Parameterized | Support runtime inputs and named bindings without requiring query text rewriting      |
| 6. | Graph-Native  | Express graph walks, path bindings, and graph-field filters directly                 |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-grid-traversal-shape | [Traversal Language Shape](#traversal-language-shape) | Proposed | Cypher-like textual form with `MATCH`, `WHERE`, and `RETURN` |
| req-grid-traversal-storage | [Traversal Storage Form](#traversal-storage-form) | Proposed | Traversals may be stored as a string or list of lines |
| req-grid-traversal-patterns | [Pattern And Binding Syntax](#pattern-and-binding-syntax) | Proposed | Supports node, edge, path, direction, wildcards, and bounded traversal |
| req-grid-traversal-filters | [Field And Predicate Semantics](#field-and-predicate-semantics) | Proposed | Supports inline property filters and `WHERE` predicates over model and JSON fields |
| req-grid-traversal-params | [Runtime Inputs And Variables](#runtime-inputs-and-variables) | Proposed | Supports `$var` runtime inputs and named pattern variables |
| req-grid-traversal-returns | [Return Semantics](#return-semantics) | Proposed | Supports projection of paths, objects, fields, and named expressions |
| req-grid-traversal-exec | [Execution Contract](#execution-contract) | Proposed | TAP compiles traversal text into a read-only execution plan |
| req-grid-traversal-scope.sec | [Traversal Safety Scope](#traversal-safety-scope) | Proposed | Traversal compilation and execution remain TAP-scoped and read-only |

## Explanation

Traversal is the compact graph representation TAP can use when the important thing is the path itself:

- neighborhood lookups such as "everything connected one hop away"
- alias and accepted naming path declarations
- reverse-path handshake rules
- panel and perspective graph walks
- future AI-authored saved searches

This specification deliberately separates:

| Concept | Meaning |
| --- | --- |
| Traversal text | The compact path/query expression stored in TAP |
| Traversal bindings | Named variables bound during matching |
| Execution plan | TAP-controlled compiled form used for ORM, SQL, or future engines |
| Result packaging | TAP-level choice of graph envelope, projection rows, or another result shape |

The traversal language should be pleasant to read in strings while still being structured enough to parse into a predictable AST.

### Traversal Language Shape
----
RID: `req-grid-traversal-shape`
Status: `Proposed`

TAP traversal text uses a Cypher-compatible clause style for the core read/traversal surface.

#### Status Details
Proposed. This requirement establishes the compact textual form before choosing a concrete compiler backend.

#### Implementation
The first traversal language should support these top-level clauses:

- `MATCH`
- `WHERE`
- `RETURN`

Multiple `MATCH` clauses are allowed. Clauses are evaluated in order as part of a single traversal statement.

The first version is intentionally read-only. It does not include write clauses such as `CREATE`, `MERGE`, `SET`, or `DELETE`.

Suggested examples:

```text
MATCH p = (port:port)-[:ON_INTERFACE]->(iface:interface)-[:ON_HOST]->(host:host)
WHERE port.name = $port_name
RETURN p, host.entity_id, host.name
```

```text
MATCH n = (hub)-[edge]-(neighbor)
WHERE hub.entity_id = $entity_id
RETURN n, hub, edge, neighbor
```

#### Development
Using a Cypher-like clause shape gives TAP a readable and compact representation without committing TAP to implement every feature of Cypher.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-traversal-shape-1 | Supports Match Clause | Proposed | Traversal text supports `MATCH` as the primary pattern-binding clause. | |
| req-grid-traversal-shape-2 | Supports Where Clause | Proposed | Traversal text supports `WHERE` predicates over bound variables and fields. | |
| req-grid-traversal-shape-3 | Supports Return Clause | Proposed | Traversal text supports `RETURN` for named variables and projected fields. | |
| req-grid-traversal-shape-4 | Read-Only Surface Only | Proposed | V1 traversal text excludes graph mutation clauses. | |

#### Future
Consider whether `OPTIONAL MATCH`, `WITH`, and aggregation are needed after the first round of graph and naming use cases is implemented.

### Traversal Storage Form
----
RID: `req-grid-traversal-storage`
Status: `Proposed`

Traversal text should be easy to store in JSON-backed definitions without requiring embedded newlines when they are inconvenient.

#### Status Details
Proposed. This requirement captures the preferred authoring/storage ergonomics for Search and policy objects.

#### Implementation
The canonical storage surface should allow either:

- a single `string` for single-line traversals
- a `list[str]` for multi-line traversals, preserving clause order line by line

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

Execution should normalize both forms into one canonical internal string or parsed token stream before compilation.

#### Development
This keeps traversal definitions easy to store on Search objects and other JSON-backed policy surfaces without making authors fight escaped newlines.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-traversal-storage-1 | Single-Line String Allowed | Proposed | Traversal definitions may be stored as a single string. | |
| req-grid-traversal-storage-2 | Multi-Line List Allowed | Proposed | Traversal definitions may be stored as an ordered list of strings. | |
| req-grid-traversal-storage-3 | Forms Normalize Equivalently | Proposed | TAP normalizes string and list forms into the same executable traversal meaning. | |

#### Future
If authoring tools later need per-line metadata such as comments or diagnostics, TAP may add an enriched editor format while keeping these two storage forms valid.

### Pattern And Binding Syntax
----
RID: `req-grid-traversal-patterns`
Status: `Proposed`

Traversal patterns describe node and edge shape, direction, repetition, and named bindings using Cypher-like syntax.

#### Status Details
Proposed as the core language surface for graph walking.

#### Implementation
V1 pattern syntax should support:

- node patterns: `(n)` or `(n:host)`
- multiple labels if TAP later needs them, but a single label is sufficient for initial implementation
- edge patterns: `-[e]->`, `<-[e]-`, `-[e]-`
- typed edges: `-[e:ON_HOST]->`
- anonymous edges: `--`, `-->`, `<--`, `-[ ]-` conceptually equivalent when variable/type are omitted
- inline property maps on nodes and edges
- path bindings: `p = (a)-[:EDGE]->(b)`
- bounded traversal: `-[e:EDGE_TYPE*1..3]->`
- anonymous bounded traversal: `-[*1..3]-`
- wildcard matching by omission of label, type, variable, or direction constraint

Examples:

```text
MATCH (port:port)-[:ON_INTERFACE]->(iface:interface)-[:ON_HOST]->(host:host)
```

```text
MATCH p = (src)-[rel*1..2]-(dst)
```

```text
MATCH (server:host)<-[edge:ON_HOST]-(iface:interface)
```

#### Development
The language should stay expressive enough for compact path declaration while avoiding full Cypher features that require a much larger planner.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-traversal-patterns-1 | Supports Node Variables And Labels | Proposed | Node patterns may declare a variable and label. | |
| req-grid-traversal-patterns-2 | Supports Edge Variables And Types | Proposed | Edge patterns may declare a variable and edge type. | |
| req-grid-traversal-patterns-3 | Supports Directed And Undirected Edges | Proposed | Traversal patterns support `out`, `in`, and undirected graph shape. | |
| req-grid-traversal-patterns-4 | Supports Path Variables | Proposed | Entire matched paths may be bound to named variables. | |
| req-grid-traversal-patterns-5 | Supports Bounded Repetition | Proposed | Traversal patterns support bounded hop repetition such as `*1..3`. | |
| req-grid-traversal-patterns-6 | Supports Anonymous Repeated Edges | Proposed | Bounded traversal may omit edge variable and edge type. | |
| req-grid-traversal-patterns-7 | Supports Wildcards By Omission | Proposed | Unspecified node labels or edge types behave as wildcards within TAP scope. | |

#### Future
If TAP later needs path alternation or richer label expressions, add them deliberately rather than implicitly overloading the first syntax.

Consider subgraph-scoped traversal composition, where one traversal executes first and its returned `nodes` / `edges` envelope becomes the graph scope for a later traversal. Defer this until a concrete use case appears. Do not add v1 support ahead of need; this feature would expand planner and result-scope semantics and should be built only when it directly advances an active goal.

### Field And Predicate Semantics
----
RID: `req-grid-traversal-filters`
Status: `Proposed`

Traversal text must support matching and filtering on TAP object-model fields, including JSON-backed structures.

#### Status Details
Proposed. This requirement is one of the major reasons TAP needs more than an ordered hop list.

#### Implementation
Filtering should be available in two places:

- inline property maps on node and edge patterns
- explicit `WHERE` predicates

The language should support field access using dot notation from a bound variable:

- `host.name`
- `host.entity_id`
- `edge.properties.kind`

The language should also support JSON-friendly access patterns:

- keyed lookup: `node.dimensions["tap.graph"]`
- positional lookup: `node.properties.aliases[0].name`
- array wildcard lookup: `node.properties.aliases[*].name`

Array wildcard semantics:
- `[*]` means "any member of this array"
- a comparison against a `[*]` path is true when at least one member satisfies the predicate

Suggested examples:

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

```text
MATCH (n)-[e:HAS_METADATA]->(m)
WHERE e.properties.labels[*] = "external"
RETURN n, e, m
```

#### Development
The filter surface should be expressive enough for real graph/naming work without drifting into an unbounded procedural language.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-traversal-filters-1 | Inline Property Maps Supported | Proposed | Node and edge patterns may include inline property filters. | |
| req-grid-traversal-filters-2 | Where Predicates Supported | Proposed | Traversal text supports `WHERE` predicates over bound variables. | |
| req-grid-traversal-filters-3 | Dot Field Access Supported | Proposed | Predicates may access object-model fields with dot notation. | |
| req-grid-traversal-filters-4 | Keyed Json Access Supported | Proposed | Predicates may access JSON keys using bracket notation. | |
| req-grid-traversal-filters-5 | Positional Array Access Supported | Proposed | Predicates may address array members by numeric index. | |
| req-grid-traversal-filters-6 | Array Wildcard Access Supported | Proposed | Predicates may use `[*]` to mean "any array member". | |

#### Future
Consider adding explicit `IN`, `EXISTS`, and collection functions once enough real queries demonstrate the need.

### Runtime Inputs And Variables
----
RID: `req-grid-traversal-params`
Status: `Proposed`

Traversal text should be parameterizable and bind reusable names for nodes, edges, and paths.

#### Status Details
Proposed. This requirement keeps traversal text stable while allowing different runtime values.

#### Implementation
Runtime inputs use `$var` syntax:

- `$entity_id`
- `$port_name`
- `$alias`

Bound names may be introduced for:

- nodes
- edges
- paths

Examples:

```text
MATCH p = (port:port)-[:ON_INTERFACE]->(iface:interface)-[:ON_HOST]->(host:host)
WHERE port.name = $port_name
RETURN p, host
```

```text
MATCH (hub)-[edge]-(neighbor)
WHERE hub.entity_id = $entity_id
RETURN edge, neighbor.name
```

Traversal storage and execution should treat runtime inputs separately from the traversal text itself. Input values should be provided by the search service or another TAP-controlled caller and validated against a schema when one is declared.

#### Development
This allows TAP to keep durable traversal definitions while still supporting current-node, current-alias, or other context-specific execution.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-traversal-params-1 | Supports Dollar Variables | Proposed | Runtime inputs use `$var` syntax within traversal text. | |
| req-grid-traversal-params-2 | Supports Node Edge And Path Variables | Proposed | Traversal matching may bind names for nodes, edges, and entire paths. | |
| req-grid-traversal-params-3 | Inputs Are Supplied Separately | Proposed | Runtime values are provided separately from stored traversal text. | |

#### Future
If TAP later needs default parameter values or parameter typing inline in the traversal text, define that separately rather than overloading `$var`.

### Return Semantics
----
RID: `req-grid-traversal-returns`
Status: `Proposed`

Traversal text should support compact projection of matched bindings without requiring the traversal language itself to own TAP's full result-packaging contract.

#### Status Details
Proposed. This requirement allows one traversal language to serve graph-panel and naming/resolution use cases.

#### Implementation
`RETURN` may reference:

- node variables
- edge variables
- path variables
- field projections
- aliased return expressions

Examples:

```text
RETURN host
```

```text
RETURN p, host.entity_id, host.name
```

```text
RETURN host.name AS accepted_name, iface.entity_id AS source_interface
```

The traversal language defines what values are requested from the match, but TAP execution remains responsible for packaging results into:

- graph envelope mode
- projection row mode
- future consumer-specific shapes

If `RETURN` is omitted, TAP may define a default projection mode for the execution surface using this traversal. The first implementation should document those defaults per consumer rather than leaving them implicit.

#### Development
Keeping projection syntax in the language but packaging in TAP makes the traversal text reusable across graph-native and scalar-resolution features.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-traversal-returns-1 | Supports Variable Returns | Proposed | `RETURN` may include node, edge, and path variables. | |
| req-grid-traversal-returns-2 | Supports Field Projection | Proposed | `RETURN` may include specific fields from bound variables. | |
| req-grid-traversal-returns-3 | Supports Named Return Aliases | Proposed | `RETURN` may rename returned values using `AS`. | |
| req-grid-traversal-returns-4 | Packaging Remains Tap-Controlled | Proposed | Traversal text does not by itself redefine TAP's canonical execution packaging. | |

#### Future
Aggregation and ordering within `RETURN` should be considered only after base traversal execution semantics are stable.

### Execution Contract
----
RID: `req-grid-traversal-exec`
Status: `Proposed`

Traversal text is compiled by TAP into an internal execution plan and does not execute directly as raw backend code.

#### Status Details
Proposed. This preserves the service-layer control TAP already wants for searches and future AI-authored query definitions.

#### Implementation
Execution flow should be:

1. Normalize stored traversal text from `string` or `list[str]`.
2. Parse the traversal into a TAP AST.
3. Validate labels, edge types, field paths, and runtime inputs.
4. Compile the AST into a TAP execution plan.
5. Execute the plan through a TAP-controlled backend such as SQL, ORM, or another approved engine.
6. Normalize results into the consumer's expected packaging contract.

The compiler backend is intentionally unspecified in this document. TAP may target:

- ORM for simple cases
- SQL for richer graph walks
- another future read-only execution backend

#### Development
This lets TAP adopt a compact traversal language now without prematurely locking the implementation to one backend forever.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-traversal-exec-1 | Traversal Is Parsed Before Execution | Proposed | Traversal text is parsed into TAP-controlled structure before backend execution. | |
| req-grid-traversal-exec-2 | Traversal Is Backend-Agnostic At Rest | Proposed | Stored traversal text is not itself backend-specific SQL or ORM code. | |
| req-grid-traversal-exec-3 | Compilation Produces Tap-Controlled Plan | Proposed | TAP compiles validated traversal text into an internal execution plan. | |

#### Future
Once execution backends stabilize, publish exact lowering rules from traversal syntax into SQL or ORM plans.

### Traversal Safety Scope
----
RID: `req-grid-traversal-scope.sec`
Status: `Proposed`

Traversal execution is a security-sensitive read surface and must remain constrained to TAP-approved graph data and read-only execution.

#### Status Details
Proposed. This requirement mirrors the safety posture already established for search.

#### Implementation
Traversal execution must:

- remain read-only
- stay scoped to TAP-managed graph data
- reject unsupported clauses or functions rather than passing them through
- validate runtime inputs before backend execution
- preserve TAP control over result normalization and execution limits

Traversal text must not be treated as arbitrary SQL, arbitrary Python, or arbitrary database-native graph syntax supplied by the caller.

#### Development
The traversal language is useful partly because it creates a safer trust boundary than direct backend query execution.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-traversal-scope.sec-1 | Read Only | Proposed | Traversal execution does not mutate persisted TAP state. | |
| req-grid-traversal-scope.sec-2 | Tap Scope Only | Proposed | Traversal compilation and execution stay scoped to TAP-approved graph data. | |
| req-grid-traversal-scope.sec-3 | Unsupported Syntax Rejected | Proposed | Unknown or disallowed traversal constructs are rejected explicitly. | |
| req-grid-traversal-scope.sec-4 | Inputs Validated Before Execution | Proposed | Runtime inputs are validated before the backend plan runs. | |

#### Future
Document backend-specific guardrails once TAP chooses its first concrete traversal compiler target.

## Initial Notes

The first implementation should explicitly target these motivating use cases:

- immediate neighborhood traversal for graph panels
- alias offer path declaration
- accepted naming reverse-path declaration
- compact reusable search definitions with runtime inputs

The first implementation should explicitly avoid trying to be "all of Cypher." If a feature does not materially help these use cases, it should be deferred until a real TAP need appears.
