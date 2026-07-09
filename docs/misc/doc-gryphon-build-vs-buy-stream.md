---
audience: [human, llm, developer]
covers:
  - doc-gryphon-build-vs-buy-analysis.md
  - doc-dev-gryphon-vs-cypher.md
  - doc-dev-gryphon-wishlist.md
  - doc-gryphon-battle-hardening.md
  - comparanda/dossier-cyp2sql.md
  - ../../plugins/gryphon_playground/specs/spec-gridkin-v0.md
  - ../../architecture.md
status: working-note
created: 2026-07-07
provides: |
  A deliberately less-formal capture of the architectural intuition behind TAP's
  SQL-backed graph and Gryphon, including the current doubts raised by Memgraph,
  Neo4j, Apache AGE, a possible Gryphon v2 rewrite, and the cost of owning a
  query compiler. This is the raw note; the structured decision analysis lives
  beside it.
---

# Gryphon Build-vs-Buy Stream Note

This note captures the live architectural conversation before it hardens into a
decision memo. It is intentionally written closer to how the concern arrived:
half history, half doubt, half "wait, why are we doing this again?" Yes, that is
three halves. Query compilers do that to a person.

## The Origin Story

TAP wanted graph capabilities from the start. Not a graph-shaped UI over flat
tables, and not a few foreign keys pretending to be a graph, but real nodes,
real edges, traversals, neighborhoods, topology, provenance, visualization, and
future AI-readable graph context.

At the same time, TAP was not trying to leave SQL behind. The pull in the other
direction was just as strong:

- SQL databases give typed tables, constraints, transactions, migrations,
  indexes, operational familiarity, backup tooling, and decades of hardening.
- Django's ORM gives a productive, inspectable application substrate.
- TAP's domain objects want real schemas, not only property bags.
- The service layer wants one place for graph writes, provenance, optimistic
  concurrency, hotlinks, future authorization, and GRIFT import.
- The product wants local, inspectable, on-prem friendly deployment without
  making the database architecture exotic on day one.

The entity-spine design was the bridge. Nodes are concrete `BaseModel`
subclasses with typed fields. Edges are first-class graph objects. Both hang off
the `Entity` spine. The graph is therefore SQL-backed, typed where TAP needs
types, and still navigable as a graph.

Once the graph existed in SQL, the next problem was obvious: people and panels
needed to ask graph-shaped questions. That need created Gryphon, originally as a
compact Cypher-like traversal notation over the TAP grid.

## How Gryphon Actually Grew

The honest history is that Gryphon did not arrive as a fully designed compiler.
It grew from demand:

- `7694613c` introduced the traversal language as a hub-and-spoke neighborhood
  replacement.
- The Sam/Rampart demo path pulled in concrete read shapes, panel needs, table
  projections, filtering, string operators, bare scans, typeless edges, and
  graph envelopes.
- The first validation push created Gridkin, SQL capture, and the dedicated
  `gryphon_playground` corpus.
- Later work added a model oracle, rejection scenarios, TCK mining as
  inspiration, TLP/metamorphic tests, a feature-demand study, a comparative
  study, the commandments, and the lowering ladder.

That means Gryphon's *user-facing reason to exist* is not accidental, but its
executor internals were absolutely emergent. The language is now load-bearing
enough that the emergent shape is no longer cute. A vibe-coded query transpiler
is still a query transpiler. It can produce silent wrong answers, and silent
wrong answers are the worst possible failure mode for a security/compliance
system.

The last week and a half of Gryphon work is basically the system waking up to
that reality. The direction has been:

- write down the semantics that were previously implicit;
- make unsupported constructs reject instead of guessing;
- collapse duplicate executor tails where possible;
- push work into the ORM/Postgres plan instead of Python glue;
- preserve the read-only trust boundary;
- build validation that can catch wrong answers without trusting the executor's
  own mental model.

This is not polishing for elegance. It is paying down a correctness debt that
became visible only after Gryphon became important.

## Why Not Just Use Cypher?

The strongest version of the critique is fair:

> Memgraph exists. Neo4j exists. Apache AGE exists. GQL exists. Why are we
> building a Cypher-like compiler when entire teams have spent years doing this?

