# Viz Projection Specification

## Philosophy

A projection is TAP Viz's highest-order visual perspective on a graph domain. It defines how a person moves through a scene across multiple zoom-driven elevations, what layouts become active at each elevation, and how additional graph detail is introduced as the user descends into the view.

A projection is not a Cytoscape layout. A projection orchestrates layouts. It is the object that gives meaning to moving from a suite-level view to a product view, from a product view to a network view, and from a network view to a host or application view. It is the bridge between a human visual journey and the underlying graph data.

The first projection architecture should favor executable layout logic over attempting to encode all visual behavior in database JSON. Layouts are deterministic Cytoscape-specific functions stored as code assets and referenced by TAP-managed layout objects. This keeps complex layout behavior in code, keeps orchestration in TAP-owned projection metadata, and avoids forcing rich scene construction into an overly declarative storage format too early.

Projections should also be self-contained. A projection must be able to define a useful visual experience without requiring model-level hints or global nesting rules. Those may later exist as defaults, helpers, or optimizations, but the projection must remain capable of fully defining its own scene behavior.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Perspective | A projection defines a coherent visual perspective over a graph domain rather than a single static layout. |
| 2. | Elevation Driven | A projection organizes the visual journey into named zoom-driven elevations. |
| 3. | Layout Oriented | A projection activates one or more executable layouts at each elevation. |
| 4. | Incremental | A projection may introduce new graph data as the user moves into deeper elevations. |
| 5. | Self-Contained | A projection can define its own view behavior without depending on model-level display hints. |
| 6. | Cytoscape Native | Projection execution is built around Cytoscape runtime behavior and Cytoscape-specific layouts. |
| 7. | Evolvable | The projection contract should support future work on scaling, nesting, styling, and alternate elevation controls without redesigning the model. |

