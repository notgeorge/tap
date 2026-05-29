# Agent-Legibility Doctrine

Captured 2026-05-29, end of a Friday brainstorm about the eventual grid-native
AI agent (`tap_ai`, still unbuilt). George articulated the destination; the
design discipline below was synthesized in that conversation and is captured
here as a standing lens for development going forward. Brainstorm-stage — not a
spec, not committed scope. It's a *lens*, the way the [Page Story Doctrine](page-story-doctrine.md)
is a lens.

## The destination (George, verbatim)

On where the AI agent is going:

> in the very near soon we want the ability to pop open a chat box inside the
> web ui and interface with a dedicated agent that is grid-native, connected to
> the current instance, and capable of traversing the grid with us.

> v0 is read only, which needs to be fully worked out before we can trust it to
> take actions. the eventual goal is exactly [a propose → human-approves →
> apply loop].
>
> eventually i won't be working in a separate claude session inside a terminal
> when building plugins on the grid. we'll be inside TAP building it with all
> the context, capabilities, and affordances we need.

That last line is the north star: **TAP, eventually, is built from inside TAP** —
by a grid-native agent working alongside a human, with full context and
affordances. Today that work happens in a separate terminal Claude session
editing files. The doctrine is about closing that gap deliberately.

## The doctrine

The affordances a future in-grid builder-agent will need are, almost without
exception, the same things that make the grid **legible and reachable** for any
consumer. The principles already in play — declarative shapes over code, JSON
Schema on every format, discoverable capabilities, self-describing artifacts —
were adopted for good-taste reasons. The agent endgame is the *why* that
justifies and sharpens them. So this is mostly **"keep going on the axis we're
already on, and treat the agent as the reason."**

It reduces to one standing design test, a sibling of "does this advance the story":

> **Could the grid-native agent understand and use this without reading the Python?**

Where the answer is "no," that's the work.

## The axis that matters most: data vs. the code wall

A terminal agent builds by editing Python, running a migration, restarting a
worker. An in-grid agent **cannot do that from a chat box.** So the dominant
question for everything we build is: *is this expressible as **grid data**, or is
it trapped behind **code + migration + restart**?*

- **Data side (agent-buildable, eventually):** pages, panel *instances*, searches,
  projections / elevations / layouts / arrangements, dimensions, edge *instances*,
  GRIFT batches, keystones. A large share of "build a view / a query / a
  dashboard" is already pure service-layer data ops — no code, no restart.
- **Code wall (needs a deploy affordance the agent doesn't have):** new entity
  *types* (model class + migration), new edge *types*, new panel *types*,
  collectors, Gryphon grammar, viz layout JS.

Two moves follow: **(a) make the data side ergonomic and complete** — it's the
surface the agent builds on first and most — and **(b) name the code wall
consciously.** When something must be code, fine, but log it as "agent can't
build this yet" so the wall is visible, not accidental.

**The keystone is the seed of crossing the wall.** A node carrying `context_json`
*plus* `context_schema_json` is a *data-defined, self-describing shape* — a
micro-version of "a type whose structure is data, not a hand-written class."
Generalized, that pattern points at agent-definable node types without
migrations. We already have a working proof-of-concept on the grid.

## Affordances we don't support yet (the gaps)

Prioritized; several already started.

1. **The universal access layer — authed, scoped, audited read API.** Real gap
   today (Gryphon is `auth=None`; no read-activity log). Everything the agent
   does flows through this; build it for hygiene, the agent just forces it.
   This is "Phase 0" and it is not AI work — it's API hardening that helps
   humans too.
2. **Exhaustive self-description / a capability manifest.** Discovery exists for
   entity types; the agent also needs a queryable map of edges + their from/to
   constraints, searches, pages, panels, projections, collectors, dimensions,
   and Gryphon's own grammar — each **with human descriptions**. Discipline:
   every new capability ships its discovery metadata in the same change (the way
   a new format ships its JSON Schema).
3. **Machine views alongside human views.** Pages render HTML only; the agent
   needs the page's declarative data (panels → their resolved search results) as
   a structured surface. Nearly free because pages are already declarative — the
   endpoint just doesn't exist. Make "data twin" a standing deliverable for every
   human surface. (No Playwright — the agent consumes data, not pixels.)
4. **The change spine: propose → preview → approve → apply → reversible +
   attributed.** How read-only-v0 becomes write-capable safely *without ever
   letting the model write directly*: the agent emits a **GRIFT batch proposal**;
   a human previews it (the `import_plugin_grift --dry-run` fixed 2026-05-29 is a
   brick in this wall); approves; it applies through the service layer;
   history/FLIP makes it reversible; provenance tags it "AI-proposed,
   human-approved." Most pieces exist in fragments; the gap is composing them
   into one previewable proposal primitive. Build *toward* this shape now — treat
   GRIFT-batch-as-proposal as the canonical future write path.
5. **Context parity.** The terminal agent has specs + skills (codified build
   procedures like `add-model`) + the keystone at hand. The grid agent has the
   keystone (new) but specs are files and skills are terminal-only. Make specs
   and the build-procedures the agent will need **readable by the agent**. The
   skills are especially valuable — they're exactly the "how to build X in TAP"
   knowledge an in-grid builder needs.

## How to shape development going forward (process)

- **Apply the agent-legibility test** as a standing lens, not a heavyweight gate.
- **Keep the declarative bias; name the code wall** when you hit it.
- **Build human + machine surfaces together** — resist shipping an HTML-only page
  or a code-only capability without its data/discovery twin. Cheap alongside,
  expensive to retrofit.
- **Don't build the agent yet — build the substrate it stands on** (Phase 0,
  discovery, machine views, the proposal spine). The agent is the easy, fun part
  once the grid is fully legible and reachable; the substrate is the real work,
  and it's all dual-purpose (better for humans too).

## The read-only gate (non-negotiable for v0)

`tap_ai` must not write to core graph state in v0 (canonical rule). The agent
**traverses, summarizes, suggests**. The brain-in-a-vat architecture (LLM emits
tool-call requests; the backend executes them authenticated/scoped/audited; the
provider never gets instance credentials) is what makes that enforceable, and it
bounds prompt-injection blast radius to "can be made to say something dumb, can't
be made to do anything outside read scope." Writes arrive only via the proposal
spine above, human-approved — never the model's hand on the grid directly.

## Why this isn't just hygiene

The same axis runs through it as the Page Story Doctrine: it's the difference
between TAP being "a graph database with panels and an AI bolted on" and TAP
being a substrate that is legible and reachable end-to-end — by humans reading
top-down, and by an agent traversing through one scoped, audited, declarative
API. A grid an AI can build on is just a grid that's fully legible and fully
reachable. We've been building exactly that. The endgame says keep going, and
make "the agent could understand and use this" the reason.

## Next steps (queued — Tuesday-and-beyond, not now)

1. **Phase 0 first**: auth + read-scope + activity logging on the Gryphon/read
   API. Prerequisite for everything; good hygiene regardless.
2. Sketch the **capability manifest** — extend discovery beyond entity types.
3. Define the **page machine-view** endpoint (data twin of the rendered page).
4. Compose the **GRIFT-proposal / dry-run-preview / approve / apply** primitive.
5. Decide how **specs + skills** become agent-readable context.
6. Only then: the chat box (`tap_ai`), brain-in-a-vat, single provider, one
   `gryphon_query` tool, off-spine conversation storage, read-only.
