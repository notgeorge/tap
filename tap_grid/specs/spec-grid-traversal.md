# Grid gryphon Specification

## Philosophy

TAP needs a compact, graph-native language for describing traversals as durable configuration
rather than scattering ad hoc Python, ORM fragments, or SQL across panels, alias rules, and
future AI-generated query definitions.

This language is named gryphon, a TAP portmanteau of "grid" and "cypher." gryphon should feel
familiar to anyone who has seen Cypher while remaining intentionally smaller and easier to reason
about. The goal is not full Cypher compatibility. The goal is a TAP-native traversal
representation that is concise enough to store as strings, expressive enough to describe real
graph walks, and constrained enough to compile safely into TAP-controlled execution plans.

gryphon expressions describe graph shape, binding, filtering, and projection. They are not the
same thing as execution packaging. A gryphon expression may be executed in graph-envelope mode,
projected row mode, or another TAP-defined result shape without changing the gryphon text.

## Goals

|    |              |                                                                                      |
| :---: | ---       | ---                                                                                  |
| 1. | Compact       | Represent common graph traversals in a short string-friendly gryphon form            |
| 2. | Familiar      | Reuse Cypher-like shape and notation where it improves readability                   |
| 3. | Reusable      | Support storage on Search objects, alias rules, naming policies, and panel config    |
| 4. | Safe          | Keep gryphon narrow enough to compile into TAP-controlled read-only execution        |
| 5. | Parameterized | Support runtime inputs and named bindings without requiring query text rewriting      |
| 6. | Graph-Native  | Express graph walks, path bindings, and graph-field filters directly                 |

## Sub-Specifications

| Sub-Spec | Status | Description |
| --- | :---: | --- |
| [gryphon Language](spec-grid-traversal-language.md) | Approved for Development | Language surface: clauses, patterns, filters, params, return semantics |
| [gryphon Execution](spec-grid-traversal-execution.md) | Approved for Development | Execution pipeline, compiler strategy, safety scope |

## Requirements Summary

| RID | Sub-Spec | Status | Notes |
| --- | --- | :---: | --- |
| req-grid-traversal-lang-shape | [Language](spec-grid-traversal-language.md#traversal-language-shape) | Approved for Development | MATCH/WHERE/RETURN clause structure |
| req-grid-traversal-lang-storage | [Language](spec-grid-traversal-language.md#traversal-storage-form) | Approved for Development | String and list[str] storage forms |
| req-grid-traversal-lang-patterns | [Language](spec-grid-traversal-language.md#pattern-and-binding-syntax) | Approved for Development | Node/edge/path patterns, direction, bounded traversal |
| req-grid-traversal-lang-filters | [Language](spec-grid-traversal-language.md#field-and-predicate-semantics) | Approved for Development | Dot/bracket/wildcard field access, inline property maps |
| req-grid-traversal-lang-combinators | [Language](spec-grid-traversal-language.md#predicate-combinators) | Approved for Development | AND/OR/NOT predicate combinators |
| req-grid-traversal-lang-params | [Language](spec-grid-traversal-language.md#runtime-inputs-and-variables) | Approved for Development | $var runtime inputs and named bindings |
| req-grid-traversal-lang-returns | [Language](spec-grid-traversal-language.md#return-semantics) | Approved for Development | RETURN projection and graph envelope default |
| req-grid-traversal-exec-pipeline | [Execution](spec-grid-traversal-execution.md#execution-pipeline) | Approved for Development | Normalize → parse → validate → compile → execute → package |
| req-grid-traversal-exec-compiler | [Execution](spec-grid-traversal-execution.md#compiler-strategy) | Approved for Development | lark as v1 parser; grammar.lark is the spec artifact |
| req-grid-traversal-exec-scope.sec | [Execution](spec-grid-traversal-execution.md#traversal-safety-scope) | Approved for Development | Read-only, TAP-scoped, unsupported syntax rejected |

## Explanation

gryphon is the compact graph representation TAP uses when the important thing is the path itself:

- neighborhood lookups such as "everything connected one hop away"
- alias offer path declaration
- accepted naming reverse-path declaration
- panel and perspective graph walks
- future AI-authored saved searches

This specification deliberately separates:

| Concept | Meaning |
| --- | --- |
| gryphon text | The compact path/query expression stored in TAP |
| gryphon bindings | Named variables bound during matching |
| Execution plan | TAP-controlled compiled form used for ORM, SQL, or future engines |
| Result packaging | TAP-level choice of graph envelope, projection rows, or another result shape |

New gryphon capabilities (aggregation, subqueries, time-travel reads) get their own sub-spec
rather than growing the language or execution sub-specs.


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