## Requirement Status

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-viz-projection-artifact | [Projection Artifact](#projection-artifact) | Implemented | Projection is a first-class TAP Viz artifact (`tap_viz.models.Projection`) |
| req-viz-projection-structure | [Projection Structure](#projection-structure) | Implemented | Monolithic v0 shape enforced via `FIELD_VALIDATION_SCHEMA` and `validate()` cross-field checks |
| req-viz-projection-elevation | [Elevation Model](#elevation-model) | Implemented | Zoom threshold watcher + double-tap handler in `runtime/projection.js` |
| req-viz-projection-layout-orchestration | [Layout Orchestration](#layout-orchestration) | Implemented | Tap layouts referenced inline by `js_file`, run serially per elevation |
| req-viz-projection-layout-runtime | [Layout Runtime](#layout-runtime) | Implemented | Runtime context (`cy`, `projection`, `elevation`, `trigger_reason`, `trigger_node`) passed to `execute(context)` |
| req-viz-projection-incremental-loading | [Incremental Loading](#incremental-loading) | Implemented | `character-view.js` demonstrates runtime sub-search via `runtime/search.js` |
| req-viz-projection-self-contained | [Self-Contained Execution](#self-contained-execution) | Implemented | LOTR saga projection defines nesting, dimensions, and layout without model-level hints |
| req-viz-projection-lotr-monolith | [LOTR Monolithic Example](#lotr-monolithic-example) | Implemented | Wired in `plugins/lotr/grift/web.grift.json` + saga-stage / character-view modules |

## Requirements

### Projection Artifact
----
RID: `req-viz-projection-artifact`
Status: `Implemented`

A projection is a first-class TAP Viz artifact that defines a reusable visual perspective over graph data.

#### Implementation

The projection artifact should be TAP-managed and reusable. It is not just a page-local config blob and not just a raw Cytoscape options object. A projection includes human-readable metadata plus projection-specific definition data.

#### Development

Treating projections as first-class artifacts allows the same perspective to be reused in multiple panels or pages and keeps complex scene orchestration out of panel-local config.

#### Future

Define the exact storage model and relation to existing layout entities in a follow-up pass.


### Projection Structure
----
RID: `req-viz-projection-structure`
Status: `Implemented`

A projection owns the top-level structure needed to initialize and advance a visual perspective.

#### Implementation

The initial projection shape is expected to include:

- `name`
- `description`
- `default_elevation`
- one or more `elevations`

For the first pass, projection should be defined as one monolithic object rather than split into separate elevation nodes or separately referenced layout nodes.

The v0 projection shape is:

- `name`
- `description`
- `default_elevation`
- `elevations`

`default_elevation` references an elevation by `name`.

#### Development

This keeps the first implementation easy to build and easy to revise. Projection can be broken into reusable referenced artifacts later, once the structure proves itself in a real working example.

#### Future

Break projections into reusable referenced artifacts once the v0 structure stabilizes.


### Elevation Model
----
RID: `req-viz-projection-elevation`
Status: `Implemented`

Elevations are named zoom-driven stages within a projection.

#### Implementation

Each elevation represents a meaningful visual altitude such as suite, product, network, host, application, or function.

The v0 elevation shape is:

- `name`
- `description`
- `zoom`
- `tap_layouts`
- `double_tap_targets`

Where:

- `zoom` is the zoom level at which the elevation becomes active
- `tap_layouts` is an ordered array of TAP layouts to run
- `double_tap_targets` is an array of:
  - `entity_type`
  - `target_elevation`

Elevation names must be unique within a projection.
Elevation zoom values must be unique within a projection.

There is exactly one active elevation at a time.

Elevation activation is TAP-managed and binds to Cytoscape zoom behavior through TAP-owned threshold logic rather than through a built-in Cytoscape elevation model.

Elevations may be entered by:

- projection initial load via `default_elevation`
- zoom threshold crossing
- double-tap on an eligible node type

When multiple zoom thresholds are crossed quickly, only the final target elevation is activated.

When an elevation is re-entered, its tap layouts rerun.

When a double-tap activates an elevation:

- the double-tap target elevation wins over ambient zoom-threshold activation
- TAP Viz temporarily disables other zoom-driven elevation transitions
- Cytoscape zoom animates to the target elevation's configured zoom level
- the target elevation's tap layouts run
- zoom-driven elevation transitions are re-enabled only after both:
  - the zoom animation completes
  - the target elevation's tap layouts complete

#### Development

Elevations are the key abstraction that let a projection describe a human visual journey across multiple levels of detail. They should be treated as first-class projection concepts rather than as incidental layout options.

Double-tap behavior allows semantic navigation between elevations that may not be reached naturally by simple zooming alone.

#### Future

Define elevation metadata, zoom thresholds, enter/exit semantics, and how multiple layouts are activated within an elevation.


### Layout Orchestration
----
RID: `req-viz-projection-layout-orchestration`
Status: `Implemented`

Projections orchestrate one or more layouts at each elevation rather than replacing the layout system.

#### Implementation

Layouts remain deterministic Cytoscape-specific executable functions. A projection decides when layouts run and which nodes they operate on. Multiple layouts may be active within the same elevation when they operate on different graph members or different scopes of the current scene.

In v0, a projection references inline tap layouts rather than separate layout entities.

The v0 tap layout shape is:

- `name`
- `description`
- `js_file`

`tap_layouts` run in array order.

#### Development

This requirement preserves a clean layering:

- projections define perspective and progression
- elevations define staging and activation
- layouts do the actual graph arrangement work

Keeping tap layout references inline for the first pass makes it easier to discover the right long-term artifact shape before introducing more graph-managed indirection.

#### Future

Define the runtime contract for executable layouts and how elevations invoke them.


### Layout Runtime
----
RID: `req-viz-projection-layout-runtime`
Status: `Implemented`

Tap layouts execute serially with a projection-scoped runtime context and may mutate the Cytoscape scene directly.

#### Implementation

In v0, a tap layout is a deterministic executable function referenced by `js_file`.

Tap layouts:

- run serially
- may fetch additional graph data
- may add or update nodes and edges
- may apply nesting, positioning, scaling, or styling logic
- operate against the whole active Cytoscape graph for now
- resolve completion asynchronously

The v0 completion model is:

- the layout mutates `cy` directly
- the layout resolves a promise when finished

The projection-scoped runtime context should exist and should include at least:

- current `cy`
- current projection definition
- current active elevation
- trigger reason such as:
  - `initial_load`
  - `zoom_transition`
  - `double_tap`
- optional triggering node for double-tap entry

The runtime must support a transition state for double-tap-driven elevation entry so ambient zoom-threshold activation can be suspended until the commanded elevation transition is complete.

#### Development

This runtime model keeps the first implementation simple and honest. Layouts are real code, operate directly on the Cytoscape scene, and are free to perform the work needed to make an elevation real.

#### Future

- Add viewport-aware runtime helpers for large complex datasets.
- Define the helper API contract precisely once the first layouts are implemented.


### Incremental Loading
----
RID: `req-viz-projection-incremental-loading`
Status: `Implemented`

Deeper elevations may gather additional graph data at runtime based on what is already present in the Cytoscape scene.

#### Implementation

In v0, fetch behavior should live inside tap layouts rather than in a separate elevation-level initiating search contract.

An elevation may therefore begin with one or more tap layouts that inspect the currently rendered graph members, perform follow-up search calls, and add newly required nodes and edges to the scene.

#### Development

This keeps projections responsive and avoids front-loading the entire graph problem at projection initialization time.

#### Future

Define the search and data-fetching helpers available to layout functions and how incremental additions are merged safely into the active scene.


### Self-Contained Execution
----
RID: `req-viz-projection-self-contained`
Status: `Implemented`

Projections must be able to define a complete visual experience without depending on model-level display hints or global nesting declarations.

#### Implementation

A self-contained projection may define the searches, elevations, layout sequencing, and nesting behavior required for that projection's visual experience. Model-level hints may later be used as defaults or helpers, but they are not required for a projection to function.

#### Development

Starting from self-contained projections ensures TAP can always support specialized visual experiences without forcing all rendering behavior into global metadata contracts.

#### Future

Define how self-contained projection logic interacts with model-level defaults, reusable helpers, and optional shared nesting utilities.


### LOTR Monolithic Example
----
RID: `req-viz-projection-lotr-monolith`
Status: `Implemented`

The LOTR plugin provides a worked monolithic projection example that exercises the v0 projection model.

#### Implementation

The worked example lives in the LOTR plugin as the "LOTR Saga Projection" node in `plugins/lotr/grift/web.grift.json`, wired to the "LOTR Saga Graph" panel via a `USES_PROJECTION` edge. The projection `definition` follows the monolithic shape from `req-viz-projection-structure` and orchestrates two elevations:

- `saga-level` (zoom 0.6) — runs the `saga-stage` tap layout at `plugins/lotr/static/lotr/js/projections/saga-stage.js`, which applies realm→location→character→artifact nesting, declares per-parent dimensions, and runs the dimensions plugin's recursive layout.
- `character-view` (zoom 1.4) — entered by double-tapping a character node, runs `plugins/lotr/static/lotr/js/projections/character-view.js`.

See the grift file for the canonical definition; this spec intentionally does not duplicate the payload.

#### Development

The LOTR example should be treated as the proving ground for the v0 projection architecture before projection data is split into more reusable pieces.

#### Future

Split LOTR projection pieces into reusable referenced artifacts only after the monolithic shape proves itself in practice.
