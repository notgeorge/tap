# Page Story Doctrine

Captured 2026-05-23, end of the samsite/compliance refactor session. George
articulated this as a guiding principle for the upcoming **build-page**,
**build-layout/projection**, and (newly named) **build-site/instance** skills.
Preserved verbatim — per the expand-don't-compress rule, strategy docs are
the user's prose, not the agent's distillation.

## The doctrine

> what really strikes me about the tables and pages we started from this
> morning is this:
>
> web pages are a story. they're designed to convey to humans a plot, an
> explanation, of something through text and visuals. the problem with what
> we started from is there was no context, concept of operations, semantic
> weight to what's there.
>
> it's the same with modern dashboard-heavy systems. they throw a bunch of
> dials and graphs and charts and stuff on the screen but without context
> none of it makes any sense. it's like walking into the cabin of a modern
> airliner — jesus yeah if i was trained as a pilot i'd know what's going
> on here, but to literally anyone short of that it's an overwhelming array
> of buttons, dials, lights, and a few control surfaces sprinkled in.
>
> what we want to get to with any page we create is a visual story that
> "reads" from the top-down and we should be able to describe that in the
> setup for the page, the narritive of the page should be expressable in
> human language and that page should sit in the greater context of what
> this instance is for, which will itself be a reflection of what the
> system or systems that its mapping are for.
>
> so it's stories all the way down.
>
> the same holds for graph visualizations — what is it that we're conveying
> here. in the version of the aws system on sam's site i can see three
> distinct story flows. there's how the website works. there's the
> compliance machinery, and there's pieces of the backend deploy process.
> there's a way to present those stories as separate, but related things,
> and there's going to be ways to dig deeper into each of them.
>
> in addition to his compliance story, there's now our compliance and
> verification story, which we're going to build once we get his story
> dialed in, so the sets of stories are:
>
>     website operation (and deployment)
>
>     compliance operation (and management)
>
>     grid-centric evaluation (of both).
>
> the stories should be clear from the very first landing page that these
> are the themes that we're dealing with.
>
> the end result is that someone coming to the site for the first time
> should intuit the stories — in sam's case he'll recognize his website's
> story made visual and real, his compliance tooling made visible and
> tangible, and then we'll sort out how to do our grid-centric evaluation
> (if we even get that far for the demo).
>
> so going forward, in the skills we're deriving for page building and soon
> layout / projection building and eventually for site / instance building
> (which we should begin formulating now so we can capture this and other
> lesson as we go), it's about stories.

## Refinement, named immediately after (2026-05-23)

> and one last idea — i think our grid-centric evalution will be threaded
> through. integrated as we go in a way that waves and enhances his story.
> new threads of grid-centric gold that highlight, re-inforce, strengthen

**So grid-centric evaluation is NOT a third parallel story alongside the
website and compliance flows — it is woven through both as enhancement.**
TAP's contribution is the colored thread running through the visitor's
reading of Sam's stories, not a separate self-aggrandizing "look what TAP
does" thread. Where a panel in Sam's compliance story would land flat as a
table, the grid-centric thread makes it shine: history overlays, joined
inventory checks, cross-system reconciliation, fed back into the moment
the visitor is already in.

This sharpens the design discipline considerably. Grid-centric callouts
that DON'T strengthen the visitor's understanding of Sam's story have no
place. The measure is: does this thread reinforce the story being told, or
distract from it.

## Implications named in the same breath

- **A new skill is on the horizon**: `build-site` / `build-instance` — formulate
  it now so it can absorb this lesson and others as we go.
- **The three samsite story flows** (website operation, compliance operation
  & management, grid-centric evaluation) become the demo's narrative spine —
  the landing page should announce them and let visitors choose a thread to
  follow.
- **Graph visualizations** are story surfaces too — same doctrine applies.
  The samsite AWS subgraph already contains three distinct narrative threads
  visible to a trained eye; we have to make them legible without that
  training.

## How this lands in the skills we already have or are building

- **build-collector** (already shipped) — ingestion-side; this doctrine
  doesn't change it directly, but it gives the *display* side a brief to
  work against, which reshapes how collectors choose to surface
  per-emission summary fields, derived rollups, "what's interesting" hints.
- **build-page** (forthcoming) — first prompt should be "what story does
  this page tell, in one sentence." Then "what's the opening paragraph
  (intro context). Then "what paragraphs (panels) carry the plot. Then
  layout. Then data sources. Story → structure → data, not the reverse.
- **build-layout / build-projection** (forthcoming) — projections are
  narrative editing decisions. Choosing what to surface IS choosing what
  the visitor reads first.
- **build-site / build-instance** (to formulate) — the instance-level
  narrative ("what is this TAP instance FOR") frames every page below it.
  The first page a visitor sees should announce the themes the instance
  is organized around. For samsite that's the three story flows above.

## Why this isn't just polish

It's the difference between TAP being "a graph database with some panels on
top" and TAP being "a story-telling surface that happens to use a graph as
its substrate." The first never goes mainstream because every consumer has
to learn the data model before they can read anything. The second works
because the page reads top-down like an article and the data model is
discoverable on demand by readers who want to dig deeper.

## Next steps (queued for Tuesday)

1. Formulate **build-site** skill — at minimum, what the site-level
   metadata should carry (purpose statement, story themes, landing-page
   thesis).
2. Begin sketching **build-page** skill around the
   "story-sentence first, panels later" flow.
3. Apply the doctrine to the samsite landing page (`/`) — currently it
   redirects to `/samsite` which is the AWS resource graph. The landing
   should announce the three story flows and let the visitor pick.
4. Apply the doctrine to `/samsite/compliance` — currently a table dump.
   Frame the page with an intro sentence ("here is what samsite is
   attesting and where the verification stands") and let panels follow as
   paragraphs.
