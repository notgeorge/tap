# Viz Panel Specification

## Philosophy

The viz panel is the primary runtime surface for human-facing graph visualization inside TAP pages. It brings graph-native data into the existing page and panel system so people can inspect and navigate meaningful slices of the grid without leaving the broader page context.

The viz panel owns runtime concerns such as loading a layout, receiving resolved page inputs, rendering a scene, and handling user navigation within the panel. It does not own the definition of the graph view itself. Data retrieval, graph assembly, containment, placement, and presentation rules belong to the referenced layout.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Hostable | Viz panels must fit cleanly into the existing TAP page and panel framework. |
| 2. | Input-Aware | Viz panels must consume resolved page inputs through the existing panel input contract. |
| 3. | Navigable | Viz panels must support core graph navigation behaviors such as pan, zoom, fit, selection, and optional popovers. |
| 4. | Layout-Driven | Viz panels must render a referenced layout entity rather than embedding full graph logic directly in panel config. |
| 5. | Safe | Viz panels must fail safely and remain read-only in v1. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-viz-panel-hosting | [Panel Hosting](#panel-hosting) | Implemented | Viz panels are hosted by the existing TAP panel framework |
| req-viz-panel-config | [Panel Configuration](#panel-configuration) | Proposed | Panel config covers layout reference and runtime host behavior |
| req-viz-panel-inputs | [Panel Inputs](#panel-inputs) | Proposed | Viz panels consume resolved page inputs and pass them into layout execution |
| req-viz-panel-layout-reference | [Layout Reference](#layout-reference) | Proposed | Viz panels reference reusable layout entities |
| req-viz-panel-runtime-nav | [Runtime Navigation](#runtime-navigation) | Implemented | Pan, zoom, and fit are required runtime behaviors |
| req-viz-panel-runtime-selection | [Runtime Selection](#runtime-selection) | Implemented | Selection is part of the core runtime contract |
| req-viz-panel-node-nav | [Node Navigation](#node-navigation) | Implemented | Clicking a graph node navigates to the TAP object viewer for that entity |
| req-viz-panel-runtime-popover | [Runtime Popovers](#runtime-popovers) | Proposed | Popovers are an optional but standardized runtime behavior |
| req-viz-panel-landing-default | [Landing Page Default](#landing-page-default) | Implemented | Default landing page should host a viz panel showing the graph in grid layout |
| req-viz-panel-readonly | [Read-Only Runtime](#read-only-runtime) | Implemented | Viz panel runtime is read-only in v1 |
| req-viz-panel-failure-handling | [Failure Handling](#failure-handling) | Implemented | Viz panels fail safely within the panel shell |

### Panel Hosting
----
RID: `req-viz-panel-hosting`
Status: `Implemented`

The viz panel is hosted through the normal TAP panel framework and participates in the same page composition rules as other panel types.

#### Status Details
This requirement makes viz a first-class panel citizen instead of a special page-level exception.

#### Implementation
- A viz panel is a TAP panel type rendered inside a page slot.
- It uses the generic panel lifecycle for:
  - page placement
  - asset loading
  - runtime rendering
  - panel error fallback
- Viz-specific runtime behavior may be implemented in `tap_viz`, but hosting remains owned by the general panel system.

#### Development
The panel shell is the right place to standardize composition, while viz-specific logic stays inside the viz subsystem.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-panel-hosting-1 | Existing Host Framework Used | Implemented | Viz panels render through the existing TAP panel framework rather than a separate host model. | `GraphPanel` registered via `panel_type_registry` in `tap_viz/apps.py` |
| req-viz-panel-hosting-2 | Page Slot Compatible | Implemented | Viz panels are placeable in normal TAP page slots. | Grid overview panel on landing page |
| req-viz-panel-hosting-3 | Generic Panel Error Path Preserved | Implemented | Viz panel failures still resolve through the standard panel error behavior. | Panel error fragment via `tap_web` panel view handler |

#### Future
If full-screen dedicated viz routes are needed later, define them as alternate hosts for the same panel/runtime contract.


### Panel Configuration
----
RID: `req-viz-panel-config`
Status: `Proposed`

Viz panel configuration is limited to host/runtime concerns. It does not embed the layout pipeline itself.

#### Status Details
This keeps a clean separation between panel instance concerns and reusable layout definition concerns.

#### Implementation
The canonical panel config shape in v1 includes:

- `layout_entity_id` required
- `initial_viewport` optional
- `chrome` optional object:
  - toolbar enabled
  - fullscreen enabled
  - fit control enabled
- `interaction` optional object:
  - selection enabled
  - popover enabled
  - minimum zoom
  - maximum zoom

The panel config does not define:
- search steps
- placement actions
- containment rules
- styling rules

#### Development
Panel config should stay small enough that the same layout can be reused in multiple panels with different host behavior.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-panel-config-1 | Layout Reference Required | Proposed | Viz panel config requires a referenced layout entity identifier. | |
| req-viz-panel-config-2 | Host Behavior Only | Proposed | Viz panel config is limited to host/runtime behavior rather than embedding layout logic. | |
| req-viz-panel-config-3 | Reuse Preserved | Proposed | A layout can be reused by multiple panel instances with different panel-level runtime settings. | |

#### Future
If common panel chrome patterns emerge, define shared config helpers instead of expanding the core panel config arbitrarily.


### Panel Inputs
----
RID: `req-viz-panel-inputs`
Status: `Proposed`

Viz panels consume resolved page inputs through the existing panel input contract and pass those values into layout execution.

#### Status Details
This requirement aligns viz with the TAP page/panel input model from the start so viz can participate in page-level coordination rather than becoming a closed island.

#### Implementation
- Viz panels declare panel-local input names as needed.
- Pages remain responsible for mapping page variables to panel-local names.
- Viz panels receive resolved input objects through the canonical panel input event contract.
- Layout execution may bind resolved panel inputs into search execution inputs and layout inputs.
- On input change, the panel reruns layout execution deterministically for the new input state.

#### Development
Input binding belongs at the panel/layout boundary, not inside renderer-native configuration.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-panel-inputs-1 | Existing Panel Input Contract Used | Proposed | Viz panels consume resolved inputs through the existing TAP panel input model. | |
| req-viz-panel-inputs-2 | Layout Execution Input Binding Allowed | Proposed | Layout execution may bind resolved panel inputs into layout and search inputs. | |
| req-viz-panel-inputs-3 | Deterministic Rerun On Input Change | Proposed | Viz panel runtime reruns layout execution deterministically when panel inputs change. | |

#### Future
Define richer input typing and validation in the layout spec once common patterns emerge.


### Layout Reference
----
RID: `req-viz-panel-layout-reference`
Status: `Proposed`

Every viz panel references a reusable viz layout entity that defines what graph view is rendered.

#### Status Details
This requirement prevents panel instances from becoming one-off graph-definition containers.

#### Implementation
- The panel references one default layout entity.
- The layout reference is stable and reusable.
- The panel may provide runtime inputs and host settings, but the layout defines the graph view.

#### Development
The panel should be thought of as “a runtime host for a layout” rather than “the place where the graph view is authored.”

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-panel-layout-reference-1 | Default Layout Reference Exists | Proposed | A viz panel references one default layout entity for runtime rendering. | |
| req-viz-panel-layout-reference-2 | Layout Remains Reusable | Proposed | The referenced layout is not owned by the panel instance and may be shared elsewhere. | |

#### Future
Later work may define layout switching or adjacent layouts, but that is not part of v1.


### Runtime Navigation
----
RID: `req-viz-panel-runtime-nav`
Status: `Implemented`

The viz panel supports core graph navigation behavior: pan, zoom, and fit.

#### Status Details
These are the minimum runtime behaviors required to make the panel feel like a serious graph surface rather than a static image.

#### Implementation
- Users may pan the graph.
- Users may zoom in and out.
- Users may fit the current scene to the viewport.
- Zoom constraints may be configured at the panel level.

#### Development
This requirement intentionally stops short of drilldown or pivots. Those are later interaction features, not part of the first runtime contract.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-panel-runtime-nav-1 | Pan Supported | Implemented | The viz panel supports panning the current graph scene. | `userPanningEnabled: true` in `panel-graph.js` |
| req-viz-panel-runtime-nav-2 | Zoom Supported | Implemented | The viz panel supports zooming the current graph scene with panel-level zoom constraints. | `userZoomingEnabled: true`; `minZoom` set post-layout via `layoutstop` |
| req-viz-panel-runtime-nav-3 | Fit Supported | Implemented | The viz panel provides a fit-to-view behavior for the current graph scene. | Fit button in `_attachToolbar`; `cy.fit()` |

#### Future
If overview maps or saved viewport states become important, specify them separately rather than overloading the base navigation contract.


### Runtime Selection
----
RID: `req-viz-panel-runtime-selection`
Status: `Implemented`

Selection is part of the core runtime contract for nodes and edges shown in a viz panel.

#### Status Details
Selection is required so the panel can support meaningful inspection and future integrations without requiring editing behavior.

#### Implementation
- Nodes may be selected.
- Edges may be selected.
- The selected graph object may drive:
  - visual highlighting
  - optional popover content
  - future integrations not defined in this spec

#### Development
Selection is the minimal stateful interaction that makes inspection possible without dragging in full editing complexity.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-panel-runtime-selection-1 | Node Selection Supported | Implemented | The panel supports selecting visible nodes. | Cytoscape `boxSelectionEnabled: true`; `userZoomingEnabled: true` |
| req-viz-panel-runtime-selection-2 | Edge Selection Supported | Implemented | The panel supports selecting visible edges. | Cytoscape default selection behavior |
| req-viz-panel-runtime-selection-3 | Selection Affects Presentation | Implemented | Selection changes visible runtime state such as highlighting or inspection context. | `:selected` style rule changes `background-color` and `line-color` |

#### Future
If multi-select becomes important, define it as a deliberate extension rather than assuming it implicitly.


### Node Navigation
----
RID: `req-viz-panel-node-nav`
Status: `Implemented`

Clicking a graph node navigates to the TAP object viewer for that entity.

#### Implementation
- Node click (tap) triggers a browser navigation to `/object/{entity_type}/{url_id}/`.
- `url_id` is a `{slug}--{entity_id}` string serialized into every node payload by `_serialize_entity`.
- The slug is derived from the entity name via `django.utils.text.slugify`.
- Edge clicks do not navigate; only node taps are wired.
- Navigation replaces the current page (`window.location.href`).

#### Development
Node navigation is read-only and requires no graph mutation. It uses the same viewer URL contract as any other TAP object viewer entrypoint.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-panel-node-nav-1 | Node Tap Navigates | Implemented | Tapping a graph node navigates to `/object/{entity_type}/{url_id}/`. | `panel-graph.js` `cy.on("tap", "node", ...)` |
| req-viz-panel-node-nav-2 | URL ID In Node Payload | Implemented | Every serialized node carries a `url_id` field usable as the viewer URL segment. | `_serialize_entity` in `orm_compiler.py` |
| req-viz-panel-node-nav-3 | Edge Tap Does Not Navigate | Implemented | Clicking an edge does not trigger viewer navigation. | |

#### Future
If richer in-panel inspection (popovers, side panels) is later implemented, node tap behavior may be overridden by that contract.


### Runtime Popovers
----
RID: `req-viz-panel-runtime-popover`
Status: `Proposed`

Viz panels may provide popovers for selected nodes or edges, but popovers are optional in v1.

#### Status Details
The panel should support richer inspection surfaces without making them mandatory for every initial implementation.

#### Implementation
- Popovers, when enabled, are driven by selection or click behavior.
- Popover content may include summary information about the selected graph object.
- Popovers are panel/runtime behavior, not layout-definition logic.

#### Development
Keep popovers optional in the first contract so the runtime can ship without overcommitting to a detailed inspection UI too early.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-panel-runtime-popover-1 | Popover Capability Standardized | Proposed | The spec defines optional popovers as a standard viz panel runtime behavior. | |
| req-viz-panel-runtime-popover-2 | Popovers Are Optional | Proposed | Popovers may be disabled without making the panel invalid. | |

#### Future
Define structured inspection cards, related actions, and deep-linked details in a later interaction spec.


### Landing Page Default
----
RID: `req-viz-panel-landing-default`
Status: `Implemented`

The default landing page should host a viz panel that shows all visible graph nodes and edges using a grid-style layout.

#### Status Details
This requirement captures the current high-priority product goal of making the landing page show the graph through the new panel-native architecture.

#### Implementation
- The default landing page contains a viz panel.
- That panel’s default layout renders all nodes and edges in a graph-wide view.
- The initial placement mode for this layout is grid-oriented.

#### Development
This requirement is primarily a product target, but it also serves as the reference implementation for panel-native graph rendering.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-panel-landing-default-1 | Landing Page Uses Viz Panel | Implemented | The default landing page hosts a viz panel under the normal page/panel system. | Grid Overview panel on the seeded landing page |
| req-viz-panel-landing-default-2 | Full Graph View Used | Implemented | The panel’s referenced default layout renders all visible nodes and edges. | `list-concepts` search runner via graph panel |
| req-viz-panel-landing-default-3 | Grid Placement Used Initially | Implemented | The default layout uses grid-style placement in the initial implementation target. | `cytoscape:cose` layout (default in `_buildLayout`) |

#### Future
The landing-page layout may later become more curated or contextual, but the panel-native architecture should remain.


### Read-Only Runtime
----
RID: `req-viz-panel-readonly`
Status: `Implemented`

The viz panel runtime is read-only in v1.

#### Status Details
This keeps the runtime inspection-focused and prevents editor behavior from leaking into the panel contract before permissions and draft semantics exist.

#### Implementation
- Allowed:
  - render
  - pan
  - zoom
  - fit
  - select
  - optional popovers
- Excluded:
  - node creation
  - edge creation
  - graph mutation
  - saved drag repositioning
  - runtime layout editing

#### Development
Any future editing surface should be specified separately and should not implicitly redefine runtime panel behavior.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-panel-readonly-1 | Runtime Navigation Allowed | Implemented | The panel permits non-mutating runtime navigation and inspection actions. | Pan, zoom, fit, select, node tap navigate |
| req-viz-panel-readonly-2 | Runtime Mutation Excluded | Implemented | The panel excludes graph and layout mutation from the v1 runtime contract. | No write paths in `panel-graph.js` |

#### Future
If inline editing is later desired, it should be gated behind a separate spec and permission model.


### Failure Handling
----
RID: `req-viz-panel-failure-handling`
Status: `Implemented`

Viz panel failures must fail safely inside the panel shell and surface useful runtime warnings without breaking the hosting page.

#### Status Details
Graph rendering and layout execution are more complex than simple text rendering, so safe failure behavior must be explicit.

#### Implementation
- If the layout cannot be loaded, the panel fails with the standard panel error behavior.
- If layout execution produces warnings, the runtime may surface warning state while still rendering.
- If an unsupported step or formatter is encountered, the failure must be explicit and isolated to the panel.

#### Development
Prefer explicit failure or warning surfaces over silent partial behavior that leaves the graph view misleading.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-panel-failure-handling-1 | Host Page Remains Intact | Implemented | Viz panel failure does not break page rendering outside the affected panel. | Panel error fragment from `tap_web` panel view handler; HTMX swap isolates failures |
| req-viz-panel-failure-handling-2 | Warning State Allowed | Implemented | Recoverable layout/runtime warnings may be surfaced without treating the entire render as fatal. | Empty-nodes early return renders inline message in the panel container |
| req-viz-panel-failure-handling-3 | Unsupported Behavior Fails Explicitly | Implemented | Unsupported layout behavior fails explicitly rather than degrading silently. | Guard clause in `initGraph` returns without rendering if required elements are missing |

#### Future
Define richer diagnostics, telemetry, and operator-facing debugging tools once the runtime matures.

## Deferred Areas

The following items are intentionally deferred:

- adjacent-layout pivots
- zoom-to-deeper-view behavior
- path overlays
- legend system
- runtime graph editing
- layout editor behavior

## Status Vocabulary

| Status States |  |
| --- | --- |
| Proposed |  |
| Approved for Development | Requirement is accepted and ready to be implemented |
| In Development |  |
| Implemented |  |
| Verified |  |
| Refactoring |  |
| Deprecating |  |
| Deprecated | Not part of the current architecture and should not be implemented |

## RID Format

`req-<application>-<specification>-<feature>-<sub-feature>`

## Requirements Format

`RID: \`...\``
`Status: \`...\``
