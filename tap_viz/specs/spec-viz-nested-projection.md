# Viz Nested Projection Specification

## Philosophy

The core geometric rule for nested TAP Viz scenes is simple: a node's outer size is identity, not state. A node must not become visually larger merely because it gains children at a deeper elevation. The childless rendering and the child-bearing rendering are two views of the same outer box.

Once that rule holds, nesting stops needing compensating camera tricks. The parent's already-visible box becomes a local viewport for its child scene. Children are projected into that viewport by scale, laid out within that constrained area, and rendered without changing the parent's world position or outer dimensions. Zoom remains the control that chooses which scene depth is active, but the awkward work of hiding geometry changes behind pan, fit, and hero-node anchoring can go away.

TAP nested projection does not use Cytoscape's compound-node system. All nodes remain flat peers in the Cytoscape graph. Visual containment is achieved through positional placement: children are positioned within the model-space bounding box of their parent node, rendered on top via z-index, and moved in lockstep with the parent by the runtime. Edges that express the containment relationship are hidden. This bounded-layer model avoids compound auto-sizing, compound-specific style rules, and the awkward anchor-child machinery that was needed to force compound nodes to specific dimensions.

The runtime owns the geometry work. Layout authors declare nesting relationships, base sizes, and layout preferences. The runtime resolves nesting, computes viewports, derives scale factors, and executes constrained layouts recursively. This keeps layout modules focused on scene intent rather than coordinate arithmetic.

This specification defines the geometry contract and the runtime projection API. It complements the projection spec (orchestration and elevation) and the nesting spec (relationship resolution and edge hiding).

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Stable Geometry | A node keeps the same outer bounding box whether it is childless or acting as a parent. |
| 2. | Bounded Layers | Visual containment is positional, not structural. No Cytoscape compound nodes. |
| 3. | Runtime Owned | The projection runtime owns viewport derivation, scale computation, and constrained layout execution. |
| 4. | Scale Load-Bearing | Child geometry, labels, and icons scale to fit the viewport rather than forcing parent resize or overflow. |
| 5. | Additive Elevations | Deeper elevations add nesting layers without removing higher-level structure. |
| 6. | Simpler Runtime | Camera-preservation code that exists to hide geometry discontinuities is transitional and targeted for removal. |

