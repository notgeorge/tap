# Future Seam: Grid-Native Paths

Captured 2026-06-14 from a stream-of-consciousness design note. This is a
thinking document, not a spec, not scheduled implementation, and not an
architecture decision record. Its purpose is to preserve the shape of the idea
so a later spec pass can pick it up cleanly.

Roadmap posture: general-purpose paths are strategically important but should
not displace the active Rampart critical path. They are, however, already named
as a parallel capability for the first-paying-customer/productization horizon,
especially for representing build, deploy, ownership, reliance, and AI-system
flows.

## Core Thesis

Paths are a first-class data construct on the grid. TAP already has graph
objects and graph traversal, but it does not yet have durable, named, queryable
representations of "the way through" a system.

That matters because paths turn a graph model into systemic structure. A graph
can show territory: entities and their relationships. A path can show a route,
process, dependency chain, blast radius, ownership chain, workflow, or flow of
meaning through that territory.

In the compact TAP framing: TAP maps the Tao. Paths are the feature that makes a
map of "the way" possible as a standardized, robust, flexible, first-order
capability rather than as a reader's private interpretation layered over raw
nodes and edges.

## Candidate Representation 1: Persistent Path Nodes

Working title only. Better name needed.

In this model, a path is represented by a TAP-managed node entity. That path
node has ordered step edges to each entity participating in the path. Step
ordering and path-local metadata live on those step edges.

Immediate benefits:

- A path has identity on the grid.
- A path can be named, tagged, described, versioned, visualized, and protected.
- Finding a known path does not require re-running a traversal query.
- Gryphon can search for paths as ordinary graph objects.
- Path metadata can live in normal TAP graph structures rather than in an
  opaque side table.

The hard part is representing a true node-edge-node walk. If a path step needs
to include both the node and the edge traversed from that node, the path must be
able to point at edges as path participants.

That implies relaxing the current convention that TAP edges connect only node
entities. Since edges are already first-class graph objects with their own
backing Entity rows, this is not structurally impossible. It is a convention TAP
set early, and paths may be the first use case that justifies a narrow,
well-specified exception: path-step edges may target edge entities when the path
needs to record the relationship traversed, not only the endpoint reached.

Questions for the later spec pass:

- Is the exception limited to path-related edge types, or does TAP introduce a
  general "edge endpoints may be any Entity" model with constraints layered on
  top?
- Does a path step point directly at a node or edge Entity, or is there a
  dedicated path-step node between the path and the participant?
- Where do step order, branch labels, loop labels, traversal direction, and
  confidence/provenance belong?
- How do path nodes interact with history, FLIP, tombstones, and GRIFT removals?

## Candidate Representation 2: Embedded Path Membership

In this model, a named path may still be represented by a node, but each Entity
also carries a first-order path membership object. Conceptually, this might be an
`Entity.paths` field that records which paths the entity participates in and
where it appears within them.

The argument for putting this on Entity is that paths feel like dimensions,
history, and FLIP: cross-cutting grid infrastructure rather than plugin-domain
payload. Entity is already the spine for first-order graph concerns, and path
membership may belong there for the same reason dimensions do.

Immediate benefits:

- Fast path-aware traversal across the Entity table.
- No need to load typed BaseModel rows just to follow path metadata.
- Efficient checks for "what paths is this entity part of?"
- A natural foundation for service-layer behavior such as cascades,
  protection, validation, and path-aware deletes.

This approach may be especially useful for model-defined or edge-defined paths.
For example, a model/edge declaration could say that `application - RUNS_ON ->
ec2_instance` establishes an ownership or reliance path. Deleting the EC2
instance could then delete, tombstone, block, or warn on associated applications
according to declared path semantics.

That cascading behavior is one of the places embedded paths may first earn
their keep: standardizing ownership/reliance information as nodes and edges are
created, so later graph mutations can consult consistent path membership instead
of hand-rolled traversal logic.

Questions for the later spec pass:

- Is `Entity.paths` a cache of materialized path membership, an authoritative
  source of path membership, or both depending on path type?
- If path data is embedded, how is it kept consistent with path nodes and path
  step edges?
- What is the JSON shape, and does it need a schema in the same change?
- How does this avoid becoming a junk drawer for rich path semantics that should
  instead be nodes?
- How does optimistic concurrency apply when path membership changes as a
  side-effect of ordinary node/edge writes?

## Candidate Representation 3: Traversed or Generated Paths

