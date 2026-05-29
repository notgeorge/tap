# Future Seam: Trace Overlay on a System Model

Captured 2026-05-29, end of the "nitpicking" session. A thinking-out-loud chat
about observability that produced one idea worth keeping. **This is a named
future seam, not scheduled work** — do not build it now. Its purpose is to
shape a couple of cheap near-term decisions so the later version is a join,
not a retrofit. Demand signal: the customer-hosted inflection (when "reproduce
it locally" stops being an option). Until then, parked.

## How we got here

The chat walked down a ladder:

1. **Observability on samsite (the modeled site)?** Mostly *too thin* — it's an
   S3+CloudFront static site plus a daily cron Lambda. Classic OTel/RED metrics
   would watch a sleeping system. The *meaningful* version there is ingesting
   the runtime KSI signal (`ksi-signal-runtime.json`, which TAP does **not**
   currently fetch — see the compliance collector's `artifact_manifest.json`)
   and modeling deploy↔runtime **drift**. That's a separate, on-thesis idea;
   noted here only as the thing this conversation started from.

2. **Observability on TAP itself?** A genuinely good target, *unlike* samsite:
   real multi-layer work (request → page → panels → Gryphon → generated SQL →
   recursive CTEs over entity/edge tables), live collectors, GRIFT batches, a
   background worker. And it has the silent-failure classes observability is
   built to catch: Gryphon wrong-result/silent-drop (which we already hold as
   "not okay"), CTE blowups/N+1, GRIFT rejections, the stale-worker pain.
   **Caveat:** solo-on-a-laptop means you can *reproduce* everything today, so
   the present-day value is dev-insight/profiling, not production debugging.
   Real observability earns its keep at the customer-hosted inflection.

3. **The temptation we resisted (again):** logging/telemetry **to the grid**.
   Spans/datapoints as Entity rows is a category error. Keep resisting.

4. **The idea worth keeping** (this doc): the *inverse* of that category error.

## The idea

Keep spans **out** of the grid. Instead:

- **Grid holds the map** — an authored/derived model of TAP's own architecture
  (components, codepaths, the DB, collectors, Gryphon, web layer, and their
  relationships). Stable, low-cardinality. TAP's home turf.
- **Jaeger holds the journeys** — OTel spans, local-only (all-in-one binary,
  OTLP in, and a query API to pull traces back out). High-cardinality,
  ephemeral. Jaeger's home turf. (Local by requirement — no SaaS.)
- **The visualization is the join** — pull traces from Jaeger's query API, map
  each span to a model node, and **project** the telemetry onto the system
  model in tap_viz: per-node heat/count/p-latency, lit call paths on edges.
  Computed at view time, **never persisted to the grid.**

## Why this beats the vendors' own service maps

Honeycomb/Jaeger **infer topology from the telemetry** — emergent, noisy, only
shows exercised paths, reshuffles with sampling. Projecting onto an authored
ground-truth model instead buys what they structurally can't:

- **Negative space** — cold/dead/never-run components are visible, because the
  map exists independently of whether spans touched it.
- **Stable topology** — the diagram is the system, not a sampling artifact.
- **Time-scrubbing against history** — the grid has history; overlay traces
  from window T onto the model *as it was at T*. The vendors have the traces
  but no durable structural model to scrub against.

George's framing: "a visual dimension Honeycomb should have done years ago."
The reason they didn't is they never had an authored model — only what the
wire implied.

## Two existing investments this rides on (exploit them)

1. **Callsite-addressable logging is the join key.** "The logger name IS the
   callsite path" + the `[<hex>]` site tokens (spec-tap-logging Option A) is
   already a callsite-addressable identity scheme. OTel spans carry
   `code.namespace` / module path. **The one cheap do-it-now move:** when you
   next touch logging or add any tracing, make span identity == model-node
   identity == log-site namespace. Lock that alignment and the later overlay is
   a join, not a retrofit. This is the only thing that needs deciding *now*.

2. **Registry-backed discovery is the model generator.** Node types, edge
   types, collectors, Gryphon capabilities already self-describe through the
   discovery system. So "a model of TAP in TAP" isn't a hand-drawn diagram that
   rots — its spine is introspectable from the registry, which is what keeps it
   from drifting away from the code as the system grows.

And the viz end is the *easiest* part: tap_viz already renders the grid as
cytoscape, so the overlay is a decoration layer over a canvas that exists.

## The risk to design around

Disclosure discipline pointed inward (same `unknown ≠ false` rule we apply to
stale AWS metrics): a cold node must distinguish **"this code genuinely never
ran"** from **"this code isn't instrumented yet."** The overlay needs a third
state for *no coverage here* — otherwise empty silently reads as dead, and the
pretty picture lies in exactly the seductive way.

## What to do now vs. later

- **Now:** nothing to build. Only constraint — when logging/tracing identity
  decisions come up, honor the "span identity == model-node identity ==
  log-site namespace" alignment above.
- **Later (at the customer-hosted inflection):** stand up local Jaeger + OTel
  instrumentation, derive the system model from the registry, build the
  tap_viz projection layer with the three-state coverage rule.