## Requirement Status

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-viz-nested-projection-stable-box | [Stable Outer Bounding Box](#stable-outer-bounding-box) | Approved for Development | Childless and child-bearing renderings share one outer box |
| req-viz-nested-projection-bounded-layer | [Bounded-Layer Model](#bounded-layer-model) | Approved for Development | No Cytoscape compounds; positional containment with z-ordering |
| req-viz-nested-projection-screen-viewport | [Screen-Derived Parent Viewport](#screen-derived-parent-viewport) | Approved for Development | Parent viewport derived from model-space bbox minus padding |
| req-viz-nested-projection-scale-fit | [Scale-To-Fit Projection](#scale-to-fit-projection) | Approved for Development | Nested scenes scale uniformly into the viewport with no overflow |
| req-viz-nested-projection-layout-order | [Viewport-Constrained Layout Order](#viewport-constrained-layout-order) | Approved for Development | Child sizes established before layout runs inside the viewport |
| req-viz-nested-projection-runtime-api | [Runtime Projection API](#runtime-projection-api) | Approved for Development | `projectNested` runtime module owns the geometry pipeline |
| req-viz-nested-projection-container-visual | [Container Visual Switch](#container-visual-switch) | Approved for Development | Viewport parents switch to container rendering automatically |
| req-viz-nested-projection-additive-elevations | [Additive Elevation Nesting](#additive-elevation-nesting) | Approved for Development | Deeper elevations extend the nesting chain without collapsing higher levels |
| req-viz-nested-projection-scene-activation | [Scene-Wide Elevation Activation](#scene-wide-elevation-activation) | Approved for Development | Whole-scene elevation switching remains the v1 model |
| req-viz-nested-projection-runtime-simplification | [Runtime Simplification Direction](#runtime-simplification-direction) | Approved for Development | Hero-node anchoring and camera choreography are transitional |

## Requirements

### Stable Outer Bounding Box
----
RID: `req-viz-nested-projection-stable-box`
Status: `Approved for Development`

A node's childless rendering and child-bearing rendering must share the same outer bounding box.

#### Implementation

For a given active scene, a node already has a displayed size as a normal Cytoscape node (set by the layout's `baseSizes` declaration). When a deeper elevation causes that node to host children, the runtime preserves that outer box rather than substituting a larger "parent version" of the node.

Rules:

- the outer box is determined by the `baseSizes` declaration in the layout's `projectNested` call
- the node's world position remains stable across the elevation transition
- becoming a viewport parent must not trigger any size change
- if a node has no visible children at the active elevation, it still retains the same outer box it would use as a parent

This requirement applies to the outer node geometry only. The inner viewport (available space for children) is derived by subtracting padding.

#### Development

This is the key invariant that removes the need for camera compensation. If the parent box does not change identity when children appear, then the user is no longer being asked to visually swallow a hidden resize event during drilldown.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-nested-projection-stable-box-1 | Same Outer Box Across States | Approved for Development | A node uses the same outer bounding box when childless and when hosting children. | |
| req-viz-nested-projection-stable-box-2 | Parent Position Stable | Approved for Development | Entering a deeper elevation does not move the parent's world position merely because it gained children. | Layouts may still reposition the wider scene intentionally. |
| req-viz-nested-projection-stable-box-3 | No Auto-Expansion | Approved for Development | Nested content may not enlarge the parent's outer box. Guaranteed by the bounded-layer model (no compound auto-sizing). | |

#### Future

Later work may define authoring-time visualization tools that make this invariant easier to preview.


### Bounded-Layer Model
----
RID: `req-viz-nested-projection-bounded-layer`
Status: `Approved for Development`

TAP nested projection uses positional containment rather than Cytoscape's compound-node system.

#### Implementation

All nodes in a TAP Viz scene remain flat peers in the Cytoscape graph. No node is ever assigned as a Cytoscape compound parent via `node.move({parent: id})` or element data `parent` fields.

Visual containment is achieved through:

- **Positional placement**: children are positioned within the model-space bounding box of their parent node by the constrained layout runner.
- **Z-ordering**: children are rendered on top of their parent via z-index style rules. Deeper nesting depth = higher z-index.
- **Edge hiding**: edges that express the containment relationship are hidden via the `.tap-hidden-containment` class (same convention as before).
- **Data stamping**: children carry `_viewport_parent` in their data to identify their containing node. The runtime uses this for position coupling and containment queries.

Benefits of this model over Cytoscape compounds:

- no compound auto-sizing (parent never grows to contain children)
- no invisible anchor children needed to force minimum sizes
- no compound-specific style rules or `:parent` pseudo-selectors
- children may extend beyond parent perimeter in future layouts (ports, interfaces)
- parent node styling is trivial (it is always a regular node)
- position coupling is explicit rather than implicit

#### Position Coupling

In v1, projection scenes are non-interactive for drag. Layouts place all nodes and the user navigates via zoom/pan only. Position coupling (children follow parent on drag) is deferred.

#### Development

The compound-node system in Cytoscape is designed for a different use case: auto-sizing containers where the parent's size is derived from its children. TAP's use case is the opposite — the parent's size is authoritative and children must fit within it. Fighting Cytoscape's auto-sizing with anchor children and dimension overrides added complexity without solving the fundamental mismatch. The bounded-layer model sidesteps the issue entirely.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-nested-projection-bounded-layer-1 | No Compound Parents | Approved for Development | No node in a TAP nested projection scene is assigned as a Cytoscape compound parent. | |
| req-viz-nested-projection-bounded-layer-2 | Positional Containment | Approved for Development | Children are contained by being positioned within the parent's bbox by the constrained layout. | |
| req-viz-nested-projection-bounded-layer-3 | Z-Index Layering | Approved for Development | Children render on top of parents via z-index depth assignment. | |
| req-viz-nested-projection-bounded-layer-4 | Data Stamping | Approved for Development | Children carry `_viewport_parent` data identifying their containing node. | |
| req-viz-nested-projection-bounded-layer-5 | Drag Deferred | Approved for Development | Position coupling for user drag is deferred in v1. Scenes are zoom/pan only. | |

#### Future

Add drag-follows-parent behavior when interactive projection scenes are needed. Consider allowing children to extend beyond parent perimeter for specialized layouts (network interfaces, ports).


### Screen-Derived Parent Viewport
----
RID: `req-viz-nested-projection-screen-viewport`
Status: `Approved for Development`

The parent viewport is derived from the node's model-space bounding box.

#### Implementation

When the runtime projects children inside a parent node:

1. the runtime reads the parent's model-space bounding box (position + width/height as set by `baseSizes`)
2. the runtime subtracts configured padding from that box to derive an inner viewport rect
3. that inner viewport is the effective bounding box in which child content is scaled and laid out

"Model-space" means the coordinate system Cytoscape uses internally. The on-screen rendering is `model * zoom`. The viewport is stable in model coordinates — zooming makes everything uniformly larger/smaller on screen without changing the viewport rect.

V1 uses padding only. Header carve-outs, label bands, and other richer box-model concepts are deferred.

#### Development

This keeps concerns separated cleanly. The layout declares how big a node is via `baseSizes`. The runtime reuses that already-declared size to derive the viewport for children, without a second geometry contract.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-nested-projection-screen-viewport-1 | Model-Space Box Is Source | Approved for Development | Parent viewport derivation starts from the node's model-space bbox. | |
| req-viz-nested-projection-screen-viewport-2 | Padding Creates Inner Viewport | Approved for Development | V1 derives an inner viewport by subtracting padding from the outer box. | |
| req-viz-nested-projection-screen-viewport-3 | No Alternate Parent Box Required | Approved for Development | No separate larger per-parent size declaration is needed for parent mode. The same `baseSizes` entry is used. | |

#### Future

If TAP later needs richer parent chrome, add explicit box-model sub-areas without revoking the rule that the outer box comes from `baseSizes`.


### Scale-To-Fit Projection
----
RID: `req-viz-nested-projection-scale-fit`
Status: `Approved for Development`

Child scenes are projected into the parent viewport by uniform scale-to-fit.

#### Implementation

Nested child content must fit inside the parent viewport. Resizing the parent, allowing overflow, or introducing scrolling is not allowed in v1.

Rules:

- child nodes, labels, icons, and related nested scene geometry scale uniformly
- the scale factor is derived at runtime from the parent viewport dimensions and the natural extent of the child scene (determined by child count, base sizes, and layout algorithm)
- `baseSizes` defines the "full-scale" size for each entity type; the runtime computes a scale factor that makes the laid-out children fit within the viewport
- scale is multiplicative across nesting levels: a node nested 2 levels deep has its base size multiplied by both the outer and inner scale factors
- labels are allowed to become small in v1; later readability policy may refine this
- if a layout produces children that would overfill the viewport at any scale > 0, the runtime should log a warning (sign to the layout author that the scene needs a different approach)

#### Development

Uniform scale keeps the visual contract honest. The child scene should feel like the same scene viewed through a smaller local window, not a different hand-tuned set of arbitrary exceptions.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-nested-projection-scale-fit-1 | Uniform Scale Applied | Approved for Development | Nested node bodies, labels, icons, and other child scene geometry use one projection scale per nesting level. | |
| req-viz-nested-projection-scale-fit-2 | Fit Required | Approved for Development | Nested content fits within the parent viewport. Overflow and scrolling are not allowed. | |
| req-viz-nested-projection-scale-fit-3 | Multiplicative Across Levels | Approved for Development | Scale compounds across nesting depth. A node 2 levels deep applies both scale factors. | |
| req-viz-nested-projection-scale-fit-4 | Overfill Warning | Approved for Development | If children cannot reasonably fit, the runtime logs a warning rather than failing silently. | |

#### Future

Future work may define semantic label suppression, minimum-readable-size thresholds, or projection-aware icon policies once the first implementation proves out.


### Viewport-Constrained Layout Order
----
RID: `req-viz-nested-projection-layout-order`
Status: `Approved for Development`

Child sizes are established before the child layout runs, and the layout runs inside the parent viewport constraint.

#### Implementation

The runtime follows this order for each nesting level:

1. determine the parent viewport from the parent's model-space bbox and padding
2. determine the base sizes of child nodes from `baseSizes` declarations
3. compute the scale factor that makes the natural child scene extent fit within the viewport
4. apply scaled sizes to child nodes
5. run the declared inner layout with Cytoscape's `boundingBox` option set to the parent viewport rect
6. render the resulting child scene positioned within the parent's outer box

This means layouts operate against the viewport they actually have, using the scaled sizes that will really be displayed. The runtime uses Cytoscape's built-in `boundingBox`-constrained layout behavior.

For the recursive case (multiple nesting levels), the runtime processes from outermost parents inward: position parents first, then project their children, then recursively project children-of-children.

#### Development

Running layout after scaled sizes are known avoids "flying giants" and other geometry discontinuities where the layout solves for one set of dimensions but the user sees another.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-nested-projection-layout-order-1 | Sizes Before Layout | Approved for Development | Child sizes are resolved and scaled before the constrained child layout runs. | |
| req-viz-nested-projection-layout-order-2 | Layout Uses Parent Viewport | Approved for Development | Child layout runs inside the effective parent viewport bounding box. | |
| req-viz-nested-projection-layout-order-3 | Outer-In Recursion | Approved for Development | Multi-level nesting is processed from outermost parents inward. | |

#### Future

Add helper APIs so layout authors do not have to hand-roll the viewport and scale plumbing in every layout module.


### Runtime Projection API
----
RID: `req-viz-nested-projection-runtime-api`
Status: `Approved for Development`

The `projectNested` runtime module owns the geometry pipeline for nested scenes.

#### Implementation

`projectNested` is the primary runtime API that layout authors call to declare nested scene intent. It lives at `tap_viz/static/tap_viz/js/runtime/nested-projection.js`.

Layout authors call it with a config object:

```javascript
import { projectNested } from "/static/tap_viz/js/runtime/nested-projection.js";

export async function execute(context) {
  const { cy, trigger_reason } = context;

  await projectNested(cy, {
    relationships: [
      {
        name: "realm-contains-location",
        gryphon: "(parent:realm)-[:CONTAINS]->(child:location)"
      },
      {
        name: "location-contains-character",
        gryphon: "(parent:location)<-[:LOCATED_IN]-(child:character)"
      }
    ],
    baseSizes: {
      realm:     { width: 300, height: 200 },
      location:  { width: 80, height: 60 },
      character: { width: 40, height: 40 }
    },
    padding: 10,
    innerLayout: "grid"
  });

  if (trigger_reason === "initial_load") {
    cy.fit(cy.nodes(":visible"), 40);
  }
}
```

The runtime performs:

1. **Resolve nesting**: Parse Gryphon patterns, match edges in cy, determine parent-child assignments. Same resolver logic as `resolveNesting` but stamps `_viewport_parent` data instead of setting Cytoscape `.parent()`.

2. **Hide containment edges**: Apply `.tap-hidden-containment` class to consumed edges.

3. **Apply base sizes**: Set `width` and `height` on all nodes according to `baseSizes` keyed by `entity_type`.

4. **Recursive descent projection**: Starting from outermost parents (nodes that have children but no `_viewport_parent` themselves), work inward:
   - Read parent model-space bbox
   - Subtract padding → inner viewport rect
   - Collect children (nodes with `_viewport_parent` == this parent's id)
   - Compute scale factor: `min(viewport.w / naturalExtent.w, viewport.h / naturalExtent.h)` where natural extent is derived from child base sizes and the layout algorithm's expected arrangement
   - Apply scaled dimensions to children: `baseSize * scale`
   - Run the inner layout with `boundingBox` set to the viewport rect
   - Recurse into any children that themselves have children

5. **Container visual switch**: Add `.tap-viewport-parent` class to any node that has children positioned inside it. Remove the class from nodes with no children at this elevation.

6. **Z-ordering**: Assign z-index by nesting depth. Depth 0 nodes get the lowest z-index, depth 1 higher, etc.

7. **Warnings**: Emit warnings for overfill situations, multiple-parent conflicts, and cycles (same categories as the nesting resolver).

#### Config Shape

| Field | Type | Required | Description |
| --- | --- | :---: | --- |
| `relationships` | array | Yes | Ordered nesting relationship declarations with `name` and `gryphon` fields. |
| `baseSizes` | object | Yes | Map of `entity_type` → `{width, height}`. Defines full-scale base size for each type. |
| `padding` | number | Yes | Pixels subtracted from parent bbox to derive inner viewport. Applied uniformly on all sides. |
| `innerLayout` | string or object | Yes | Cytoscape layout name (e.g. `"grid"`) or layout options object passed to `cy.layout()`. Used for child arrangement within each viewport. |
| `innerLayouts` | object | No | Optional per-entity-type layout overrides. Map of parent `entity_type` → layout name/options. Falls back to `innerLayout`. |
| `fit` | boolean | No | If true, fit the viewport to the full scene after projection. Default: false. |

#### Development

Centralizing the geometry pipeline in one runtime module keeps layout code declarative and minimal. Layout authors express what they want (relationships + sizes + layout algorithm), not how to compute viewports and scale factors. This makes writing new layouts significantly easier and eliminates the class of bugs where layouts implement subtly different coordinate arithmetic.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-nested-projection-runtime-api-1 | Single Entry Point | Approved for Development | `projectNested(cy, config)` is the primary API layouts use for nested scene projection. | |
| req-viz-nested-projection-runtime-api-2 | Resolver Integration | Approved for Development | Nesting resolution uses the same Gryphon-subset parsing as the existing resolver but stamps data instead of compounds. | |
| req-viz-nested-projection-runtime-api-3 | Recursive Descent | Approved for Development | The runtime processes multi-level nesting from outermost parents inward. | |
| req-viz-nested-projection-runtime-api-4 | Scale Computation | Approved for Development | Scale factors are computed automatically from viewport size and child scene extent. | |
| req-viz-nested-projection-runtime-api-5 | Constrained Layout | Approved for Development | Inner layouts run with `boundingBox` set to the parent viewport rect. | |
| req-viz-nested-projection-runtime-api-6 | Warnings Emitted | Approved for Development | Overfill, multiple-parent, and cycle warnings are logged. | |

#### Future

Add per-parent layout override support if different parent types need fundamentally different child arrangement algorithms. Consider exposing the scale factor to layouts for advanced use cases.


### Container Visual Switch
----
RID: `req-viz-nested-projection-container-visual`
Status: `Approved for Development`

Nodes that host children automatically switch to a container visual style.

#### Implementation

When `projectNested` determines that a node has children positioned inside it, the runtime adds the `.tap-viewport-parent` class to that node. When children are cleared (next elevation re-asserts without that nesting level), the class is removed.

Default container visual behavior for `.tap-viewport-parent` nodes:

- background rendered as a subtle container (light fill, border)
- icon suppressed (no background-image)
- label repositioned to a header/top position (`text-valign: top`, outside or at top edge)
- node body serves as the visual frame for children inside it

When the class is removed, the node reverts to its normal leaf styling (icon, centered label, standard background).

The style rules for `.tap-viewport-parent` are defined in the graph panel's base stylesheet so they apply consistently across all projection-driven panels.

#### Development

Switching to container mode automatically means layout authors don't have to manually manage style transitions. The visual mode follows from the structural fact of having children inside you.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-nested-projection-container-visual-1 | Class Added Automatically | Approved for Development | `.tap-viewport-parent` is added by the runtime when a node has children projected inside it. | |
| req-viz-nested-projection-container-visual-2 | Class Removed On Clear | Approved for Development | `.tap-viewport-parent` is removed when the node no longer hosts children at the active elevation. | |
| req-viz-nested-projection-container-visual-3 | Default Container Style | Approved for Development | Container nodes show a subtle background, suppressed icon, and top-positioned label by default. | |
| req-viz-nested-projection-container-visual-4 | Revert On Remove | Approved for Development | Removing the class reverts the node to its normal leaf visual. | |

#### Future

Allow layout authors to customize container visual per entity type if different parent types need different visual treatments. Consider header bands, colored borders, or other richer chrome.


### Additive Elevation Nesting
----
RID: `req-viz-nested-projection-additive-elevations`
Status: `Approved for Development`

Deeper elevations extend the nesting chain without removing higher-level structure.

#### Implementation

Each elevation declares its full nesting chain via the `relationships` array in its `projectNested` call. Deeper elevations include all relationships from shallower elevations plus additional levels.

For the LOTR saga example:

- **Saga-level** declares: `realm → location`, `location → character` (3 levels visible)
- **Character-view** declares: `realm → location`, `location → character`, `character → artifact` (4 levels visible)

The "assert scene state on entry" invariant means each elevation's layout is a complete declaration of nesting truth. There is no incremental-add semantic — the full chain is stated each time. The runtime clears prior nesting state and re-resolves from scratch on each elevation entry.

This means:
- zooming deeper adds visual information (more levels of children become visible)
- zooming shallower hides deeper content (elevation-hidden class) without removing it
- the user never loses context about where they are in the hierarchy

#### Development

Additive elevation nesting is the "magnify and enhance" model applied to nesting structure. The user's journey is always additive — you see more as you go deeper, never less of what was already visible.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-nested-projection-additive-elevations-1 | Full Chain Declared | Approved for Development | Each elevation declares the complete nesting chain for its scene, not just the delta from the previous elevation. | |
| req-viz-nested-projection-additive-elevations-2 | Deeper Adds Levels | Approved for Development | Deeper elevations add nesting levels visible to the user. | |
| req-viz-nested-projection-additive-elevations-3 | Shallower Hides | Approved for Development | Shallower elevations hide deeper content via elevation-hidden class rather than removing. | |
| req-viz-nested-projection-additive-elevations-4 | Context Preserved | Approved for Development | Higher-level structure (realms, locations) remains visible at deeper elevations. | |

#### Future

Consider whether very deep nesting chains (5+ levels) need progressive disclosure to avoid multiplicative scale making deep nodes illegibly small.


### Scene-Wide Elevation Activation
----
RID: `req-viz-nested-projection-scene-activation`
Status: `Approved for Development`

Elevation switching remains scene-wide in v1 even though nested projection is local to each parent box.

#### Implementation

The active elevation is still chosen by projection runtime zoom thresholds. When the scene crosses an elevation boundary:

- the new elevation activates for the whole scene
- every eligible parent at that elevation renders its nested content
- double-tap remains a shortcut for "zoom to the next level centered on this location"
- per-node independent expansion is deferred

Nested projection changes how content is rendered inside parent boxes. It does not yet change the scene-wide activation model.

#### Development

This keeps the first implementation tractable. The geometry contract gets much cleaner without forcing TAP to solve selective per-node expansion at the same time.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-nested-projection-scene-activation-1 | Whole Scene Activates | Approved for Development | Crossing an elevation threshold activates the deeper scene for all eligible parents. | |
| req-viz-nested-projection-scene-activation-2 | Double-Tap Remains Shortcut | Approved for Development | Double-tap remains a navigation shortcut to the next level centered on the tapped location. | |
| req-viz-nested-projection-scene-activation-3 | Per-Node Expansion Deferred | Approved for Development | Independent per-node zoom/expansion behavior is explicitly deferred. | |

#### Future

Per-node selective expansion is a plausible later refinement built on top of the stable geometry contract.


### Runtime Simplification Direction
----
RID: `req-viz-nested-projection-runtime-simplification`
Status: `Approved for Development`

Camera and focus logic that exists primarily to hide geometry discontinuities is transitional under the nested projection model.

#### Implementation

Under the current runtime, scroll-driven elevation changes use viewport-preservation logic such as cursor tracking, hero-node selection, ancestor fallback, and post-layout pan correction. Those mechanisms exist because deeper elevations currently change parent geometry in ways that would otherwise produce visible jumps.

Under this specification:

- geometry continuity is the primary fix (stable bounding box)
- camera compensation is not the primary architecture
- hero-node anchoring, focus gyrations, and similar choreography should be treated as transitional and removed once the nested projection model is implemented
- double-tap centering remains valid as a direct navigation affordance rather than a geometry patch

Code targeted for removal:

- `cytoscape-tap-dimensions.js` — anchor children, `layoutRecursive`, manual grid (replaced by `nested-projection.js`)
- Hero-node selection and cursor tracking in `projection.js`
- Ancestor-chain fallback in `projection.js`
- Post-layout pan correction in `projection.js`
- DOM parent-label overlay in `panel-graph.js` (replaced by `.tap-viewport-parent` native Cytoscape label positioning)

Code that survives:

- Zoom watcher and elevation activation in `projection.js`
- Hysteresis after commanded transitions
- Double-tap detection and pan-zoom animation
- Transition lock during animations
- `search.js` (runtime search helper)
- `layout-loader.js` (module loading)
- `nesting.js` resolver logic (relationship parsing, edge matching, cycle detection — adapted to stamp data instead of setting compound parents)

#### Development

This requirement is intentionally directional. The new geometry contract should let TAP delete more code than it adds.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-nested-projection-runtime-simplification-1 | Geometry First | Approved for Development | Nested projection treats stable geometry and local scaling as the primary solution to drilldown continuity. | |
| req-viz-nested-projection-runtime-simplification-2 | Camera Tricks Removed | Approved for Development | Hero-node anchoring and viewport choreography are removed, not just deprecated. | |
| req-viz-nested-projection-runtime-simplification-3 | Double-Tap Survives As Navigation | Approved for Development | Double-tap remains as a centering/navigation gesture. | |
| req-viz-nested-projection-runtime-simplification-4 | Tap-Dimensions Retired | Approved for Development | `cytoscape-tap-dimensions.js` is deleted entirely, replaced by `nested-projection.js`. | |

#### Future

Once the new geometry model is implemented, update the projection spec to remove the Deprecating viewport-preservation requirement entirely.
