---
audience: [llm, developer]
covers:
  - ../doc-gryphon-commandments.md
  - ../../tap_grid/specs/spec-grid-traversal-execution.md
  - doc-dev-gryphon-wishlist.md
assumes:
  - Reader knows Gryphon (Cypher-subset → ORM→SQL, read-only, pattern-matching-shaped) and the lowering ladder
  - This is an IDEA note for future consideration — nothing here is built or committed
provides: |
  The thought that NetworkX (or a faster peer) could serve as a distinct analytical
  backend for the class of graph computations Gryphon deliberately does not and cannot
  cheaply lower to SQL — centrality, community, shortest-path, reachability, flow — with
  the clean division "Gryphon selects the subgraph, NetworkX computes over it." Includes
  why the fit is a complement not an overlap, the proven-precedent (Neo4j GDS / Memgraph
  MAGE do exactly this), the guardrails our own commandments impose, and open questions.
---

# NetworkX as an Analytical Backend — Complement, Not Competitor (Idea Note)

> A "jot it down before yoga" idea. Nothing built. The naive framing — *extract a subgraph from
> Postgres, load it into NetworkX, run graph queries* — is directionally right, but the value is
> sharper (and more bounded) than "the full range of graph queries," so this note reframes it.

## 1. The reframe: NetworkX is the *complement* of Gryphon, not more of it

The instinct is "NetworkX does graph queries, Gryphon does graph queries, maybe we borrow theirs."
But they occupy **opposite** halves of the graph-workload space, and that's exactly why it's
interesting:

- **Gryphon does pattern-matching / relational-shaped work** — `MATCH` a shape, filter, project,
  aggregate. This lowers cleanly to SQL joins, which Postgres does well. It is *selection*: "find
  the nodes/edges matching this description."
- **NetworkX does whole-graph *algorithms*** — centrality (PageRank, betweenness, closeness,
  eigenvector), community detection (Louvain, label propagation, modularity), connectivity
  (components, articulation points, bridges, k-core), shortest/weighted paths (Dijkstra, A\*),
  reachability, max-flow/min-cut, cycle enumeration, clustering coefficients, DAG ops, link
  prediction. These are **not expressible as relational joins** — they're iterative/recursive
  computations over the whole (sub)graph. It is *computation*: "compute a property of the graph's
  structure."

So the value isn't "borrow NetworkX's query language" (it doesn't have one — no Cypher, its own
Python API; and its subgraph-isomorphism matcher would lose to SQL joins on the relational-shaped
patterns Gryphon already owns). The value is **its algorithm library** — precisely the "graph-flavored"
class Gryphon's lowering ladder struggles with and the wishlist parks as the heaviest work
(Bucket E: reachability & topology — variable-length paths, `shortestPath`, "blast radius").

**The clean division of labor:** *Gryphon selects the subgraph (its strength), NetworkX computes
over it (its strength).* The extraction is itself a Gryphon query, so the two **compose** rather
than compete.

## 2. The naive approach is the right shape — and it's a proven product pattern

"Materialize a bounded subgraph → load into an in-memory analytical engine → run algorithms → return
the result" is not a hack; it is the architecture two mature Cypher engines already ship:

- **Neo4j GDS (Graph Data Science)** exists *because* pattern-Cypher can't do the algorithms and
  pulling everything to a client didn't scale. GDS *projects* a subgraph into an in-memory analytical
  graph and runs the algorithm library natively. That's the user's naive idea, industrialized — and
  it hands us the scaling answer: **project a bounded subgraph, don't stream the whole graph to
  Python.**
- **Memgraph MAGE** goes further and **bridges to NetworkX directly** — you can invoke NetworkX
  algorithms as procedures over a Memgraph graph. A Cypher engine that routes the algorithm tail to
  NetworkX is *exactly* the pattern being proposed here. (Verify the current MAGE↔NetworkX surface
  before leaning on it, but the precedent is real.)

That two independent Cypher engines converged on "in-memory analytical engine for the algorithm tail"
is strong evidence the shape is sound — and that the interesting design question is *scope and
boundary*, not *whether*.

## 3. Where it slots into our existing plans

This isn't a new axis — it's a concrete candidate for slots we've already named:

- **Wishlist Bucket E (Reachability & Topology).** E1 (variable-length paths), E2 (path functions),
  E3 (`shortestPath`) are marked "the heaviest engineering item" and "wait-for-signal." NetworkX is
  a candidate *backend* for that whole bucket — an alternative to hand-written `WITH RECURSIVE` CTEs
  (rung 4) that would otherwise be painful and, for true shortest-path/centrality, not expressible in
  SQL at all.
- **The exec spec's own open question.** `spec-grid-traversal-execution.md` (Lowering Ladder, Future)
  already asks *"whether a PostgreSQL graph extension (e.g. Apache AGE) belongs as a distinct backend
  rather than a sixth rung, if reachability queries outgrow hand-written recursive CTEs."* NetworkX is
  a second candidate for that **distinct-backend** slot — specifically for the *analytics* tail, where
  AGE (still relational-ish) wouldn't help either.