That question should be taken seriously. Query languages are hard. Query
planners are hard. Null semantics, duplicates, optional matches, aggregation,
path identity, row materialization, and variable scope are all bug farms. A
general-purpose Cypher engine is not a weekend feature. It is a database product.

But the real question is not "can somebody else run Cypher?" They can. The real
question is:

> Can an off-the-shelf graph database replace the role Gryphon plays in TAP
> without losing the guarantees TAP is trying to preserve?

That is a much harder sell.

Gryphon is not just "our Cypher." It is the read language over TAP's typed SQL
graph. It routes through TAP's service/search surface, executes read-only,
bind-parameterizes inputs, respects TAP's explicit spine/data/display lanes,
uses the typed schema as an oracle, sees dimensions on the Entity spine, returns
GRIFT-shaped envelopes or row projections, and can be validated against the
Gridkin/model-oracle corpus.

Plain Cypher does not know any of that. A Cypher database sees a property graph.
TAP sees a typed application graph with provenance, dimensions, service-layer
rules, first-class edge entities, and future authorization semantics.

## The External Options, In Human Terms

### Neo4j

Neo4j is the mature graph database and Cypher's home. If TAP were primarily a
graph analytics product over a property graph, Neo4j would be the default thing
to evaluate seriously.

The fit problem is that Neo4j would either become:

1. the canonical store, replacing TAP's SQL typed model, or
2. a secondary graph mirror, duplicating TAP state.

The first path loses too much of what TAP is: Django models, typed tables,
service-layer writes, SQL constraints, JSONB/dimensions on the spine, GRIFT
import semantics, and the path to a compact deployment shape.

The second path creates a synchronization problem. Every graph write now has to
be reflected into a second database, kept consistent, rebuilt after failures,
authorized coherently, versioned, backed up, and validated. That might be
worthwhile for a bounded analytics backend someday. It is not a simpler primary
architecture.

Also, Neo4j's property model is not a free superset of TAP's data model.
Neo4j's current manual says property values can be stored only for property
types; maps are constructed/returned values, not stored properties, and only
homogeneous lists of simple types can be stored as properties. TAP's need for
nested structured data sits more naturally in SQL/JSON fields with declared
JSON Schema than in Neo4j's property bag.

