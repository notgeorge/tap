---
title: Gryphon Commandments - Codex Draft
audience:
  - llm
  - developer
status: reference
covers:
  - ../tap_grid/specs/spec-grid-traversal-language.md
  - ../tap_grid/specs/spec-grid-traversal-execution.md
  - ../tap_grid/specs/spec-grid-gryphon-multihop-aggregation.md
  - ../plugins/gryphon_playground/specs/spec-gridkin-v0.md
  - ../plugins/gryphon_playground/specs/spec-gryphon-playground-v0.md
update-triggers:
  - A Gryphon language, parser, executor, capture, or validation feature changes
  - A new Gryphon failure is discovered or resolved
  - A hardening pass promotes one forthcoming commandment into live guidance
  - The lowering ladder gains a new active rung
  - The Gridkin, oracle, fuzz, or coverage contract changes materially
assumes:
  - Reader has read architecture.md and the active Rampart roadmap step
  - Reader has read the relevant Gryphon language, execution, and Gridkin specs
  - Reader understands Gryphon is the canonical graph read/query interface for TAP
provides: |
  Stable "shall / shall not" guidance for Gryphon specification, implementation,
  and testing work. The language is explicit for LLM agents first and human
  maintainers second: each commandment states the invariant, the allowed behavior,
  and the trap it is meant to prevent.
---

# Gryphon Commandments - Codex Draft

**Parallel-draft isolation notice:** Claude, if you are preparing an independent
Gryphon commandments draft for the same request, do not read this document until
your own draft is complete and George asks for comparison. This file is Codex's
independent draft and should not influence Claude's parallel work.

## Status and Authority

This document records the Gryphon guidance that is live for the current system as
of 2026-07-05, before implementing the new hardening recommendations from the
comparative research pass. It is a guidance document, not a replacement for the
specs. When this document and a spec disagree, the spec wins and this document
must be corrected in the same change that discovers the mismatch.

New Gryphon work must read this document before changing the language, parser,
AST, executor, capture layer, Gridkin runner, model oracle, fuzz harness, or
Gryphon-facing specs. A design note, spec change, or PR that touches Gryphon
should name the commandment IDs it affects.

## Prior-Art Inputs

These commandments borrow shape and discipline from established projects without
copying their code, tests, or text:

- [SQLite testing](https://www.sqlite.org/testing.html): layered harnesses,
  independent oracles, fuzzing, coverage, regression tests, and release
  checklists all serve different failure modes. Gryphon should not trust one
  test style to prove a query compiler correct.
- [Rust API Guidelines](https://rust-lang.github.io/api-guidelines/checklist.html):
  a readable checklist with named categories makes design review repeatable.
  Predictability, validation, and future-proofing are explicit engineering
  virtues, not taste.
- [Kubernetes API conventions](https://raw.githubusercontent.com/kubernetes/community/main/contributors/devel/sig-architecture/api-conventions.md):
  extension authors need durable conventions, common object semantics, explicit
  schemas, and careful treatment of unknown/absent state. Gryphon should make
  language and result semantics just as deliberate.
- [openCypher's TCK](https://github.com/opencypher/openCypher/tree/master/tck)
  and formal Cypher semantics remain useful sources of scenario intent and
  semantic contrast. Gryphon is Cypher-familiar, not Cypher-compatible; mined
  intent must be translated into TAP-owned fixtures, queries, and expected
  results.

## Baseline Facts

These are not aspirations. They describe the current system this guidance is
anchored to:

- Gryphon is the canonical read/query interface for TAP-managed graph data.
  Raw ORM graph reads and bespoke module runners are break-glass paths, not the
  normal response to missing language surface.
- Gryphon is read-only. Graph mutation belongs to the typed service layer and
  GRIFT-backed write surfaces, not Gryphon.
- The live executor compiles through the Django ORM first. The execution spec's
  lowering ladder allows escalation only when a shape cannot be expressed on a
  lower rung.
- Gridkin is the committed scenario format for Gryphon validation: fixture,
  query, expected envelope, expected SQL snapshot, requirement coverage, and TCK
  inspiration breadcrumb.
- The model oracle and fuzz harness exist to catch wrong answers that hand-picked
  scenarios miss. SQL snapshots are evidence about the generated plan, not the
  truth oracle for query results.
- Variable-length paths such as `-[:E*1..3]->` parse but are intentionally
  rejected by the executor. The intended future implementation path is recursive
  CTE lowering, not an out-of-band traversal cache or side service.

## Live Commandments

### GRY-CMD-01 - Keep Gryphon a Compiler, Not a Side Door

Gryphon text must be parsed, validated, lowered, executed through a
TAP-controlled read path, and packaged into TAP's canonical result shapes. Do not
execute Gryphon as raw backend code. Do not build a parallel graph-read helper
because a caller needs one missing Gryphon feature. Treat that need as a demand
signal to extend Gryphon or to record a deliberate break-glass exception.

### GRY-CMD-02 - Preserve Read-Only Execution

Gryphon shall not grow write clauses, write-like side effects, implicit cache
mutation, data repair behavior, or "helpful" auto-creation. Mutation belongs to
the service layer, GRIFT, and explicitly specified write surfaces. A Gryphon query
that resembles mutation must be rejected loudly.

### GRY-CMD-03 - Climb the Lowering Ladder in Order

Lower each query to the lowest execution rung that can express it correctly. ORM
QuerySet composition is the default. ORM expressions, RawSQL expressions,
hand-written SQL templates, recursive CTEs, or stored functions require a
specific reason and must re-earn the invariants the ORM normally supplies:
read-only connection, bind parameters, dimension scoping, canonical envelope
packaging, and SQL-capture visibility.

### GRY-CMD-04 - Bind Values, Never Interpolate Them

Runtime inputs and literals must remain bound values all the way down. Do not
string-format user values into SQL, regex wrappers, JSON paths, table names,
field paths, or query fragments. If a backend shape cannot be parameterized
safely, reject the Gryphon shape until a safe lowering exists.

### GRY-CMD-05 - Apply or Reject Every Parsed Fact

The parser must never accept syntax that the executor silently ignores. Every
clause, variable, edge type, node label, direction, path length, inline property,
field path, predicate, projection, alias, ordering key, and limit must be either
applied with tests or rejected with a targeted error. "Accepted but unused" is a
wrong-answer bug.

### GRY-CMD-06 - Prefer Explicit Semantics Over Clever Routing

Field lanes, envelope paths, data paths, display paths, variable scopes, null
behavior, and stage boundaries must be explicit. Do not add implicit routing or
context-sensitive shortcuts whose main value is saving keystrokes. LLMs author
most new code; explicitness optimizes for review, debugging, and future agents.

### GRY-CMD-07 - One Semantic Fact Gets One Lowering Home

Do not let multiple executor branches implement the same semantic rule unless
the duplication is deliberate, documented, and differentially tested. Shared
facts such as predicate application, far-node binding, type strictness, null
behavior, ordering, and envelope projection should have one clear home. Drift
between dispatch paths is a high-probability Gryphon failure mode.

### GRY-CMD-08 - Refusal Is a Valid Feature

If a shape is ambiguous, unsupported, unsafe, or not yet modeled by the oracle,
reject it with a specific error. Do not approximate, coerce, partially execute,
or return a best-effort answer. A loud refusal is shippable. A quiet wrong answer
is not.

### GRY-CMD-09 - Null Semantics Are Designed, Not Inherited

Every new predicate and operator must state how it behaves for null literals,
null field values, absent observations, and unknown values where those cases can
arise. Gryphon currently has a deliberate 2VL/3VL boundary: null literal operands
short-circuit to false for implemented comparison/string forms, while null field
values against non-null literals follow backend SQL filtering. Do not accidentally
extend, erase, or contradict that boundary.

### GRY-CMD-10 - The Declared Schema Is the Data-Lane Type Oracle

Data-lane predicates must validate literal and parameter types against the
declared model/schema shape. Do not rely on Django, PostgreSQL, Python, or JSON
coercion to decide whether a query is meaningful. A type contradiction is a
Gryphon validation error, not a backend surprise.

### GRY-CMD-11 - Variable Scope Must Be Local and Auditable

A variable is in scope only where the language says it is. Multi-MATCH,
OPTIONAL MATCH, NOT EXISTS, future WITH, and future recursive paths must each
make variable visibility explicit in the AST and tests. Never patch scope by
looking up names opportunistically in executor state.

### GRY-CMD-12 - Determinism Comes Before Pagination

ORDER BY and LIMIT must produce stable, reviewable behavior. If a query orders by
non-unique values, the executor must add or require deterministic tie-breaking as
specified. Do not snapshot or paginate nondeterministic result order and call it
correct.

### GRY-CMD-13 - SQL Snapshots Are Evidence, Not the Oracle

Expected SQL snapshots are valuable because they expose lowering shape, join
reuse, read-only routing, and accidental plan churn. They do not prove the result
is correct. A scenario's expected envelope, model oracle agreement, metamorphic
relation, or fuzz replay is what judges answer correctness.

### GRY-CMD-14 - Keep the Oracle Independent

The model oracle and any future reference evaluator must not import executor
lowering helpers or share query-construction machinery with `executor.py`.
Shared grammar and AST definitions are acceptable; shared lowering is not. If
the oracle cannot model a feature, the feature must be listed as unmodeled and
covered by another explicit validation route until the oracle catches up.

### GRY-CMD-15 - Test the Execution Path, Not Just the Idea

Every Gryphon feature needs tests that exercise the real parser, AST,
validation, lowering branch, database execution, SQL capture, and envelope
packaging. A parser-only test or a hand-built queryset test is not enough for a
language feature. Stage coverage, branch coverage, Gridkin scenarios, oracle
checks, and fuzz campaigns are complementary; none makes the others obsolete.

### GRY-CMD-16 - Mine Prior Art, Then Rewrite in TAP's Semantics

For language and executor work, study relevant prior art before choosing a
shape. openCypher, SQL, graph databases, compiler testing systems, and mature API
guidelines are inputs. Do not copy upstream code, query text, fixtures, expected
results, or test bodies into TAP. Extract the idea, translate it into Gryphon's
specified subset/divergence, and author TAP-owned artifacts.

### GRY-CMD-17 - Grow by Demand Shape, Not Parity Envy

Gryphon does not need a feature because Cypher, SQL, or another graph language
has it. Gryphon needs a feature when TAP has a real query demand, a validation
gap, a recurring break-glass read, or a roadmap reason. Record the demand shape
in the spec or wishlist, then build the smallest correct surface that serves it.

### GRY-CMD-18 - Known Failures Are Public Work Items

A Gryphon crash, wrong answer, silent drop, unmodeled accepted shape, or
executor/oracle disagreement must be reported to the user, recorded in the
Gryphon known-issues/wishlist or findings ledger as appropriate, reproduced in
the validation system, and fixed or converted into a loud rejection. Do not route
callers around a failing Gryphon case and leave the language quietly sick.

### GRY-CMD-19 - Preserve Canonical Result Shapes

Gryphon results must package through the canonical graph envelope and row
projection shapes specified by TAP. Do not add caller-specific result shapes from
inside the executor. If a caller needs a different view, define that view outside
Gryphon or specify a general result-envelope extension.

### GRY-CMD-20 - Optimize Only Behind a Soundness Argument

Skip-work fast paths, join reuse, predicate pushdown, alias reuse, aggregation
shortcuts, and future planner rewrites must come with an answer-preservation
argument and regression coverage. Performance is allowed to shape lowering, but
not to change semantics by accident.

### GRY-CMD-21 - Documentation Moves With Behavior

A Gryphon behavior change must update the owning spec, Gridkin coverage or test
surface, Cypher divergence/credit ledger when relevant, and this document if it
changes a commandment. Do not let behavior, docs, and validation drift into three
different stories.

## Forthcoming Commandments

These are intentionally not live requirements yet. They become live after the
named capability or hardening pass lands. Until then, use them as design targets
and review prompts, not as blockers.

### FUT-GRY-CMD-01 - Once an AST Conservation Ledger Exists, Every Node Is Accounted For

Future commandment once conservation checking lands: every AST field and parsed
semantic fact must be marked applied, rejected, or intentionally non-semantic by
a machine-checked ledger. A new AST field without a conservation decision fails
validation.

### FUT-GRY-CMD-02 - Once Must-Fail Ratchets Exist, Known Gaps Can Only Shrink

Future commandment once must-fail ratchets land: accepted-broken, rejected-future,
oracle-unmodeled, and fuzz-found cases live in committed ledgers with expected
status. A change may move an item toward support or a louder rejection; it may
not make the ledger looser without an explicit spec decision.

### FUT-GRY-CMD-03 - Once Variable-Length Paths Land, Use Recursive CTE Semantics

Future commandment once bounded variable-length traversal is implemented:
`-[:E*m..n]->` lowers through the sanctioned recursive CTE rung, with explicit
bound, direction, cycle, path-identity, duplicate-row, and dimension semantics.
No side traversal service, cache, Python graph walk, or post-query expansion may
be the canonical implementation unless the execution spec is deliberately
changed.

### FUT-GRY-CMD-04 - Once WITH Lands, Every Stage Owns Its Scope and WHERE

Future commandment once WITH/pipelining lands: each stage has explicit inputs,
outputs, projections, and local predicates. Per-MATCH WHERE attachment should
arrive with that same stage model. Do not simulate pipeline semantics with one
global WHERE plus variable-name conventions.

### FUT-GRY-CMD-05 - Once a Plan IR Exists, It Is an Invariant Layer, Not an Optimizer Toy

Future commandment once Gryphon grows a logical/physical plan IR: the IR exists
to make scope, lowering choices, semantic conservation, and validation visible.
It must not become a place where rewrites happen before the answer oracle can
check them. Plan-shape tests supplement answer tests; they do not replace them.

### FUT-GRY-CMD-06 - Once Raw SQL Templates Are Active, They Carry the Full Safety Envelope

Future commandment once rung-4 SQL templates are live: each template must declare
its parameters, dimension filters, read-only route, capture surface, expected
result packaging, and validation coverage. A template that cannot show all of
those is not a legal Gryphon lowering.

### FUT-GRY-CMD-07 - Once Formal / Exhaustive Validation Exists, It Complements Gridkin

Future commandment once bounded exhaustive or formal validation lands: formal
methods compare specified semantics against implementation for a bounded shape.
They do not replace Gridkin scenarios, SQL snapshots, fuzzing, branch coverage,
or human-readable specs. Each layer catches a different bug class.

### FUT-GRY-CMD-08 - If Gryphon Write Semantics Are Ever Proposed, Stop and Respec

Future commandment if anyone proposes write clauses: that is not an incremental
Gryphon feature. It is a new language and trust-boundary design requiring a
roadmap decision, service-layer integration model, authz model, concurrency
model, GRIFT relationship, and validation strategy. Until such a spec exists,
Gryphon remains read-only.

## Agent Checklist

Before changing Gryphon, an agent should be able to answer these questions:

1. Which live commandment IDs does this work touch?
2. What demand shape or bug justifies the change?
3. Which spec requirement owns the behavior?
4. What parsed facts are newly accepted, and where are they applied or rejected?
5. Which lowering rung is used, and why is the lower rung insufficient?
6. What independent oracle, Gridkin scenario, fuzz replay, metamorphic relation,
   coverage gate, or rejection scenario proves the behavior?
7. What prior art was consulted, and what was deliberately not copied?
8. What known issue, divergence ledger entry, wishlist item, or forthcoming
   commandment should move because of this change?

If an agent cannot answer these, it should pause the implementation and gather
the missing context before editing the executor.
