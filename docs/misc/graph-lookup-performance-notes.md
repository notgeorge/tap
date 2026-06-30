# Graph Lookup Performance: Why Relational-Backed Traversal Holds Up

Captured 2026-06-29 from a design discussion. This is a thinking document — not
a spec, not an ADR, not scheduled work. Its purpose is to preserve the
performance argument for TAP's entity/edge model so the decision can be defended
later (e.g. "why not just use Neo4j?") without re-deriving it from scratch.

Status of the model as captured: Entity/Edge as described below is **built**.
Dimensions are **built** (JSONB on Entity). RLS, edge-table partitioning, and
materialized paths are **not built** — they appear here only as the
forward-looking part of the argument.

## TL;DR

- Neo4j's headline is **index-free adjacency**: a hop is a pointer dereference,
  cost depends only on a node's *local* degree, independent of total graph size.
  That's genuinely O(1) per hop.
- TAP does an indexed lookup instead. A hop is `O(log E + k)` — a B-tree descent
  on the edge table (E = total edges) plus a scan of the k matching neighbors.
  Not O(1), but **near-constant in practice** (log₂ of 100M ≈ 27, usually
  buffer-cache-hot).
- The qualitative difference: index-free adjacency cost is **local** (degree);
  index-based adjacency cost is **global-but-logarithmic** (total table size).
- This holds up because of three deliberate design choices: **sparsity**,
  **dimensions to defuse supernodes**, and (future) **materialized paths**.
- The real performance enemy is **not** the `log E` factor. It's letting
  traversal degrade into per-hop round trips (N+1) instead of staying set-based
  (one recursive CTE). Guard that and you stay in constant-ish territory.

## The as-built shape (tap_grid/models.py)

`Edge` extends `BaseModel`, so every edge is also backed by an `Entity` on the
spine. The edge row itself carries:

- `from_entity` (FK), `to_entity` (FK), `edge_type` (CharField)
- Composite B-tree indexes, **both directions**:
  - `idx_edge_from_type` on `(from_entity, edge_type)`
  - `idx_edge_to_type` on `(to_entity, edge_type)`

`Entity` carries `dimensions` as a **JSONField**, indexed with a **GIN** index
(`idx_entity_dimensions_gin`). Critically: **dimensions live on Entity, not as a
column on the edge row.** (This is the load-bearing fact for the RLS discussion
below.)

Consequence worth remembering: the edge row physically contains both endpoint
ids, so **walking topology never touches the Entity table.** You only pay a
second lookup (Edge → Entity → typed BaseModel table) when you *materialize* a
node's payload. Reachability / path-existence / counting traversals never incur
that second cost.

## Per-hop cost, precisely

One hop ("from X, follow edge_type T") compiles to a range scan on
`idx_edge_from_type`:

- `O(log E)` to descend to the `(X, T)` range (E = **total** edges in the table)
- `O(k)` to scan the k matching neighbors

A B-tree's height is fixed by the number of entries in the index — i.e. total E.
A `WHERE` predicate does **not** shrink it; it only changes where you land and
how much you scan. So per-hop ≈ `O(log E + k)`, and the only way to make the
`E` inside `log E` smaller is **physical layout** (partitioning or partial
indexes), never a predicate alone.

Also true and useful: a single hop's wall-clock is dominated by the `O(k)` scan
+ heap fetches, not the ~27-comparison descent. So when a filter speeds up a
hop, the term that actually shrank is **k**, not `log E`.

## Why it holds up at scale: the three pillars

**1. Sparsity (the foundation).** Real infra graphs are sparse: |E| ≈ O(|V|),
not O(|V|²). "System X depends on System Y" is inherently local, so k stays
small. The entire "constant-ish" claim rests on k being small, which rests on
sparsity.

**2. Dimensions defuse supernodes (the best idea).** A node with 10⁶ edges — the
**supernode / dense-node** pathology — kills index-free adjacency *and* a
relational index equally dead. TAP sidesteps it: represent "this AWS account
contains these million hosts" as a **dimension tag on each host**, not a million
`CONTAINS` edges. You never traverse it; you *filter* by it. An edge-explosion
becomes an attribute.

  Boundary to remember: a dimension is a **set-membership / scoping** relation,
  not an arbitrary typed relationship. It substitutes cleanly when the
  super-connected thing is containment- or co-location-shaped (account, region,
  tenant, env) — which is the large majority of high-cardinality relationships.
  When you genuinely need a *semantically rich* relationship at high cardinality
  (rare), a dimension can't stand in.

