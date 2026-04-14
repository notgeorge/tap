# Viz Layouts Specification

## Philosophy

Tap layouts are executable TAP Viz layout functions. They are not raw Cytoscape built-in layouts such as `grid`, `cose`, or `breadthfirst`, and they are not TAP-owned declarative layout recipes stored entirely in JSON. A tap layout is a deterministic JavaScript module that can fetch data, add graph members, apply nesting, invoke Cytoscape layouts, position nodes manually, and adjust styling or scaling as needed to produce a meaningful scene.

Tap layouts exist because the graph views TAP wants to build are richer than what can be expressed cleanly through static configuration alone. A serious visual system needs to combine multiple behaviors in one execution: search, grouping, nesting, built-in Cytoscape layouts, manual positioning, and scene-specific logic. Treating layouts as executable code keeps that complexity in files where it can be tested, evolved, and reused.

Tap layouts are Cytoscape-oriented. Cytoscape remains the graph runtime that tap layouts control. A tap layout may call built-in Cytoscape layouts as one tool among several, but a tap layout is a TAP Viz runtime contract rather than a Cytoscape plugin contract.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Executable | Layouts are executable code assets rather than purely declarative database payloads. |
| 2. | Cytoscape Oriented | Layout execution is built for the Cytoscape runtime and may leverage built-in Cytoscape layouts. |
| 3. | Deterministic | Given the same context and underlying graph state, a layout should execute predictably. |
| 4. | Comprehensive | A layout may gather data, nest objects, position nodes, and refine the scene in one pass. |
| 5. | Reusable | Layouts can be reused across projections, pages, and other TAP Viz hosts. |
| 6. | File Based | Complex layout logic lives in JavaScript files shipped through TAP or plugin static assets rather than in DB code blobs. |
| 7. | Evolvable | The v0 layout contract should be minimal but strong enough to support future helpers, testing, and alternate hosts. |

