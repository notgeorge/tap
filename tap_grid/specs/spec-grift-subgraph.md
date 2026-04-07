# GRIFT Subgraph Specification

## Philosophy

GRIFT v0 defines a batch-oriented interchange document for moving graph data between files and grids. Many TAP systems, however, need to exchange graph data without a batch wrapper: searches, gryphon traversals, viewer graph context, graph panels, and future graph-native APIs.

GRIFT Subgraph defines that common contract.

A GRIFT subgraph is the canonical batchless graph shape for TAP: a simple `nodes` and `edges` envelope whose members use the same full canonical node and edge shapes defined by GRIFT v0. This gives TAP one portable object contract for graph data while still allowing higher-level systems to add their own outer result metadata or presentation adapters.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Canonical     | TAP defines one standard node/edge member contract              |
| 2. | Reusable      | Searches, gryphon, web viewer context, and viz can share it     |
| 3. | Lightweight   | Subgraphs omit batch wrappers while preserving full object data |
| 4. | Strict        | Subgraph structure is schema-backed and stable                  |
| 5. | Layered       | Presentation metadata remains outside the canonical contract    |

## Terminology

- GRIFT subgraph: the canonical batchless graph envelope defined by this specification
- node member: one canonical node object in a subgraph `nodes` array
- edge member: one canonical edge object in a subgraph `edges` array
- full member shape: the canonical GRIFT-style nested member shape
- wrapper envelope: a higher-level result object that contains a subgraph plus other keys such as `info`, `warnings`, pagination metadata, or rendering metadata
- presentation adapter: a consumer-specific transform that derives UI-oriented fields from a canonical subgraph without redefining the underlying graph contract

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-grift-subgraph-shape | [Subgraph Shape](#subgraph-shape) | Implemented | Canonical `nodes` / `edges` envelope |
| req-grift-subgraph-layers | [Return Layers](#return-layers) | Implemented | `lite`, `full`, and `extended` graph member layers |
| req-grift-subgraph-members | [Canonical Member Shape](#canonical-member-shape) | Implemented | Members reuse GRIFT node and edge objects |
| req-grift-subgraph-order | [Ordering](#ordering) | Implemented | Array order expresses graph member order |
| req-grift-subgraph-wrap | [Wrapper Envelopes](#wrapper-envelopes) | Implemented | Search/web/viz may wrap subgraphs without redefining members |
| req-grift-subgraph-present | [Presentation Separation](#presentation-separation) | Implemented | UI/view metadata is out of canonical scope |
| req-grift-subgraph-impl | [Implementation Home](#implementation-home) | Implemented | Canonical serializers and validators live in `tap_grid.grift` |

## JSON Schema

The canonical GRIFT subgraph schema is:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:tap:grift:v0:subgraph",
  "type": "object",
  "additionalProperties": false,
  "required": ["nodes", "edges"],
  "properties": {
    "nodes": {
      "type": "array",
      "items": {
        "$ref": "urn:tap:grift:v0:document#/$defs/GriftNodeObject"
      }
    },
    "edges": {
      "type": "array",
      "items": {
        "$ref": "urn:tap:grift:v0:document#/$defs/GriftEdgeObject"
      }
    }
  }
}
```

This schema reuses the canonical GRIFT v0 node and edge member definitions.

## Subgraph Shape
----
RID: `req-grift-subgraph-shape`
Status: `Implemented`

A GRIFT subgraph is a JSON object with exactly these keys:

- `nodes`
- `edges`

Unknown keys are invalid at the canonical subgraph level.

Both arrays are always present, even when empty.

### Example

```json
{
  "nodes": [],
  "edges": []
}
```

## Return Layers
----
RID: `req-grift-subgraph-layers`
Status: `Implemented`

TAP should support three intentional subgraph return layers.

### `lite`

The `lite` layer carries only lightweight graph identity and relationship structure.

Intended use cases:

- fast neighborhood and traversal responses
- graph scans where full typed payloads are unnecessary
- lightweight intermediate graph contexts

In `lite` mode:

- node members carry entity-envelope data only
- edge members carry edge relationship data sufficient to describe the graph connection
- omitted canonical payload sections are not inferred

### `full`

The `full` layer carries the complete canonical GRIFT member shape.

Intended use cases:

- canonical subgraph responses
- interchange-oriented service responses
- any consumer that needs complete typed object data

In `full` mode:

- node members are full GRIFT node objects
- edge members are full GRIFT edge objects

`full` is the default and canonical subgraph return layer.

### `extended`

The `extended` layer carries `full` canonical graph data plus derived presentation or display metadata.

Intended use cases:

- web graph viewers
- graph panels
- table and navigation-oriented display helpers

Examples of extended fields:

- `icon_url`
- `shape`
- `url_id`
- display hints
- derived human-friendly endpoint labels

### Layering Rule

The layers are cumulative:

- `lite` is the smallest graph return layer
- `full` extends `lite`
- `extended` extends `full`

No layer may redefine the meaning of the fields provided by a lower layer.

## Canonical Member Shape
----
RID: `req-grift-subgraph-members`
Status: `Implemented`

Subgraph members reuse the full canonical GRIFT member shapes.

### Node Members

Each item in `nodes` is a GRIFT node object:

```json
{
  "entity": {
    "entity_id": "01962ebd-f9d4-7f8a-9b4e-0e4f4d2dc101",
    "entity_type": "character",
    "name": "Frodo Baggins",
    "dimensions": {},
    "created_at": "2026-04-06T15:00:00Z",
    "updated_at": "2026-04-06T15:00:00Z",
    "deleted_at": null
  },
  "node": {
    "name": "Frodo Baggins",
    "bio": "A hobbit of the Shire who inherits the One Ring."
  }
}
```

### Edge Members

Each item in `edges` is a GRIFT edge object:

```json
{
  "entity": {
    "entity_id": "01962ebd-f9d4-7f8a-9b4e-0e4f4d2dc201",
    "entity_type": "edge",
    "name": "WIELDS",
    "dimensions": {},
    "created_at": "2026-04-06T15:00:00Z",
    "updated_at": "2026-04-06T15:00:00Z",
    "deleted_at": null
  },
  "edge": {
    "from_entity_id": "01962ebd-f9d4-7f8a-9b4e-0e4f4d2dc101",
    "to_entity_id": "01962ebd-f9d4-7f8a-9b4e-0e4f4d2dc102",
    "edge_type": "WIELDS",
    "properties": {}
  }
}
```

### Canonical Rule

The full nested GRIFT member shape is the default and canonical subgraph contract for TAP graph responses.

TAP also defines `lite` and `extended` return layers, but `full` remains the canonical default. Alternate layers must be requested or selected explicitly and must not silently replace the canonical `full` member contract.

### Lite Member Guidance

In `lite` mode, node members should expose the entity-envelope fields directly and edge members should expose the edge relationship fields directly.

Example `lite` node:

```json
{
  "entity_id": "01962ebd-f9d4-7f8a-9b4e-0e4f4d2dc101",
  "entity_type": "character",
  "name": "Frodo Baggins",
  "dimensions": {},
  "created_at": "2026-04-06T15:00:00Z",
  "updated_at": "2026-04-06T15:00:00Z",
  "deleted_at": null
}
```

Example `lite` edge:

```json
{
  "entity_id": "01962ebd-f9d4-7f8a-9b4e-0e4f4d2dc201",
  "from_entity_id": "01962ebd-f9d4-7f8a-9b4e-0e4f4d2dc101",
  "to_entity_id": "01962ebd-f9d4-7f8a-9b4e-0e4f4d2dc102",
  "edge_type": "WIELDS",
  "properties": {}
}
```

## Ordering
----
RID: `req-grift-subgraph-order`
Status: `Implemented`

Member order is represented directly by JSON array order.

### Rules

- `nodes` array order expresses node ordering
- `edges` array order expresses edge ordering
- no secondary ordering structure is required in the canonical subgraph contract

Examples:

- alphabetized node results are represented by the order of `nodes`
- edge results ordered by type or creation time are represented by the order of `edges`

## Wrapper Envelopes
----
RID: `req-grift-subgraph-wrap`
Status: `Implemented`

Higher-level TAP systems may wrap a canonical subgraph in their own result envelope.

Examples:

- search may return:

```json
{
  "nodes": [...],
  "edges": [...],
  "info": {},
  "warnings": {}
}
```

- paginated search may return:

```json
{
  "count": 0,
  "limit": 25,
  "offset": 0,
  "results": {
    "nodes": [...],
    "edges": [...]
  }
}
```

### Rule

Wrapper envelopes may add outer metadata, but they must not redefine the canonical shape of node members or edge members.

## Presentation Separation
----
RID: `req-grift-subgraph-present`
Status: `Implemented`

Canonical graph data and presentation metadata are separate concerns.

The canonical subgraph contract does not include UI-oriented fields such as:

- `icon_url`
- `shape`
- `url_id`
- `from_name`
- `to_name`
- Cytoscape placement or rendering hints

These values may be derived by presentation adapters in `tap_web`, `tap_viz`, or other consumers, but they are not part of the canonical GRIFT subgraph member contract.

The `extended` return layer may include such fields for runtime responses, but that does not make them part of the canonical `full` interchange contract.

### Rule

Systems that need presentation-friendly graph payloads should derive them from a canonical GRIFT subgraph rather than inventing a separate canonical graph serialization.

## Implementation Home
----
RID: `req-grift-subgraph-impl`
Status: `Implemented`

The canonical implementation home for GRIFT subgraph serialization and validation is `tap_grid.grift`.

Responsibilities that belong in `tap_grid.grift`:

- entity envelope serialization
- node member serialization
- edge member serialization
- subgraph serialization
- subgraph structural validation
- reuse of GRIFT member validators across file import and service/search graph responses

Responsibilities that do not belong in `tap_grid.grift`:

- search pagination metadata
- search execution timing or warnings packaging
- web viewer context assembly
- graph-panel Cytoscape shaping
- table-oriented flattening or row navigation helpers

### Development

This keeps TAP's canonical graph interchange logic in one place. Search, gryphon, web, and viz should call into `tap_grid.grift` for canonical graph data rather than maintaining parallel serializers.