This is closest to the way graph databases commonly expose paths today: a path
is the result of a traversal query.

In TAP terms, Gryphon would gain traversal/path result support. A search could
return a subgraph plus metadata describing traversal order, which edge was
followed at each step, branch position, and possibly loop information.

This does not need to compete with persistent path nodes or embedded path
membership. It may be the primary mechanism by which those structures are
created and maintained:

- A user or plugin defines a pathfinder/pathmaker query.
- Gryphon executes it and returns ordered traversal metadata.
- The result can be inspected directly, materialized into a path node, embedded
  as Entity path membership, or refreshed on a schedule.

This gives TAP both ephemeral computed paths and durable named paths.

Questions for the later spec pass:

- What does a Gryphon path result look like in GRIFT-shaped output?
- Does Gryphon return one path, many paths, or a path-indexed subgraph?
- How are branch and loop metadata represented without inventing a confusing
  private notation?
- Are pathmaker queries stored as grid objects, plugin declarations, or both?
- How are authz and dimensions applied during traversal and materialization?

## Branches, Loops, and Path Addressing

Branches need a notation that identifies path segments and positions. Dotted
notation is the current sketch: something like `path.branch:step.branch:step`,
where each segment makes the local branch/step relationship legible.

Loops may be representable with a related notation, such as `loop:step`, so a
walker can tell immediately that it is entering a cycle and where that cycle
returns.

This needs prior art before it becomes a TAP-specific design. The future spec
pass should look at established approaches in graph query languages, workflow
engines, tracing systems, route planning, provenance models, and possibly
parser/tree address schemes before choosing terminology or notation.

Open concern: paths can be simple walks, branching structures, cyclic
structures, or subgraphs with a preferred traversal. TAP should avoid choosing a
notation that only handles the simple case while pretending it solved paths.

## Paths on Paths

If branch and loop metadata are embedded in a consistent way, paths themselves
become traversable structures. TAP could support path-specific traversal:

- Walk this path forward.
- Walk this path backward.
- Follow only this branch.
- Follow only this loop.
- Compare two paths through the same graph.
- Treat a branch, loop, or subpath as a first-class object.

This points toward "paths on paths": path structures that can themselves be
queried, composed, tagged, protected, and visualized. The exact use cases are
not yet clear, but the capability feels powerful enough that the initial design
should avoid closing the door.

## Broken Paths and Path Protection

Paths create a new class of integrity signal: a graph mutation can break an
important path.

The newly spec'd flaws implementation may be a natural way to report path
breakage. A delete, edge rewrite, dimensional move, or permission change could
produce a flaw saying that a named path is now broken or degraded.

Path protection may also become part of authz. Some paths should block
destructive changes; others should allow the change but warn, record, notify, or
mark the path broken. This likely interacts with dimensionality-based authz:
permission to modify an object may depend not only on the object's dimensions,
but also on whether the mutation harms protected paths that pass through it.

The model probably needs both modes:

- Non-breaking/protected paths, where certain mutations are refused or require
  explicit override.
- Break-detecting paths, where mutations proceed but the system records that a
  critical path was damaged.

Path importance and tagging need to be fine-grained. A whole path may be
critical, but so might only one branch or loop. Teams should be able to classify
paths in their own language without TAP baking in one universal severity model.

## Gryphon Implications

Gryphon will need explicit path traversal affordances.

Likely capabilities:

- Fetch all parts of a named path.
- Traverse from a node along a path.
- Filter nodes/edges within a path result.
- Return traversal order metadata.
- Return path membership as part of a subgraph response.
- Execute and store pathfinder/pathmaker queries.
- Materialize a traversal result into persistent path structures.

This should stay canonical in Gryphon, not become a one-off ORM search helper or
plugin-specific graph traversal module. A Gryphon failure in this area should be
treated like any other Gryphon failure: reproduce it in the validation surface,
fix it there, and do not build around it in callers.

## Actions on Paths

Paths are not only read structures. They can drive graph manipulation.

The clearest early example is cascading behavior:

- An application runs on an EC2 instance.
- That relationship participates in an ownership/reliance path.
- Deleting the EC2 instance should do something defined to the application:
  delete it, tombstone it, block deletion, request confirmation, or record a
  flaw.

The important move is to define the ownership/reliance semantics declaratively
at the model or edge level and let the service layer enforce them. TAP should
not rely on each plugin hand-writing cascade traversals.

