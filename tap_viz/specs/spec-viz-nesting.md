# Viz Nesting Specification

## Philosophy

Viz nesting is the TAP Viz capability for showing graph entities as visually contained inside one another using Cytoscape compound nodes. The purpose of nesting is to express structural hierarchy without changing canonical graph semantics. A nested artifact is still an artifact, a `WIELDS` edge is still a graph edge, and the returned search subgraph remains the source of truth. Nesting only changes how the graph is rendered inside the TAP Viz graph panel.

The first version is intentionally narrow. It defines a small model-level metadata contract, a constrained Gryphon matcher subset, and a client-side resolver that runs after graph search merge and before Cytoscape element construction. This gives TAP a reliable starting point for rich hierarchical graph views without prematurely expanding the query engine or layout system.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | Hierarchical | TAP Viz can show entities inside other entities using Cytoscape compound nodes. |
| 2. | Search-Bounded | Nesting resolution operates only on the returned graph subgraph and does not perform additional fetches. |
| 3. | Model-Declared | Nesting intent is declared on model display metadata rather than embedded ad hoc in a page or panel. |
| 4. | Symmetric | Parent-side and child-side relationship declarations are peers; neither side is canonical. |
| 5. | Narrow First Pass | V0 uses an exact single-hop Gryphon subset and client-side resolution so the system can grow safely. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-viz-nesting-metadata | [Model Nesting Metadata](#model-nesting-metadata) | Proposed | Model-level metadata path and relationship object contract |
| req-viz-nesting-gryphon-subset | [Nesting Gryphon Subset](#nesting-gryphon-subset) | Proposed | Exact supported matcher syntax for nesting |
| req-viz-nesting-client-compound-node | [Client Compound Node Resolution](#client-compound-node-resolution) | Proposed | Client-side nesting resolution and Cytoscape parent assignment |
| req-viz-nesting-hidden-edges | [Hidden Containment Edges](#hidden-containment-edges) | Proposed | Consumed containment edges remain in Cytoscape but are hidden |
| req-viz-nesting-warnings | [Warning Categories](#warning-categories) | Proposed | Normative warning categories for invalid or ambiguous nesting |
| req-viz-nesting-lotr-saga-demo | [LOTR Saga Demo](#lotr-saga-demo) | Proposed | Saved-search-backed demonstration page for the v0 nesting behavior |


### Model Nesting Metadata
----
RID: `req-viz-nesting-metadata`
Status: `Proposed`

Models may declare viz nesting relationships through model display metadata under the `tap_viz` namespace.

#### Implementation

The normative metadata path is:

- `DEFAULT_DISPLAY["tap_viz"]["nesting"]["parent"]`
- `DEFAULT_DISPLAY["tap_viz"]["nesting"]["child"]`

Both `parent` and `child` are optional arrays of relationship definitions. Parent-side and child-side declarations are peers. Either side is sufficient to participate in nesting resolution. Duplicate declarations that resolve to the same accepted assignment are deduplicated quietly.

Each relationship definition is an object with exactly:

- `name`
- `description`
- `gryphon`

Example:

```python
DEFAULT_DISPLAY = {
    "tap_viz": {
        "shape": "ellipse",
        "nesting": {
            "parent": [
                {
                    "name": "character-wields-artifact",
                    "description": "Characters visually contain artifacts they wield.",
                    "gryphon": "(parent:character)-[:WIELDS]->(child:artifact)",
                }
            ],
            "child": [
                {
                    "name": "artifact-wielded-by-character",
                    "description": "Artifacts may be visually nested inside wielding characters.",
                    "gryphon": "(parent:character)-[:WIELDS]->(child:artifact)",
                }
            ],
        },
    }
}
```

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-nesting-metadata-1 | Metadata Path Is Normative | Proposed | Nesting metadata lives at `DEFAULT_DISPLAY["tap_viz"]["nesting"]`. | |
| req-viz-nesting-metadata-2 | Parent And Child Lists Supported | Proposed | Models may declare `parent` and `child` relationship arrays independently. | |
| req-viz-nesting-metadata-3 | Sides Are Peer Declarations | Proposed | Parent-side and child-side rules are peers; neither side is canonical. | |
| req-viz-nesting-metadata-4 | Relationship Object Shape Fixed | Proposed | Each relationship definition contains `name`, `description`, and `gryphon`. | |

#### Future

- Add `parental_preference` once real ambiguity cases require explicit precedence.
- Consider opt-out or selective disable controls for certain relationships within a layout.


### Nesting Gryphon Subset
----
RID: `req-viz-nesting-gryphon-subset`
Status: `Proposed`

Nesting uses a restricted Gryphon subset intended for client-side interpretation inside TAP Viz.

#### Implementation

The supported matcher form is exactly one directed single-hop pattern:

```text
(parent[:label])-[:EDGE_TYPE]->(child[:label])
(parent[:label])<-[:EDGE_TYPE]-(child[:label])
```

Rules:

- Exactly one pattern is allowed.
- Exactly one directed hop is allowed.
- The node variable names `parent` and `child` are required.
- The edge variable is optional.
- The edge type is required.
- Node labels are optional only on the non-self side according to the metadata context.
- Any Gryphon outside this subset is invalid for nesting resolution.

Accepted examples:

```text
(parent:realm)-[:CONTAINS]->(child:location)
```

```text
(parent:location)<-[:LOCATED_IN]-(child:character)
```

```text
(parent:character)-[:WIELDS]->(child:artifact)
```

```text
(parent:location)-[rel:CONTAINS]->(child)
```

Context-sensitive validation:

- Inside a `parent` relationship list, the `parent` label must be present and must match the current model type.
- Inside a `child` relationship list, the `child` label must be present and must match the current model type.
- The opposite side may omit its label.

Rejected examples:

```text
(a:character)-[:WIELDS]->(b:artifact)
```

```text
(parent)-[:WIELDS]-(child:artifact)
```

```text
(parent:character)-[:WIELDS*1..2]->(child:artifact)
```

```text
MATCH (parent:character)-[:WIELDS]->(child:artifact) RETURN parent, child
```

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-nesting-gryphon-subset-1 | Single-Hop Directed Pattern Only | Proposed | Nesting matchers accept exactly one directed single-hop pattern. | |
| req-viz-nesting-gryphon-subset-2 | Parent And Child Variables Required | Proposed | The node variable names must be `parent` and `child`. | |
| req-viz-nesting-gryphon-subset-3 | Edge Type Required | Proposed | The edge type must be specified for nesting evaluation. | |
| req-viz-nesting-gryphon-subset-4 | Contextual Label Validation | Proposed | The self side label is required and must match the current model type for the containing metadata list. | |
| req-viz-nesting-gryphon-subset-5 | Unsupported Syntax Rejected | Proposed | Any matcher outside the accepted subset is rejected and warned. | |

#### Future

- Consider broader in-memory Gryphon support once more viz-side matching use cases appear.
- Consider formal parser reuse if TAP later standardizes client-side Gryphon utilities beyond nesting.


### Client Compound Node Resolution
----
RID: `req-viz-nesting-client-compound-node`
Status: `Proposed`

TAP Viz resolves nesting client-side and emits Cytoscape compound-node parent assignments before Cytoscape element construction.

#### Implementation

The v0 resolver is a TAP Viz utility named `TapVizNestingResolver`.

Pipeline order:

1. Execute the saved search or searches and merge the returned graph envelopes into the working graph state.
2. Run `TapVizNestingResolver` against the merged returned subgraph only.
3. Resolve accepted parent-child assignments in one flat pass.
4. Reject ambiguous children.
5. Reject cycles by dropping all assignments participating in the cycle.
6. Build Cytoscape elements.
7. For each accepted nested child, emit `data.parent = <parent_entity_id>` on the Cytoscape node.

`TapVizNestingResolver` produces:

- `parentByChildId`
- `hiddenEdgeIds`
- `warnings`

Resolution rules:

- Parent-side and child-side rules are both considered.
- Either side is sufficient to propose a parent-child assignment.
- Multiple children per parent are valid.
- A child may have at most one accepted parent.
- Nodes with no accepted parent remain top-level.
- A node may be both a parent and a child in the same render.
- Only the returned search subgraph is considered. Nesting resolution does not perform additional searches or fetches.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-nesting-client-compound-node-1 | Resolver Lives In Tap Viz | Proposed | Nesting resolution is a TAP Viz client-side concern rather than a grid or web concern. | |
| req-viz-nesting-client-compound-node-2 | Search Merge Precedes Nesting | Proposed | Nesting resolution occurs after graph search merge and before Cytoscape element construction. | |
| req-viz-nesting-client-compound-node-3 | Cytoscape Parent Data Emitted | Proposed | Accepted nested children are emitted with Cytoscape `data.parent` values. | |
| req-viz-nesting-client-compound-node-4 | Flat Pass Resolution | Proposed | Parent assignments are resolved in one flat pass rather than level-by-level execution. | |
| req-viz-nesting-client-compound-node-5 | Returned Subgraph Is Scope | Proposed | The resolver evaluates only the returned subgraph and does not query outside it. | |

#### Future

- Add component-specific inner layouts after the nesting contract stabilizes.
- Add zoom and scale behavior by containment depth.
- Add richer compound-node styling once real nested pages exist.


### Hidden Containment Edges
----
RID: `req-viz-nesting-hidden-edges`
Status: `Proposed`

Edges consumed as accepted containment relationships remain in Cytoscape but are hidden from visual display.

#### Implementation

When an edge participates in an accepted parent-child assignment:

- the edge remains present in Cytoscape
- the edge is marked with a hidden containment class
- the edge is not shown in the normal rendered graph

Only edges consumed for accepted parent-child assignments are hidden. If an edge could have implied containment but the proposed nesting assignment was rejected due to ambiguity, cycle participation, or invalid context, that edge remains visually available.

This preserves future room for traversal overlays, highlighting, or other logic that may need the original edge objects even when the edge is not normally shown.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-nesting-hidden-edges-1 | Consumed Edges Stay In Cytoscape | Proposed | Edges used for accepted nesting remain in the Cytoscape element set. | |
| req-viz-nesting-hidden-edges-2 | Consumed Edges Are Hidden By Class | Proposed | Accepted containment edges are hidden through styling or classing rather than removal. | |
| req-viz-nesting-hidden-edges-3 | Rejected Assignments Do Not Hide Edges | Proposed | An edge remains visible when its proposed nesting assignment was not accepted. | |

#### Future

- Define formal runtime affordances for temporarily showing hidden containment edges.


### Warning Categories
----
RID: `req-viz-nesting-warnings`
Status: `Proposed`

The v0 nesting system emits normative warning categories through `console.warn` when nesting cannot be applied cleanly.

#### Implementation

The warning transport in v0 is `console.warn`.

The warning categories are:

- `unsupported_matcher_syntax`
- `context_type_mismatch`
- `multiple_parents`
- `cycle_detected`

Category meanings:

- `unsupported_matcher_syntax`
  The matcher text is outside the accepted nesting Gryphon subset.
- `context_type_mismatch`
  The self-side label is missing or does not match the current model type for the metadata list being evaluated.
- `multiple_parents`
  More than one distinct parent was proposed for the same child after evaluating all applicable rules.
- `cycle_detected`
  Accepted parent-child assignments would create a cycle; all assignments participating in that cycle are dropped.

Message text is implementation-defined, but warnings should provide enough detail to identify the relationship definition, involved entities, and the failure reason.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-nesting-warnings-1 | Console Warn Transport | Proposed | V0 warnings surface through `console.warn`. | |
| req-viz-nesting-warnings-2 | Warning Categories Are Normative | Proposed | The warning categories defined here are part of the contract. | |
| req-viz-nesting-warnings-3 | Ambiguous Parents Skip Nesting | Proposed | A child with multiple candidate parents is left unnested and a warning is emitted. | |
| req-viz-nesting-warnings-4 | Cycles Drop Participating Assignments | Proposed | Cycles cause all participating assignments to be dropped and warned. | |

#### Future

- Add richer warning surfaces in the panel runtime beyond the browser console.
- Define structured warning payloads if the panel later needs UI-visible diagnostics.


### LOTR Saga Demo
----
RID: `req-viz-nesting-lotr-saga-demo`
Status: `Proposed`

TAP Viz should include a saved-search-backed LOTR Saga demo page that exercises the v0 nesting system on a concrete story-state graph.

#### Implementation

The LOTR Saga demo is a non-normative example fixture and implementation-tracking requirement for the v0 nesting work.

The demo should:

- live as a page within the existing dataset page structure
- use a saved search
- resolve nesting only from the exact returned subgraph
- demonstrate the containment chain:
  - `Middle-earth (realm) -> location`
  - `location -> character`
  - `character -> artifact`
- hide accepted containment edges for `CONTAINS`, `LOCATED_IN`, and `WIELDS`

The first story-state should include only the exact entities and edges needed for the demo slice, not nearby extra context. The working example discussed for v0 is a split story-state where:

- Frodo and Sam are in Mordor
- Gandalf, Aragorn, Legolas, and the remaining selected companions are in Rohan
- Sauron is included
- all wielded artifacts for the included characters are shown

Representative metadata examples for the demo types:

```python
DEFAULT_DISPLAY = {
    "tap_viz": {
        "shape": "hexagon",
        "nesting": {
            "parent": [
                {
                    "name": "realm-contains-location",
                    "description": "A realm visually contains its locations.",
                    "gryphon": "(parent:realm)-[:CONTAINS]->(child:location)",
                }
            ]
        },
    }
}
```

```python
DEFAULT_DISPLAY = {
    "tap_viz": {
        "shape": "round-rectangle",
        "nesting": {
            "parent": [
                {
                    "name": "location-contains-location",
                    "description": "A location may visually contain a child location.",
                    "gryphon": "(parent:location)-[:CONTAINS]->(child:location)",
                },
                {
                    "name": "location-contains-character",
                    "description": "A location visually contains characters located there.",
                    "gryphon": "(parent:location)<-[:LOCATED_IN]-(child:character)",
                },
            ],
            "child": [
                {
                    "name": "location-inside-realm",
                    "description": "A location may be visually nested inside a containing realm.",
                    "gryphon": "(parent:realm)-[:CONTAINS]->(child:location)",
                },
                {
                    "name": "location-inside-location",
                    "description": "A location may be visually nested inside a parent location.",
                    "gryphon": "(parent:location)-[:CONTAINS]->(child:location)",
                },
            ],
        },
    }
}
```

```python
DEFAULT_DISPLAY = {
    "tap_viz": {
        "shape": "ellipse",
        "nesting": {
            "parent": [
                {
                    "name": "character-wields-artifact",
                    "description": "A character visually contains artifacts they wield.",
                    "gryphon": "(parent:character)-[:WIELDS]->(child:artifact)",
                }
            ],
            "child": [
                {
                    "name": "character-inside-location",
                    "description": "A character may be visually nested inside its location.",
                    "gryphon": "(parent:location)<-[:LOCATED_IN]-(child:character)",
                }
            ],
        },
    }
}
```

```python
DEFAULT_DISPLAY = {
    "tap_viz": {
        "shape": "rectangle",
        "nesting": {
            "child": [
                {
                    "name": "artifact-inside-character",
                    "description": "An artifact may be visually nested inside a wielding character.",
                    "gryphon": "(parent:character)-[:WIELDS]->(child:artifact)",
                }
            ]
        },
    }
}
```

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-viz-nesting-lotr-saga-demo-1 | Saved Search Used | Proposed | The LOTR Saga page is driven by a saved search rather than ad hoc page assembly logic. | |
| req-viz-nesting-lotr-saga-demo-2 | Exact Returned Subgraph Used | Proposed | Nesting for the demo is derived only from the exact returned subgraph. | |
| req-viz-nesting-lotr-saga-demo-3 | Realm Location Character Artifact Chain Shown | Proposed | The page demonstrates realm, location, character, and artifact containment together. | |
| req-viz-nesting-lotr-saga-demo-4 | Containment Edges Hidden | Proposed | Accepted `CONTAINS`, `LOCATED_IN`, and `WIELDS` containment edges are hidden visually. | |

#### Future

- Expand LOTR Saga into a richer timeline or story-history visualization once nesting and layout features mature.