**3. Materialized paths (future relief).** Precompute a hot or named traversal
as a first-class object (a path node with edges to its members), trading
write-time maintenance for read-time speed. Formal names: materialized path /
transitive-closure table / path reification. Deferred cost to bank: every
materialized path is a **cache that must be invalidated** when an edge on it
mutates. (See also docs/misc/grid-native-paths-notes.md.)

## Multi-hop: where it compounds, and the real risk

A k-deep traversal with branching factor b:

- Neo4j: ~`O(b^k)` pointer chases — proportional to the frontier visited,
  indifferent to total graph size.
- TAP: ~`O(b^k · log E)` — every frontier node pays its own index descent. The
  `log E` is the standing tax vs. index-free adjacency.

But the `log E` tax is **not** what will hurt. The hazard is execution shape:

- **N+1 trap:** one query per hop from app code → `b^k` *round trips*, whose
  network/planner overhead dwarfs any log factor. This is the 1960s `FIND NEXT`
  loop reborn with worse constants.
- **Set-based win:** compile to a single `WITH RECURSIVE` CTE → Postgres expands
  the whole frontier inside one plan, reusing the indexes, switching to hash
  joins when a frontier widens. Same asymptotic shape, vastly better constants.

This is the reason Gryphon compiles to SQL rather than exposing a load-node /
loop / load-next API. **Keep traversal set-based; never let it leak into a
per-hop Python loop.**

## The RLS / dimension-filtering subtlety (don't mis-defend this one)

Tempting claim: "apply dimension restrictions via RLS to the edge queries and we
down-select E → E_dim, so `log E` becomes `log E_dim`." The *conclusion*
(dimension scoping makes traversal faster) is true. The *mechanism* is wrong on
two counts:

1. **A predicate doesn't shrink a B-tree.** Height is set by total entries.
   RLS injects a `WHERE`; it changes where you land, not the tree height. The
   only things that actually reduce the `E` in `log E` are physical:
   - **partial indexes** (`… WHERE dimension = 'x'`) — genuinely smaller index,
     `log(E_dim)` descent, but one per hot value; doesn't scale to arbitrary
     dimensions.
   - **declarative partitioning** by dimension — partition pruning hits one
     partition whose index holds only `E_dim` entries → `log(E_dim)`. *This* is
     the mechanism that delivers the intuition, and it's a data-layout decision,
     not a security-policy one.

2. **Dimensions aren't on the edge row today.** They're JSONB+GIN on
   `tap_entity`. So "restrict edges by dimension" is a **join** from each edge to
   entity rows, wrapped *around* the `(from_entity, edge_type)` probe — the probe
   still sees all E. To filter edges by dimension "up front," you'd have to
   **denormalize the dimension onto the edge/typed row as a real column** and
   then partition or composite-index on it.

Also: RLS predicates calling `current_setting()` can be **non-sargable /
planner-opaque** and a naïve policy can *prevent* index use and cost you. RLS's
real job is the **correctness boundary** (you cannot leak a cross-dimension
edge); any speed is a downstream consequence of a smaller result set.

**Where the dimension win actually lives** (relocate it to the right term and
the instinct comes out stronger):

- Per hop: dimension selectivity cuts **k** (fewer neighbors pass) — real
  speedup, just on the k term, not `log E`.
- Multi-hop: constraining the frontier to a dimension collapses branching at
  *every* level: `b^k → b_dim^k` — an **exponential** improvement in deep
  traversals, independent of the `log E` quibble. This is the big prize.

## When the relational approach actually starts to lose

The asymptotic gap vs. a real graph engine is small until you're doing **deep
traversals (≈6+ hops) on tens of millions of edges**, where the recursive CTE's
intermediate frontier materializes large and join constants stack. If TAP ever
lives in *that* regime routinely, that's the demand signal to consider a
dedicated graph engine alongside Postgres — a later, demand-driven decision, not
a today problem.

## One-line defense, if that's all you have time for

> Per hop is `O(log E + k)`, near-constant because the graph is sparse and
> supernodes are modeled as dimensions, not edges. The cost that matters is k
> and frontier size — both cut hard by dimension scoping — not the log factor.
> The only real risk is N+1 round trips, which Gryphon avoids by compiling
> traversal to one set-based recursive CTE.