This is probably where embedded path membership has its strongest first use
case: it makes service-layer path checks cheap and standardized during ordinary
mutations.

## Cross-Dimensional Paths

Paths may cross dimensions a user is not allowed to see.

That creates a visibility question: if a user can see parts A and C of a path
but not hidden part B, what should the traversal return?

The path-node and embedded-membership approaches may handle this reasonably:
dimension-gated nodes are simply not returned, while visible participants still
can be collected. But the UX and security semantics need care. A partial path
can accidentally reveal that hidden structure exists, even when it does not
return the hidden object.

Future design needs to decide:

- Whether hidden path segments are omitted silently, summarized as redacted
  gaps, or cause the path traversal to be denied.
- Whether path names/tags themselves are dimension-scoped.
- Whether path breakage or protection checks can reveal inaccessible path
  membership.
- How path traversal works for the future AI system, where scoped/audited read
  behavior is non-negotiable.

## Visualization

Path visualization feels like one of the fun parts, but it should still follow
the data model rather than inventing separate visual-only path semantics.

Initial visual ideas:

- Glow or highlight around path nodes and edges.
- Overlay lines drawn over existing nodes and edges.
- Fade non-path graph objects into the background.
- Recolor path participants.
- Stack multiple path overlays with separate lines.
- Highlight only a branch or loop.
- Walk a path as an animation or stepper.

Glow/highlight is probably easiest but only represents one path well at a time.
Overlay lines may support multiple simultaneous paths because they can be
stacked or offset. There are likely better established visualization patterns to
study before committing.

## Why This Matters

Vannevar Bush's "As We May Think" points at the importance of connections. TAP's
entity/edge graph already takes that seriously: the connections between things
matter.

Paths add the next layer: the route through those connections matters too.

Without paths, TAP has a map of the territory and leaves the reader to decide
what journey matters. With paths, TAP can represent the way through the
territory as data: build flows, deploy flows, evidence flows, blast radius,
ownership, dependency, lifecycle, compliance argument, user journey, incident
chain, AI model lineage, or any other systemic route that deserves identity and
durability.

There is no way to know the full set of capabilities this unlocks across the
disciplines TAP may enter. But the intuition is strong: "the way" is not a
decorative layer over the graph. It is one of the things the graph is for.

## Future Spec Hooks

Likely specs or spec sections when this becomes implementation work:

- Entity/edge model: whether edge-to-edge path participation is allowed, and
  under what constraints.
- Path data model: path nodes, path steps, path membership, branch/loop
  addressing, tags, importance, and lifecycle.
- Service layer: path-aware mutation checks, path materialization, cascades,
  path breakage detection, and optimistic concurrency.
- Gryphon: path traversal syntax, result shape, ordering metadata, pathmaker
  queries, and validation cases.
- GRIFT: portable serialization of paths, path membership, and materialized
  path updates/removals.
- Authz/dimensions: partial path visibility, redaction, protection, and audit.
- Visualization: path overlays, multiple-path rendering, branch/loop rendering,
  and interaction model.
- AI system: read-only path traversal as an agent affordance, plus future
  propose-preview-approve path mutations.

## Future Prior Art Pass

No prior art search was performed for this capture note. The later design/spec
session should research at least:

- Neo4j Cypher path values, variable-length paths, and APOC path utilities.
  Revisit specifically: **APOC `apoc.path.expandConfig` / `subgraphNodes` / `spanningTree`
  configuration knobs** — `relationshipFilter`, `labelFilter`, `sequence`, uniqueness modes,
  min/max depth, and node allow/deny lists. These are the field-tested vocabulary graph users
  hand-roll per-query to define a trajectory; they are the closest prior art for what a *named
  path definition* will want to express declaratively (edge-type / label / depth / node
  allow-deny scoping). Note added 2026-07-06 from the Gryphon feature-demand APOC analysis —
  see `doc-gryphon-feature-demand.md` §7.3 (the knobs) and §5.1 (named-paths-replace-reachability
  framing). Cross-reference when the path-definition surface is specced.
- PostgreSQL recursive CTE path accumulation patterns.
- Workflow engines and DAG systems for branch/cycle representation.
- Distributed tracing span/trace path models.
- Provenance models that represent ordered derivation chains.
- Graph visualization approaches for multi-path overlays.
- Access-control behavior for partial graph traversal results.

The goal of that pass is inspiration and vocabulary, not code copying.