Source: [Neo4j Cypher Manual, property/structural/constructed values](https://neo4j.com/docs/cypher-manual/current/values-and-types/property-structural-constructed/).

### Memgraph

Memgraph is the best "wait, maybe we can just use an open graph engine" challenge
to this decision. It has a serious Cypher surface, ACID transactional modes,
advanced algorithms, MAGE, and it supports maps/lists as property values. That
last point matters: unlike Neo4j, Memgraph's docs explicitly list `Map` and
`List` among supported property types, with practical limits governed by memory.

Sources:

- [Memgraph data types](https://memgraph.com/docs/fundamentals/data-types)
- [Memgraph storage memory usage](https://memgraph.com/docs/fundamentals/storage-memory-usage)
- [Memgraph advanced algorithms](https://memgraph.com/docs/advanced-algorithms)

But Memgraph is not "free Neo4j, no tradeoffs." Its repository license is BSL
1.1 as amended, with internal production use grants but restrictions around
redistribution, database-as-a-service, and competitive use. Enterprise features
include HA, RBAC/LBAC, auth integrations, multi-tenancy, tenant profiles,
parallel execution, and dynamic graph algorithms. For TAP as a commercial
product that may be deployed for others, embedded for customers, or eventually
packaged as a platform, the licensing question is not cosmetic.

Sources:

- [Memgraph repository LICENSE](https://github.com/memgraph/memgraph/blob/master/LICENSE)
- [Memgraph BSL text](https://github.com/memgraph/memgraph/blob/master/licenses/BSL.txt)
- [Memgraph Enterprise features](https://memgraph.com/docs/database-management/enabling-memgraph-enterprise)

Architecturally, Memgraph still has the same canonical-store/mirror split. It
does not understand TAP's service-layer mutation contract, GRIFT atomic import,
Entity dimensions, typed BaseModel rows, edge entities as spine objects, or
field-level provenance. We would need to project those ideas into it.

The positive read: Memgraph is not a reason to delete Gryphon. It is a credible
candidate for a future bounded graph-analytics backend if TAP reaches workloads
where SQL lowering is the wrong tool: shortest paths, BFS/DFS, centrality,
community detection, and large reachability queries. That is a complement, not a
replacement.

### Apache AGE

Apache AGE is tempting because it says "Postgres plus Cypher." That sounds like
the compromise TAP already wanted.

The actual shape is less attractive for TAP's current architecture. AGE queries
are invoked through a `cypher(graph_name, query_string, parameters)` function
that returns PostgreSQL records, with values represented as `agtype`, a custom
type described as a superset/custom implementation of JSONB. That means TAP
would still not be querying its Django models through normal ORM paths. It would
be embedding a separate graph model and Cypher execution layer inside Postgres.

Sources:

- [Apache AGE homepage](https://age.apache.org/)
- [Apache AGE Cypher query format](https://age.apache.org/age-manual/master/intro/cypher.html)
- [Apache AGE agtype data types](https://age.apache.org/age-manual/master/intro/types.html)

That may be a good tool for someone who wants a graph database inside Postgres.
For TAP, it risks the worst blend: keep Postgres operationally, but lose the ORM,
typed-model, service-layer, and explicit-lowering advantages that made Postgres
attractive in the first place.

### RedisGraph

RedisGraph is the cautionary tale. Redis' own current docs list RedisGraph under
deprecated Redis Open Source modules. The point is not "never use projects."
The point is that graph engines are strategic products, not just libraries. A
module can go away when the business or community focus moves.

Source: [Redis deprecated Open Source features and modules](https://redis.io/docs/latest/operate/oss_and_stack/stack-with-enterprise/deprecated-features/).

TAP can depend on Postgres and Django with much more confidence than it can
depend on a graph engine becoming an invisible embedded detail forever.

## The Relief Valve Is Real

There is a real escape hatch: not every high-value query has to go through the
general Gryphon language forever.

For product delivery, a battle-hardened query-specific module or direct ORM
formulation can be the right answer if:

- the query is critical;
- the general language cannot express it safely yet;
- the module is validated against the intended Gryphon/query semantics;
- the bypass is logged as a demand signal rather than normalized as the new
  normal.

This reframes the relief valve as a product-safety mechanism, not an admission
that Gryphon failed. "Particular accuracy" matters. A customer-facing table or
compliance finding must be right. If a per-query implementation is the fastest
way to make a specific decision path correct, that is legitimate.

But it must remain governed. If every hard query becomes a bespoke module, TAP
quietly loses its canonical read surface. The relief valve should protect
delivery while feeding Gryphon's backlog, not replace Gryphon by drift.

## What Still Feels Scary

The scary part is not the idea of a SQL-backed graph. That still feels right.

The scary part is the general-purpose compiler boundary. The executor currently
has too many shape-specific paths, too much Python glue, and a history of
features landing because a demo needed them rather than because an execution
architecture had already made room for them.

The recent spec work is pointed at exactly this:

- no premature logical-plan IR;
- keep the Django QuerySet plus Postgres plan as the borrowed IR;
- collapse row materialization into one backend;
- keep envelope unification out of scope until the plan can carry structural
  hop descriptors;
- document every Cypher divergence;
- reject unsupported syntax loudly;
- keep validation oracle-first.

That is the narrow path where Gryphon remains sane. The danger is sliding from
"small read-only TAP traversal compiler" into "we are accidentally implementing
Neo4j in Python."

## The Gryphon v2 Temptation

There is another path that is neither "keep renovating v1 forever" nor "give up
and buy Cypher": build Gryphon v2 from scratch, in parallel, as a disciplined
drop-in replacement.

The appeal is real. TAP now has things it did not have when Gryphon first grew:
written semantics, Gridkin scenarios, expected envelopes, SQL snapshots, a model
oracle, comparative prior art, a feature-demand study, and a much clearer sense
of where the current executor is brittle. It also has a new labor shape:
multiple coding agents can build independent contenders, MOB through hard
parts, or run bake-offs against the same corpus. That opens a new style of
software construction: not one heroic refactor, but several independently
lowered engines competing under one contract.

The really interesting version is not only "replace v1." It is:

- build two or more implementations with intentionally different internals;
- compare each against the running engine, the model oracle, and hand-authored
  expectations;
- keep the best ideas at stable seams rather than grafting arbitrary internals;
- eventually shadow-run v1 and v2 on the same real queries to detect
  disagreements before customers depend on the result.

That is legitimately exciting. It turns multiple agents into a verification
pressure system instead of just a faster typing pool.

But it has traps.

The first trap is rewrite romanticism. The cyp2sql prior-art dossier is the
warning label. That project rewrote its Cypher-to-SQL translator and fixed many
known problems, but the rewrite preserved the bad assumptions the validation net
did not reject. A rewrite fixes what its authors can name. It conserves what
the tests and oracles are blind to.

The second trap is false independence. Two engines written by different agents
are not automatically independent if they share the same vague spec, same
fixtures, same ORM misunderstandings, same result-normalization blind spots, or
same model oracle. If they both return the same wrong answer, the customer still
gets the wrong answer. Agreement is useful evidence, not proof.

The third trap is permanent duality. Running two engines forever can become the
query-layer version of a dual-write database. Every feature needs two
implementations, every disagreement needs governance, and every caller wonders
which answer is real. That can be worth it in a bounded shadow-validation phase.
It is a dangerous default architecture.

So the safe shape is probably:

- do not start v2 until the current materialization/DISTINCT work lands and the
  semantics are stable enough to judge;
- write a v2 charter before code: public API compatibility, supported grammar,
  internal seams, non-goals, acceptance gates, shadow-mode behavior, and v1
  retirement criteria;
- build clean-room from specs and tests, not by copying executor guts;
- require true independent lowering for contenders that claim differential
  value;
- promote only in stages: v1 primary/v2 shadow, then canary, then v2 primary,
  then retire v1 or keep it as a bounded diagnostic oracle.

In other words, Gryphon v2 is attractive as a validation program that may
produce a better engine. It is dangerous as a belief that a fresh codebase makes
query semantics safe.

## Current Intuition

Do not switch TAP's canonical store to Memgraph, Neo4j, or AGE.

Do not add a second Cypher store casually.

Do not start Gryphon v2 as a launch-blocking rescue mission. Keep it on the
table as a parallel, explicitly governed rewrite once the current specs and
oracles are strong enough to judge it.

Continue with the SQL entity spine and Gryphon as the canonical read language,
but with a stricter doctrine:

- Gryphon is a constrained read compiler, not a database.
- SQL/Postgres/Django ORM remain the trusted substrate.
- New syntax lands only on demand and only with Gridkin/oracle coverage.
- Cross-cutting row behavior belongs in one backend.
- Python glue is suspect until proven necessary.
- Query-specific modules are allowed as governed relief valves.
- Gryphon v2 is a future drop-in contender, not a second permanent read path.
- External graph engines are future analytical backends, not canonical storage,
  unless the product changes enough to justify a new architecture decision.

The strongest future role for Memgraph or NetworkX-like tooling is not "replace
Gryphon." It is:

> Gryphon selects the bounded TAP subgraph; an analytical backend computes the
> graph algorithm TAP should not hand-roll in SQL.

That is a clean boundary. It preserves TAP's source of truth and gives a place
for real graph algorithms when the demand is no longer theoretical.

## The Question To Keep Asking

The build-vs-buy question should stay alive, but sharpened:

1. Are we still mostly asking typed operational/compliance questions over a SQL
   domain model? If yes, keep Gryphon over SQL.
2. Are we starting to ask repeated, high-value graph algorithm questions
   (shortest path, blast radius, centrality, communities) where SQL lowering is
   the wrong substrate? If yes, add a bounded analytical backend.
3. Are customers asking to bring their own Cypher or expect Cypher
   compatibility as a product feature? If yes, reassess Gryphon's dialect
   posture.
4. Are query-specific modules becoming common enough that the canonical read
   path is fiction? If yes, pause and either grow Gryphon or demote it honestly.
5. Are we spending more time maintaining compiler internals than shipping
   Rampart value? If yes, stop expanding the language and lean on the relief
   valve until demand justifies the next feature.
6. Has the validation surface become strong enough that an independent Gryphon
   v2 implementation can be judged without trusting v1? If yes, a parallel
   bake-off becomes one of the most interesting next bets.

That is the line: keep the architecture because it is coherent, not because we
already built it.
