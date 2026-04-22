# Viz Badges Specification

## Philosophy

Viz badges are small attached visual markers rendered on a node to communicate information without consuming the node body. They are a TAP Viz presentation pattern, not a new icon ownership system. Canonical icon ownership remains defined by the grid icon contract. The badges spec defines how TAP Viz may place and group those visual cues on Cytoscape-rendered nodes.

The first useful badge pattern is the type icon badge: a small circular badge anchored to the upper-left corner of a node that reminds the viewer what kind of node they are looking at. This pattern should work the same way for parent nodes and leaf nodes. That consistency keeps the interior of a parent node available for child layout while keeping the interior of a leaf node available for the node name.

Badge sets are the related grouping mechanism, but they remain future work. TAP Viz should name the concept now so later status-style groupings such as info, warning, and alert have a natural home, while keeping the first implementation tightly focused on the type icon badge.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Consistent | The same badge concepts should work across parent and leaf nodes. |
| 2. | Non-Intrusive | Badges should preserve the node body for names, children, and other content. |
| 3. | Modular | The badge vocabulary should leave room for future grouped badge constructs without requiring them in the first implementation. |
| 4. | TAP-Owned | Badge behavior should be described by TAP Viz concepts rather than ad hoc Cytoscape-only styling tricks. |
| 5. | Evolvable | The type icon badge can land now while status badge sets remain explicitly tracked for later. |

