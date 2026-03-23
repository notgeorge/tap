# Viz Layouts Specification

## Philosophy

Viz layouts are the canonical TAP artifacts that define how graph data is gathered and presented in a viz panel. A layout is not merely a renderer algorithm name or a saved list of coordinates. It is an ordered, declarative recipe that retrieves graph data, shapes it into a working graph view, applies containment and placement logic, and emits a renderer-ready scene.

The purpose of the layout system is to retain graph-native power while making the visible result legible to humans. That requires a contract that is richer than raw Cytoscape JSON but still more structured and safer than arbitrary executable code stored in the database.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Declarative | Layouts must be TAP-owned declarative definitions rather than raw renderer-native config as the primary artifact. |
| 2. | Search-Driven | Layouts must retrieve graph data through ordered search execution based on TAP Search entities. |
| 3. | Ordered | Layout behavior must execute through a deterministic ordered pipeline. |
| 4. | Hierarchical | Layouts must reserve room for containment behavior without making it part of the smallest initial default contract. |
| 5. | Extensible | Layouts must support controlled extension points such as plugin formatters without falling back to code blobs in storage. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-viz-layout-entity | [Layout Entity](#layout-entity) | Proposed | Defines the layout as a first-class TAP object |
| req-viz-layout-definition | [Layout Definition](#layout-definition) | Proposed | Defines the canonical TAP-owned layout payload |
| req-viz-layout-inputs | [Layout Inputs](#layout-inputs) | Proposed | Layouts may declare and consume runtime inputs |
| req-viz-layout-search-steps | [Search Steps](#search-steps) | Proposed | Ordered search steps retrieve graph data |
| req-viz-layout-pipeline-order | [Pipeline Order](#pipeline-order) | Proposed | Layout execution order is deterministic |
| req-viz-layout-graph-merge | [Graph Merge](#graph-merge) | Proposed | Search results merge into a working graph state |
| req-viz-layout-containment | [Containment](#containment) | Proposed | Parent-child graph relationships are part of the layout contract |
| req-viz-layout-placement | [Placement](#placement) | Proposed | Placement actions position graph elements in the scene |
| req-viz-layout-style-rules | [Style Rules](#style-rules) | Proposed | Layouts define normalized presentation rules using shape hints and the existing icon system |
| req-viz-layout-plugin-formatters | [Plugin Formatters](#plugin-formatters) | Proposed | Extension is registry-based, not code-in-DB |
| req-viz-layout-renderer-ready-scene | [Renderer-Ready Scene](#renderer-ready-scene) | Proposed | Execution output is a renderer-ready graph scene |
| req-viz-layout-legacy-cytoscape-deprecation | [Legacy Cytoscape Deprecation](#legacy-cytoscape-deprecation) | Proposed | Raw Cytoscape layout storage is transitional |

### Layout Entity
----
RID: `req-viz-layout-entity`
Status: `Proposed`

A viz layout is a first-class TAP entity with metadata and a declarative definition payload.

#### Status Details
This requirement replaces the narrow idea of a “saved Cytoscape layout” with a richer TAP-owned layout artifact.

#### Implementation
The canonical layout object stores:

- `name`
- `description`
- `definition`
- optional lifecycle metadata such as version or status in future work

The layout object is reusable and independent of any one panel instance.

#### Development
Keeping layouts first-class and reusable allows the same view logic to be applied in multiple pages, panels, or future clients.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-layout-entity-1 | First-Class Layout Artifact | Proposed | Layouts are specified as their own TAP-managed artifacts. | |
| req-viz-layout-entity-2 | Metadata Stored With Definition | Proposed | Layouts include human-readable metadata plus a definition payload. | |
| req-viz-layout-entity-3 | Layout Is Reusable | Proposed | A layout may be referenced by multiple panel instances. | |

#### Future
Define explicit versioning, drafts, and publication workflow in a later spec.


### Layout Definition
----
RID: `req-viz-layout-definition`
Status: `Proposed`

The canonical persisted layout payload is a TAP-owned `definition` object rather than raw renderer-native JSON.

#### Status Details
This requirement is the core architectural shift for the viz subsystem.

#### Implementation
The layout `definition` object is expected to contain structured sections such as:

- `inputs`
- `steps`
- `presentation`
- `interactions`

These are TAP-level concepts, not renderer-native fields.

#### Development
The layout definition should be specific enough to support deterministic execution and future editor tooling, but narrow enough to avoid becoming a code-storage escape hatch.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-layout-definition-1 | TAP-Owned Payload | Proposed | The canonical persisted layout payload is TAP-owned rather than raw Cytoscape config. | |
| req-viz-layout-definition-2 | Structured Sections | Proposed | The layout definition exposes structured sections for inputs, steps, presentation, and interactions. | |
| req-viz-layout-definition-3 | Renderer Independence Preserved | Proposed | Layout definition structure is not defined in terms of renderer-native configuration fields. | |

#### Future
Define a machine-validated schema once the runtime and editor requirements settle further.


### Layout Inputs
----
RID: `req-viz-layout-inputs`
Status: `Proposed`

Layouts may declare inputs and bind panel-resolved runtime values into search and layout execution.

#### Status Details
This requirement makes layouts first-class participants in the page/panel input model without forcing page-level naming into layout definitions.

#### Implementation
- A layout may declare named inputs.
- Panel-resolved input values may be mapped into those layout inputs.
- Search steps may consume layout inputs as execution inputs.
- Layout execution reruns deterministically for a given input state.

#### Development
Keep page-variable mapping in the page/panel layer. The layout should only know its own local input names and defaults.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-layout-inputs-1 | Layout Input Names Declared | Proposed | Layouts may declare their own local runtime input names. | |
| req-viz-layout-inputs-2 | Panel Inputs Bind Into Layout | Proposed | Viz panel runtime may bind resolved panel inputs into layout inputs. | |
| req-viz-layout-inputs-3 | Search Steps Consume Bound Inputs | Proposed | Search execution inputs may be derived from layout input values. | |
| req-viz-layout-inputs-4 | Rerun Deterministic | Proposed | The same layout definition plus the same input state produces deterministic execution ordering. | |

#### Future
If input schemas become important, add JSON Schema or typed validation in a later iteration.


### Search Steps
----
RID: `req-viz-layout-search-steps`
Status: `Proposed`

Layouts retrieve graph data through ordered search steps that reference TAP Search entities.

#### Status Details
This requirement keeps data retrieval aligned with the existing TAP search system.

#### Implementation
- A `search` step references a saved Search entity.
- A search step may define:
  - input bindings
  - result inclusion rules
  - step-local naming or grouping metadata
- Search steps return canonical graph envelopes which feed the layout pipeline.

#### Development
Search steps should remain references to TAP-managed searches, not inline query code or inline ORM definitions inside the layout.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-layout-search-steps-1 | Search Entity Reference | Proposed | Search steps reference TAP Search entities. | |
| req-viz-layout-search-steps-2 | Canonical Result Envelope Used | Proposed | Search steps contribute canonical graph envelopes to layout execution. | |
| req-viz-layout-search-steps-3 | Inline Query Logic Excluded | Proposed | Layout definitions do not store their own arbitrary search implementation logic. | |

#### Future
If search composition patterns become common, specify them as more explicit step types rather than overloading search steps.


### Pipeline Order
----
RID: `req-viz-layout-pipeline-order`
Status: `Proposed`

Layout execution follows a deterministic ordered pipeline.

#### Status Details
This requirement exists because layouts will eventually combine multiple searches and multiple actions. Without a defined execution order, layouts become ambiguous and difficult to reason about.

#### Implementation
The canonical execution order is:

1. Resolve layout inputs
2. Execute ordered search steps
3. Merge graph envelopes into working graph state
4. Apply filtering and derivation steps
5. Apply containment
6. Apply ordered placement actions
7. Apply style rules such as shape and icon behavior
8. Emit renderer-ready scene output

#### Development
Keeping the pipeline explicit makes future editor tooling and debugging far easier than relying on implied order or renderer behavior.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-layout-pipeline-order-1 | Canonical Order Defined | Proposed | The spec defines a canonical ordered layout execution pipeline. | |
| req-viz-layout-pipeline-order-2 | Placement Happens After Containment | Proposed | Placement actions execute after containment derivation is known. | |
| req-viz-layout-pipeline-order-3 | Style Happens After Placement Inputs Are Ready | Proposed | Style rules such as shape and icon behavior execute after the working scene structure is established. | |

#### Future
If pre-merge or post-render hooks are needed, define them explicitly rather than allowing arbitrary execution phases.


### Graph Merge
----
RID: `req-viz-layout-graph-merge`
Status: `Proposed`

Results from multiple search steps merge into a single working graph state for the layout pipeline.

#### Status Details
This requirement is necessary because useful layouts will often be composed from more than one search.

#### Implementation
- The working graph state consists of nodes and edges plus execution metadata.
- Multiple search results merge into that working graph state.
- Merge semantics must be deterministic and avoid duplicate graph members in the working set.
- Warnings may be accumulated during merge.

#### Development
The working graph state is the right intermediate representation for layout execution. It is more stable than renderer-specific node/edge payloads and richer than raw search output.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-layout-graph-merge-1 | Single Working Graph State | Proposed | Multiple search results merge into a single working graph state for the layout. | |
| req-viz-layout-graph-merge-2 | Duplicate Handling Defined | Proposed | Merge behavior handles duplicate graph members deterministically. | |
| req-viz-layout-graph-merge-3 | Warning Accumulation Allowed | Proposed | Non-fatal merge issues may be accumulated as warnings. | |

#### Future
Define richer graph derivation and grouping semantics once advanced layouts appear.


### Containment
----
RID: `req-viz-layout-containment`
Status: `Proposed`

Containment is a reserved layout concern used to represent graph objects that are visually inside other graph objects when a layout explicitly opts into it.

#### Status Details
This requirement keeps room for parent-child and “inside” relationships without forcing the smallest initial layouts to use compound structures.

#### Implementation
- Layout execution may support parent-child relationships in the working graph state when a layout explicitly uses containment.
- No model-level containment hint is part of the smallest initial display-hints contract.
- Layout definitions own containment behavior when containment is used in v1.
- Containment examples include:
  - ports inside network interfaces
  - applications inside servers
  - servers inside network segments

#### Development
Containment is intentionally not part of the simplest layout path. When used, it must be resolved before placement and styling can fully reason about parent objects and child bounds.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-layout-containment-1 | Parent-Child Supported | Proposed | Layout execution supports parent-child graph relationships as part of the scene model. | |
| req-viz-layout-containment-2 | Layout-Owned In V1 | Proposed | When containment is used in v1, the layout definition owns that behavior directly. | |
| req-viz-layout-containment-3 | Simplest Layout May Skip Containment | Proposed | A valid initial layout may omit containment entirely. | |

#### Future
Define compound-edge presentation and more advanced nesting rules separately once needed.


### Placement
----
RID: `req-viz-layout-placement`
Status: `Proposed`

Placement actions position graph members in the layout scene after the working graph structure and containment are known.

#### Status Details
This requirement turns “layout” into an explicit ordered action system rather than a single renderer algorithm name.

#### Implementation
Supported v1 placement modes include:

- `cytoscape:grid`
- `cytoscape:cose`
- `cytoscape:preset`
- `model:micro-layout`
- `plugin:<scoped-key>`

Placement actions may apply to:
- the whole working graph
- a subset of nodes
- children within a parent object

#### Development
The smallest viable layout path should not require micro-layout. More advanced placement behaviors can be layered in later without changing the basic layout contract.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-layout-placement-1 | Ordered Placement Actions | Proposed | Layout definitions may contain ordered placement actions. | |
| req-viz-layout-placement-2 | Canonical Built-In Modes | Proposed | The spec defines a canonical initial set of built-in placement modes. | |
| req-viz-layout-placement-3 | Micro-Layout Reserved | Proposed | The placement system reserves room for future micro-layout behavior without making it part of the smallest required default path. | |
| req-viz-layout-placement-4 | Subgraph Placement Allowed | Proposed | Placement actions may target subsets of the working graph rather than only the whole scene. | |

#### Future
Define richer geometric constraints or alignment semantics only when real layout cases demand them.


### Style Rules
----
RID: `req-viz-layout-style-rules`
Status: `Proposed`

Layouts define normalized presentation rules, with the smallest initial model-default contract limited to node shape under namespaced viz display metadata. Icon rendering reuses the existing grid icon system.

#### Status Details
This requirement captures human-facing visual semantics without binding them to renderer-native style syntax, while keeping the initial default surface intentionally small and avoiding duplication of the existing grid icon contract.

#### Implementation
The canonical rule layer includes:

- shapes:
  - `square`
  - `rounded-square`
  - `rectangle`
- icon behavior:
  - optional icon display when the canonical grid icon contract resolves an icon for the node type
  - text-label fallback when no icon is available

Sizing, label modes, and parent-specific presentation rules are deferred.

The canonical source for a model-level default shape is the model display metadata namespace:

```json
{
  "tap_viz": {
    "shape": "rounded-square"
  }
}
```

#### Development
This keeps the initial display-hints and layout-style contract narrow enough that early defaults are unlikely to require refactoring.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-layout-style-rules-1 | Normalized Shape Set | Proposed | Layouts use a normalized shape vocabulary rather than raw renderer style values as the canonical contract. | |
| req-viz-layout-style-rules-2 | Icon Contract Reused | Proposed | Layout icon rendering reuses the canonical grid icon contract with safe fallback behavior when no icon resolves. | |
| req-viz-layout-style-rules-3 | Shape Hint Namespaced | Proposed | Model-level default shapes are sourced from a namespaced `tap_viz.shape` display hint. | |
| req-viz-layout-style-rules-4 | Advanced Presentation Deferred | Proposed | Size tiers, label modes, and parent-specific presentation rules are explicitly deferred. | |

#### Future
Add richer typography, stroke, and semantic coloring rules only after stable use cases emerge.


### Plugin Formatters
----
RID: `req-viz-layout-plugin-formatters`
Status: `Proposed`

Layouts may use plugin-defined formatters, but extension is registry-based rather than code stored directly in layout definitions.

#### Status Details
This requirement allows custom behavior without opening the door to arbitrary JavaScript stored in the database.

#### Implementation
- A plugin formatter is referenced by a scoped registry key.
- The formatter receives a defined input contract from layout execution.
- The formatter returns deterministic placement and/or presentation output.
- Inline arbitrary JavaScript stored in the layout object is not part of the v1 contract.

#### Development
Registry-based extension is consistent with the rest of TAP and is far safer than code-in-DB for a first serious layout system.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-layout-plugin-formatters-1 | Registry-Based Extension | Proposed | Plugin layout extensions are referenced through registry keys rather than code blobs. | |
| req-viz-layout-plugin-formatters-2 | Deterministic Formatter Contract | Proposed | Formatter output is expected to be deterministic for a given input state. | |
| req-viz-layout-plugin-formatters-3 | Inline JS Excluded | Proposed | Arbitrary inline JavaScript stored on layout entities is not part of the v1 spec. | |

#### Future
Define the exact plugin formatter interface in a dedicated sub-spec once the core layout runtime is settled.


### Renderer-Ready Scene
----
RID: `req-viz-layout-renderer-ready-scene`
Status: `Proposed`

Layout execution emits a renderer-ready scene that can be consumed by a renderer adapter such as Cytoscape.

#### Status Details
This requirement defines the handoff between TAP-owned layout logic and renderer-specific rendering.

#### Implementation
- The output of layout execution is a renderer-ready scene model.
- That scene contains enough information for the renderer adapter to construct visible nodes, edges, containment, placement, and presentation.
- Renderer adapters are responsible for converting the scene into renderer-native runtime configuration.

#### Development
This keeps the renderer boundary explicit and makes future renderer changes possible without redefining the layout language.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-layout-renderer-ready-scene-1 | Explicit Execution Output | Proposed | Layout execution emits a renderer-ready scene artifact. | |
| req-viz-layout-renderer-ready-scene-2 | Adapter Consumes Scene | Proposed | Renderer adapters consume the scene artifact rather than canonical layout storage directly. | |

#### Future
Define the exact scene schema when implementation work begins.


### Legacy Cytoscape Deprecation
----
RID: `req-viz-layout-legacy-cytoscape-deprecation`
Status: `Proposed`

Raw Cytoscape layout storage is transitional and should not remain the canonical persisted layout contract.

#### Status Details
Current `cytoscape_config` storage is useful as current-state functionality, but it is too renderer-specific and too low-level to be the long-term TAP layout model.

#### Implementation
- Existing raw Cytoscape config may be preserved temporarily for compatibility.
- Import/export compatibility with Cytoscape-native data may be supported.
- Future layout implementation should target the TAP-owned `definition` model first.

#### Development
This requirement provides a clean architectural direction without requiring immediate deletion of current working behavior.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-layout-legacy-cytoscape-deprecation-1 | Raw Cytoscape Config Not Canonical | Proposed | The spec treats raw Cytoscape config as transitional rather than canonical. | |
| req-viz-layout-legacy-cytoscape-deprecation-2 | Compatibility Allowed | Proposed | Import/export or migration compatibility may exist for Cytoscape-native layout data. | |
| req-viz-layout-legacy-cytoscape-deprecation-3 | New Work Targets Definition Model | Proposed | Future layout implementation targets the TAP-owned declarative definition model. | |

#### Future
Specify concrete migration and compatibility mechanics once the new layout system is implemented.

## Deferred Areas

The following items are explicitly deferred from this specification:

- layout editor
- adjacent-layout pivots
- path overlays
- legend behavior
- runtime drilldown navigation
- arbitrary inline code execution

## Initial Validation Dataset

The initial validation dataset for viz icon rendering should be the existing LOTR plugin dataset because it already exercises the canonical grid icon system across several entity types, including `character`, `location`, `artifact`, and `race`.

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