- **The relief-valve pattern** (from `doc-gryphon-battle-hardening.md`). This is the same move: when a
  query wants a computation the primary engine can't express, route it to a specialized engine —
  demand-gated, governed, preferring to grow the primary path where feasible.

## 4. Guardrails our own doctrine imposes

The comparative study and the commandments make the *risks* here precise — this is a second execution
engine, and second engines are where peers bled:

- **Scope it to the algorithm class SQL genuinely cannot do.** NetworkX **MUST NOT** become a general
  Gryphon execution path (that's RedisGraph's whole EOL lesson — a bespoke executor re-earns
  correctness, memory-safety, and semantics for years). Route *only* centrality/community/
  reachability/flow/shortest-path — the joins-can't-express tail — never pattern-matching Gryphon
  already lowers well. It is a **distinct analytical backend**, not a rung the general path reaches
  for casually (respects GRY-ARCH-1 "compile over a trusted substrate" and GRY-ARCH-2 "lowest rung").
- **Two engines = a second-engine correctness burden *and* a differential opportunity.** NetworkX's
  null/type/multiplicity semantics differ from SQL's; its results must be validated (the model-oracle
  discipline, GRY-TEST-2). Upside: for the overlap cases it's a free *differential* oracle.
- **The result is a new type, not a graph envelope.** A centrality score, a community label, a path
  cost is a *derived analytical value*. It needs a home in the response shape (a `display`/analysis
  lane), not the `{nodes, edges}` envelope. Design that surface deliberately.
- **Read-only fits cleanly.** Extraction is a read; NetworkX computes in memory and mutates nothing —
  the read-only credit (GRY-ARCH-7) holds, and the "which subgraph?" question is answered by a Gryphon
  `MATCH`, keeping the boundary legible.
- **Determinism & provenance.** The projection is a point-in-time snapshot; record it. Algorithm
  outputs must be reproducible (seed any randomized algorithm, e.g. Louvain) or they can't be
  battle-hardened.

## 5. Two ways it could surface (both later)

1. **As a transparent backend for reachability/path clauses** — the author writes Cypher-ish
   (`shortestPath`, `-[*1..3]-`), and the executor routes those *shapes* to NetworkX (or a recursive
   CTE) instead of failing. This is the Bucket-E / distinct-backend framing. Preferred where the
   language already anticipates the shape.
2. **As a small, curated analytics surface** — named read-only functions (`pagerank()`, `betweenness()`,
   `community()`) over a Gryphon-selected subgraph. Note this bumps against Gryphon's deliberate
   omission of `CALL`/procedures; it would be a *new, tightly-scoped, read-only* analytical surface,
   not a general procedure-call mechanism. Demand-gated.

## 6. Scale escape hatches (name them so we don't reinvent later)

Pure-Python NetworkX is slow on large graphs — which *reinforces* the "project a bounded subgraph
first" discipline. If scale bites within a bounded projection, the drop-in-ish upgrades are worth
knowing: **rustworkx** (Rust, near-NetworkX API, Qiskit's engine), **igraph** (C), **graph-tool**
(C++/boost), **cuGraph** (GPU). On the Postgres side: **pgRouting** (shortest-path), recursive CTEs,
Apache AGE. The API-compatibility of rustworkx means a NetworkX prototype could later swap engines
with modest churn — a good reason to prototype on NetworkX and keep the algorithm calls behind a thin
seam.

## 7. Open questions for when this is picked up

- **Which algorithms are actually demanded?** (Tie to the Cypher-feature-demand study — if
  `shortestPath`/variable-length rank high in real corpora, Bucket E + a NetworkX backend rises
  together.) Don't build the library ahead of demand.
- **Projection boundary & size caps** — how big a subgraph, materialized how, with what snapshot
  semantics and what cap before it's rejected (fail-closed).
- **Result surface** — how analytical outputs ride the envelope/display lanes and stay AI-legible.
- **Validation** — how the model oracle / battle-hardening validate a NetworkX-backed result (or
  whether such results are validated by algorithm-level property checks instead, GraphFrames-style).
- **Build vs buy the boundary** — thin-seam-over-NetworkX (swap to rustworkx later) vs a native
  recursive-CTE rung-4 vs an AGE/GDS-style in-DB projection. The comparative study's bias: stay on the
  trusted substrate where you can (recursive CTE for bounded reachability), reach for the in-memory
  analytical engine only for the genuinely-non-relational algorithms (centrality/community/flow).

## Pointers

- **The doctrine it must respect:** `doc-gryphon-commandments.md` (GRY-ARCH-1/2/6/7, GRY-LANG-5)
- **The slot it fills:** `doc-dev-gryphon-wishlist.md` Bucket E; `spec-grid-traversal-execution.md`
  (Lowering Ladder → Future: "distinct backend")
- **The relief-valve framing:** `doc-gryphon-battle-hardening.md`
- **Demand data to gate it:** the Cypher-feature-demand study (in progress)