## Requirement Status

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-viz-badges-terminology | [Badge Terminology](#badge-terminology) | Implemented | Defines the vocabulary for badge, type icon badge, and badge set |
| req-viz-badges-type-icon | [Type Icon Badge](#type-icon-badge) | Implemented | Upper-left circular badge that indicates node type |
| req-viz-badges-body-preservation | [Node Body Preservation](#node-body-preservation) | Implemented | Badge placement must preserve the node body for primary content |
| req-viz-badges-badge-set | [Badge Set](#badge-set) | Backlog | Grouped badges with a shared purpose and shared location |
| req-viz-badges-status-future | [Status Badge Sets](#status-badge-sets) | Backlog | Future info, warning, and alert groupings |

## Requirements

### Badge Terminology
----
RID: `req-viz-badges-terminology`
Status: `Implemented`

TAP Viz uses a small vocabulary for node-attached markers.

#### Implementation

- A `badge` is a small attached visual marker rendered on or at the edge of a node.
- A `type icon badge` is a badge whose purpose is to show the node's type icon.
- A `badge set` is a grouped collection of related badges rendered together in a shared location on a node.
- A `status badge set` is a future badge set intended for state-style signals such as information, warning, and alert.

#### Development

Use `badge` as the umbrella term and more specific names for concrete badge purposes. Avoid overloaded terms such as `breadcrumb`, which imply path or hierarchy semantics rather than attached node markers.

#### Future

Add more badge subclasses only when they represent clearly distinct semantics and placement rules.


### Type Icon Badge
----
RID: `req-viz-badges-type-icon`
Status: `Implemented`

Nodes may render a type icon badge: a small circular badge anchored to the upper-left corner that indicates node type for both parent and leaf nodes.

#### Status Details

This is the first canonical badge pattern for TAP Viz. It replaces the need to choose between putting the icon inside the node body or only rendering it beside a custom HTML label.

#### Implementation

- The type icon badge uses the node's canonical type icon from the grid icon contract.
- The type icon badge is rendered as a small circular badge.
- The canonical anchor position is the upper-left corner of the node representation.
- The same type icon badge concept applies to:
  - leaf nodes
  - parent nodes
  - child nodes nested within parent nodes
- Missing type icons must fail safely by omitting the badge rather than making the node unusable.
- Badge rendering is controlled by a projection-wide `node_style` field. When `node_style` is `"icon-badge"`, all nodes in the projection receive badge treatment.
- Badges are implemented as separate Cytoscape nodes (not HTML overlays or background-image layers) so they protrude from the host node body and scale proportionally with zoom.
- Badge nodes are non-interactive (`"events": "no"`) and locked in position.
- All badges at a given elevation share a single uniform diameter. The runtime
  derives that diameter using the "smallest host wins" rule: scan every
  badge-eligible host, take the smallest `Math.min(w, h)`, multiply by the
  badge ratio (default `0.35`), and clamp to a floor of 24 model units. Every
  badge in the scene is then sized to that single value. This prevents large
  containers from producing badges that visually dominate the scene, and keeps
  badges readable even when recursive-scaling collapses leaf hosts in model
  coordinates.
- Badge bubbles render with a fully transparent background and no border by
  default, so the host's type icon reads as a free-floating glyph rather than
  inside a visible frame. A future setting may restore a visible bubble
  (see the Future section).
- The host node's icon is stashed and cleared when badges are applied, and restored on cleanup.
- Badge creation runs after layout completion so host positions and dimensions are stable.
- The runtime module is `tap_viz/static/tap_viz/js/runtime/badge-nodes.js`.

#### Development

The value of the pattern is consistency. A viewer should learn that the upper-left badge is where node identity-by-type lives, regardless of whether the node is acting as a container.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-badges-type-icon-1 | Shared Pattern Across Node Kinds | Implemented | Parent and leaf nodes use the same type icon badge concept. | `applyBadgeNodes` iterates all nodes with `icon_url` regardless of parent/leaf status |
| req-viz-badges-type-icon-2 | Upper-Left Anchor | Implemented | The type icon badge anchor is the node's upper-left corner. | Badge positioned at `(pos.x - w/2, pos.y - h/2)` |
| req-viz-badges-type-icon-3 | Circular Badge Form | Implemented | The type icon badge renders as a small circle. | `node[_is_badge]` style: `shape: "ellipse"` |
| req-viz-badges-type-icon-4 | Grid Icon Contract Reused | Implemented | The badge reuses the canonical node type icon rather than introducing a second icon source. | Badge reads `icon_url` from host node data |
| req-viz-badges-type-icon-5 | Missing Icon Safe Fallback | Implemented | Nodes without an icon remain usable and simply omit the badge. | Filtered by `icon_url` presence check |

#### Future

- Define exact sizing, overlap, and scaling rules once the first implementation is exercised across several layouts.
- Expose badge bubble appearance as a configurable setting (background fill,
  border color, border width) on the projection or on a per-elevation basis
  so layouts that want a visible frame can opt in. Today the fully transparent
  borderless form is hard-coded as the default.
- Consider a per-projection override for the badge sizing rule (e.g. "smallest
  host wins" vs "fixed fraction of viewport") once more layouts exercise the
  current default.


### Node Body Preservation
----
RID: `req-viz-badges-body-preservation`
Status: `Implemented`

Badge placement must preserve the node body for the node's primary content.

#### Implementation

- For parent nodes, the node body should remain available for child node layout.
- For leaf nodes, the node body should remain available for the node's primary text label.
- The type icon badge should not require the icon to be centered in the node body.
- Badge positioning should reduce competition between iconography and primary content.

#### Development

This is the main practical reason for adopting the type icon badge pattern. It lets the type reminder stay visible while leaving the central area available for what the node needs to contain.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-badges-body-preservation-1 | Parent Body Preserved | Implemented | Parent nodes retain usable body space for children. | Badge is a separate node outside host bounds |
| req-viz-badges-body-preservation-2 | Leaf Body Preserved | Implemented | Leaf nodes retain usable body space for their names. | `_badge_active` style centers text label in body |
| req-viz-badges-body-preservation-3 | Icon No Longer Center-Bound | Implemented | The type icon no longer needs to occupy the center of the node body. | Icon moved to external badge node |

#### Future

If TAP later supports richer interior node content, keep badge placement rules biased toward protecting the node body first.


### Badge Set
----
RID: `req-viz-badges-badge-set`
Status: `Backlog`

A badge set is a grouped collection of related badges rendered together in a defined location on a node.

#### Implementation

Future work may define:

- how a badge set is represented in node metadata
- how a badge set is anchored on the node
- how badges are ordered within a set
- whether count-bearing badges and presence-only badges use the same contract
- how a node may render both a type icon badge and one or more badge sets without clutter

#### Development

The concept is worth naming now, but implementing it would pull in interaction, ordering, overflow, and visual-density questions that are better handled after the type icon badge has landed.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-badges-badge-set-1 | Badge Set Concept Reserved | Backlog | The spec reserves `badge set` as the term for a grouped badge construct. | |
| req-viz-badges-badge-set-2 | Detailed Contract Deferred | Backlog | Badge-set metadata, rendering, and placement are explicitly deferred. | |

#### Future

Define whether multiple badge sets may occupy the same edge, whether overflow collapses into a summary badge, and how badge-set ordering should work.


### Status Badge Sets
----
RID: `req-viz-badges-status-future`
Status: `Backlog`

TAP Viz should later support status badge sets for node-local signals such as information, warning, and alert.

#### Status Details

This requirement is intentionally tracked without locking in exact rendering, counting, or interaction behavior yet.

#### Implementation

Future work may define:

- the canonical badge vocabulary for informational and warning-style signals
- whether badges display counts, simple presence, or both
- the preferred anchor location for status badge sets
- whether status badges open node details, side panels, or inline popovers
- how status badge sets coexist with the type icon badge without visual clutter

#### Development

Keep the concept on the roadmap, but do not over-design it before real node-level signal use cases are ready.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-badges-status-future-1 | Future Status Grouping Tracked | Backlog | The spec explicitly tracks status-style badge sets as future work. | |

#### Future

When status badge sets are specified, define their semantics separately from the type icon badge so identity and state remain distinct visual channels.