## Requirement Status

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-viz-layout-artifact | [Layout Artifact](#layout-artifact) | Implemented | A tap layout is a TAP-managed artifact with a file-backed implementation |
| req-viz-layout-shape | [Layout Shape](#layout-shape) | Implemented | V0 tap layouts contain name, description, and js file reference |
| req-viz-layout-module-contract | [Module Contract](#module-contract) | Implemented | Tap layout JS modules export a standard async execute entrypoint |
| req-viz-layout-runtime-context | [Runtime Context](#runtime-context) | Implemented | Layouts receive a locked-in minimal runtime context; `trigger_node` is an optional hint, not a core operand |
| req-viz-layout-capabilities | [Layout Capabilities](#layout-capabilities) | Implemented | Layouts may fetch, mutate, nest, and position the Cytoscape graph; assert scene invariants on entry |
| req-viz-layout-execution | [Execution Model](#execution-model) | Implemented | Layouts execute serially under a host but failures do not block later layouts |
| req-viz-layout-runtime-modules | [Runtime Modules](#runtime-modules) | Implemented | Shared TAP Viz runtime utilities live in `tap_viz/static/tap_viz/js/runtime/` and are imported directly |
| req-viz-layout-warnings-errors | [Warnings And Errors](#warnings-and-errors) | Implemented | Layout runtime distinguishes warnings from errors via `onWarning` / `onError` callbacks |
| req-viz-layout-lotr-example | [LOTR Worked Example](#lotr-worked-example) | Implemented | LOTR saga-stage layout demonstrates the v0 executable layout contract |

## Requirements

### Layout Artifact
----
RID: `req-viz-layout-artifact`
Status: `Implemented`

A tap layout is a TAP-managed layout artifact with a file-backed implementation.

#### Implementation

A tap layout is a TAP Viz concept that references a JavaScript file stored in TAP or plugin static assets. The executable code lives in the file, not in the database payload itself.

#### Development

This keeps complex layout behavior versioned, testable, and shippable through normal TAP and plugin file mechanisms.

#### Future

Define how tap layouts should later relate to graph-managed layout nodes and other reusable artifact shapes.


### Layout Shape
----
RID: `req-viz-layout-shape`
Status: `Implemented`

The v0 tap layout object is intentionally minimal.

#### Implementation

The v0 tap layout shape contains exactly:

- `name`
- `description`
- `js_file`

`js_file` references a static asset path under the TAP or plugin JavaScript tree.

#### Development

The first layout shape should stay minimal until real working layouts force additional structure.

#### Future

Add more layout metadata only when real runtime needs justify it.


### Module Contract
----
RID: `req-viz-layout-module-contract`
Status: `Implemented`

Tap layout JavaScript modules export a standard async entrypoint.

#### Implementation

The v0 tap layout module contract is:

```javascript
export async function execute(context) {
  // layout logic
}
```

Each layout module exports exactly one layout entrypoint named `execute`.

#### Development

This keeps module resolution and runtime invocation simple for the first pass.

#### Future

If multiple exports become useful later, define that explicitly rather than loosening the v0 contract implicitly.


### Runtime Context
----
RID: `req-viz-layout-runtime-context`
Status: `Implemented`

Tap layouts receive a locked-in minimal runtime context.

#### Implementation

The v0 layout runtime context contains:

- `cy`
- `projection`
- `elevation`
- `trigger_reason`
- `trigger_node`

Field meanings:

- `cy`
  The active Cytoscape instance.
- `projection`
  The active projection definition when the layout is running under a projection host, otherwise `null`.
- `elevation`
  The active elevation definition when the layout is running under a projection host, otherwise `null`.
- `trigger_reason`
  Why this layout execution was initiated, such as:
  - `initial_load`
  - `zoom_transition`
  - `double_tap`
- `trigger_node`
  Optional hint passed through from the runtime when an elevation transition was triggered by a user gesture aimed at a specific node. Layouts **should not** depend on it for core operation — elevation layouts are scene-wide and must assert their target scene state for every applicable node, not just a trigger target. Carried in the context for advanced uses (e.g. highlighting) and for backward compatibility.

`projection`, `elevation`, and `trigger_node` are nullable so layouts may be reused outside projection-driven hosts.

#### Development

Keeping the context small makes the runtime contract more stable and pushes reusable functionality into shared imported modules rather than callback parameter sprawl.

#### Future

Add more context fields only when concrete runtime experience shows they are necessary.


### Layout Capabilities
----
RID: `req-viz-layout-capabilities`
Status: `Implemented`

Tap layouts may perform all scene work needed to get the desired pieces onto the Cytoscape board and put them in place.

#### Implementation

In v0, a tap layout may:

- fetch additional graph data
- add or update nodes and edges
- hide or un-hide existing nodes and edges (via the `.tap-elevation-hidden` class convention described in `spec-viz-projection.md`)
- apply or change nesting
- invoke one or more built-in Cytoscape layouts
- position nodes manually
- adjust styling or scaling
- inspect the whole active Cytoscape graph

Layouts are authoritative for nesting decisions during their execution.

Under a projection host, layouts are also responsible for **asserting scene invariants on entry**: each layout should put the scene into the state its elevation requires regardless of what the previous elevation left behind. There is no separate exit hook — teardown is handled implicitly by the next elevation's entry assertion. This keeps each layout's behavior self-contained and lets the runtime stay oblivious to elevation-specific cleanup rules.

When a layout uses nesting, it should do so through the standard TAP Viz nesting process defined in `spec-viz-nesting.md`. That process uses the Gryphon-like nesting relationship format as the canonical expression for layout-owned nesting.

If a layout changes an existing nesting relationship and re-nests an object elsewhere, the runtime must emit a `layout_nesting_override` warning.

#### Development

This requirement reflects the central design decision of the new layout model: one layout does whatever work it needs to do to make its scene real.

#### Future

- Add viewport-aware optimization helpers for very large graph scenes.


### Execution Model
----
RID: `req-viz-layout-execution`
Status: `Implemented`

Tap layouts execute serially under a host runtime, but a failed layout does not block later layouts from running.

#### Implementation

Under a projection elevation or another TAP Viz host, tap layouts:

- execute serially in the order defined by the host
- mutate `cy` directly
- signal completion by promise resolution

If a layout throws or rejects:

- the runtime records an error for that layout
- the failed layout stops
- later layouts in the same host sequence still run

This behavior exists so partially successful visual progress remains visible and debuggable even when one layout fails.

#### Development

These are visuals, not mission-critical transactions. It is more valuable to preserve visible progress and inspect partial success than to abort the whole rendering pipeline at the first failure.

#### Future

Define richer runtime reporting and visualization of per-layout execution state.


### Runtime Modules
----
RID: `req-viz-layout-runtime-modules`
Status: `Implemented`

Shared TAP Viz runtime utilities live in static JavaScript modules and are imported directly by layout files.

#### Implementation

Shared utilities are not passed in `context`. Layout implementations import them directly from TAP Viz-owned static JavaScript modules.

The v0 path namespaces are:

- `tap_viz/static/tap_viz/js/projections/`
  executable projection and layout files
- `tap_viz/static/tap_viz/js/runtime/`
  shared TAP Viz runtime modules

Plugin-shipped layout files may also live under corresponding plugin static paths while following the same conceptual split between executable layout modules and shared runtime support.

#### Development

This keeps the runtime context small and lets utility code evolve as normal JavaScript modules rather than callback payload baggage.

#### Future

Define plugin-specific path conventions more explicitly once the first plugin layouts are moved into place.


### Warnings And Errors
----
RID: `req-viz-layout-warnings-errors`
Status: `Implemented`

Tap layout runtime distinguishes warnings from errors.

#### Implementation

Warnings represent recoverable issues where execution may continue.

Errors represent a thrown exception or rejected promise from a layout execution.

The runtime should support both warning and error reporting and should record them at layout granularity.

The v0 warning category `layout_nesting_override` means:

- a layout changed an existing nesting relationship for an object
- the object was re-nested elsewhere
- execution continued

#### Development

Keeping warnings and errors separate makes layout failures easier to reason about and keeps recoverable scene oddities from being treated as fatal execution failures.

#### Future

Integrate layout warnings and errors into TAP's richer runtime diagnostics once those systems are defined.


### LOTR Worked Example
----
RID: `req-viz-layout-lotr-example`
Status: `Implemented`

The LOTR saga-stage layout should be the first worked example of the executable tap layout contract.

#### Implementation

Representative module shape:

```javascript
import { executeSearch } from "/static/tap_viz/js/runtime/search.js";
import { applyNesting } from "/static/tap_viz/js/runtime/nesting.js";

export async function execute(context) {
  const { cy, projection, elevation, trigger_reason, trigger_node } = context;

  if (trigger_reason !== "initial_load") {
    return;
  }

  const result = await executeSearch({
    query: "lotr saga realm/locations/characters/artifacts union search"
  });

  // Add or update graph members in Cytoscape.
  // Apply realm -> location -> character nesting for this layout.
  // Use built-in Cytoscape grid behavior where helpful.
  // Adjust positions until the saga scene is presentable.

  applyNesting(cy, {
    relationships: [
      "realm contains location",
      "location contains character"
    ]
  });

  // Normal completion is promise resolution.
  void projection;
  void elevation;
  void trigger_node;
}
```

This example is illustrative rather than normative in its exact module internals, but it should demonstrate:

- direct imports from TAP Viz runtime modules
- the standard `execute(context)` contract
- the `initial_load` trigger reason
- whole-graph Cytoscape access
- fetching, nesting, and positioning inside one layout execution

#### Development

The LOTR example is the proving ground for the v0 layout model and should be treated as the place where the contract is validated before the model grows.

#### Future

Replace illustrative placeholder paths and helper names with the real plugin-backed LOTR layout module once implementation is finalized.
