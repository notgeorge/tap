# GRIFT v0 Specification

## Philosophy

GRIFT, the Grid Interchange Format, is TAP's JSON-based interchange format for moving graph data between files and grids. GRIFT v0 is intentionally small, strict, and practical: it should be easy to validate, easy to diff, and sufficient to refactor plugin seed data such as the LOTR dataset into portable JSON files.

GRIFT is a full-object interchange format. It does not describe patches, history replay, or FLIP state. It carries enough canonical information for an importer to choose its own create, replace, upsert, or skip behavior while preserving universal entity identity through `entity_id`.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Portable      | TAP entities can be exported, shared, and re-imported as JSON   |
| 2. | Strict        | Unknown keys and malformed objects are rejected                 |
| 3. | Canonical     | Identity is preserved through explicit `entity_id` values       |
| 4. | Batch-Aware   | Imports can preserve originating batch structure and metadata   |
| 5. | Lightweight   | v0 excludes history, FLIP transport, and semantic dedupe logic |

## Terminology

- GRIFT document: the complete top-level JSON object
- metadata: the top-level GRIFT metadata object
- reserved object: the top-level `_reserved` object reserved for future extension
- entity envelope: the canonical entity metadata wrapper used by batch, node, and edge records
- batch container: one item in the top-level `batches` array
- batch entity: the `batch_entity` envelope for the serialized batch itself
- batch node: the `batch_node` payload for the serialized batch model
- node object: one item in a batch `nodes` array, consisting of `entity` plus `node`
- edge object: one item in a batch `edges` array, consisting of `entity` plus `edge`
- node payload: the `node` object containing typed full-object node data
- edge payload: the `edge` object containing typed full-object edge data and explicit endpoints

## JSON Schemas

GRIFT v0 should publish machine-readable JSON Schemas in addition to prose requirements.

These schemas are normative for structure and basic field validation. Model-specific node, batch, and edge-property validation remains type-driven and is defined by the importing TAP installation's model registry and field contract.

### `GriftEntityEnvelope`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["entity_id", "entity_type", "dimensions"],
  "properties": {
    "entity_id": {
      "type": "string",
      "format": "uuid"
    },
    "entity_type": {
      "type": "string",
      "minLength": 1
    },
    "name": {
      "type": "string",
      "minLength": 1
    },
    "dimensions": {
      "type": "object",
      "additionalProperties": {
        "type": "string"
      }
    },
    "created_at": {
      "type": "string",
      "format": "date-time"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time"
    },
    "deleted_at": {
      "oneOf": [
        {
          "type": "null"
        },
        {
          "type": "string",
          "format": "date-time"
        }
      ]
    }
  }
}
```

### `GriftNodeObject`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["entity", "node"],
  "properties": {
    "entity": {
      "$ref": "#/$defs/GriftEntityEnvelope"
    },
    "node": {
      "type": "object"
    }
  }
}
```

### `GriftEdgePayload`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["from_entity_id", "to_entity_id", "edge_type", "properties"],
  "properties": {
    "from_entity_id": {
      "type": "string",
      "format": "uuid"
    },
    "to_entity_id": {
      "type": "string",
      "format": "uuid"
    },
    "edge_type": {
      "type": "string",
      "minLength": 1
    },
    "properties": {
      "type": "object"
    }
  }
}
```

### `GriftEdgeObject`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["entity", "edge"],
  "properties": {
    "entity": {
      "$ref": "#/$defs/GriftEntityEnvelope"
    },
    "edge": {
      "$ref": "#/$defs/GriftEdgePayload"
    }
  }
}
```

### `GriftBatchContainer`

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["batch_entity", "batch_node", "nodes", "edges"],
  "properties": {
    "batch_entity": {
      "$ref": "#/$defs/GriftEntityEnvelope"
    },
    "batch_node": {
      "type": "object"
    },
    "nodes": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/GriftNodeObject"
      }
    },
    "edges": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/GriftEdgeObject"
      }
    }
  }
}
```

### `GriftDocument`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:tap:grift:v0:document",
  "type": "object",
  "additionalProperties": false,
  "required": ["metadata", "_reserved", "batches"],
  "properties": {
    "metadata": {
      "type": "object",
      "additionalProperties": false,
      "required": ["grift_version"],
      "properties": {
        "grift_version": {
          "type": "string",
          "minLength": 1
        }
      }
    },
    "_reserved": {
      "type": "object"
    },
    "batches": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/GriftBatchContainer"
      }
    }
  },
  "$defs": {
    "GriftEntityEnvelope": {
      "type": "object",
      "additionalProperties": false,
      "required": ["entity_id", "entity_type", "dimensions"],
      "properties": {
        "entity_id": {
          "type": "string",
          "format": "uuid"
        },
        "entity_type": {
          "type": "string",
          "minLength": 1
        },
        "name": {
          "type": "string",
          "minLength": 1
        },
        "dimensions": {
          "type": "object",
          "additionalProperties": {
            "type": "string"
          }
        },
        "created_at": {
          "type": "string",
          "format": "date-time"
        },
        "updated_at": {
          "type": "string",
          "format": "date-time"
        },
        "deleted_at": {
          "oneOf": [
            {
              "type": "null"
            },
            {
              "type": "string",
              "format": "date-time"
            }
          ]
        }
      }
    },
    "GriftNodeObject": {
      "type": "object",
      "additionalProperties": false,
      "required": ["entity", "node"],
      "properties": {
        "entity": {
          "$ref": "#/$defs/GriftEntityEnvelope"
        },
        "node": {
          "type": "object"
        }
      }
    },
    "GriftEdgePayload": {
      "type": "object",
      "additionalProperties": false,
      "required": ["from_entity_id", "to_entity_id", "edge_type", "properties"],
      "properties": {
        "from_entity_id": {
          "type": "string",
          "format": "uuid"
        },
        "to_entity_id": {
          "type": "string",
          "format": "uuid"
        },
        "edge_type": {
          "type": "string",
          "minLength": 1
        },
        "properties": {
          "type": "object"
        }
      }
    },
    "GriftEdgeObject": {
      "type": "object",
      "additionalProperties": false,
      "required": ["entity", "edge"],
      "properties": {
        "entity": {
          "$ref": "#/$defs/GriftEntityEnvelope"
        },
        "edge": {
          "$ref": "#/$defs/GriftEdgePayload"
        }
      }
    },
    "GriftBatchContainer": {
      "type": "object",
      "additionalProperties": false,
      "required": ["batch_entity", "batch_node", "nodes", "edges"],
      "properties": {
        "batch_entity": {
          "$ref": "#/$defs/GriftEntityEnvelope"
        },
        "batch_node": {
          "type": "object"
        },
        "nodes": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/GriftNodeObject"
          }
        },
        "edges": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/GriftEdgeObject"
          }
        }
      }
    }
  }
}
```

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-grift-format | [Document Format](#document-format) | Implemented | Top-level GRIFT JSON document |
| req-grift-envelope | [Entity Envelope](#entity-envelope) | Implemented | Canonical entity metadata carried in every object |
| req-grift-batch | [Batch Container](#batch-container) | Implemented | Serialized TAP batches wrap nodes and edges |
| req-grift-node | [Node Object](#node-object) | Implemented | Full-object node interchange contract |
| req-grift-edge | [Edge Object](#edge-object) | Implemented | Full-object edge interchange contract |
| req-grift-validation | [Validation Rules](#validation-rules) | Implemented | Strict schema and sanity rules |
| req-grift-order | [Canonical Export Ordering](#canonical-export-ordering) | Backlog | Export ordering (no exporter yet) |
| req-grift-v0-nongoals | [v0 Non-Goals](#v0-non-goals) | Implemented | Explicit exclusions for this version |

## Document Format
----
RID: `req-grift-format`
Status: `Implemented`

### Top-Level Shape

A GRIFT document is raw JSON. It is not JSON Lines, NDJSON, JSONC, or any other extended format.

The top-level object contains exactly these keys:

- `metadata`
- `_reserved`
- `batches`

`metadata` contains:

- `grift_version`: string, required

`_reserved` contains:

- an object reserved for future extension
- in v0 it may be empty

`batches` contains:

- an array of batch containers
- it may be empty

Unknown top-level keys are invalid.

### Example

```json
{
  "metadata": {
    "grift_version": "0"
  },
  "_reserved": {},
  "batches": []
}
```

### Example Document With Data

```json
{
  "metadata": {
    "grift_version": "0"
  },
  "_reserved": {},
  "batches": [
    {
      "batch_entity": {
        "entity_id": "01962ebd-f9d4-7f8a-9b4e-0e4f4d2dc001",
        "entity_type": "batch",
        "name": "Initial LOTR import",
        "dimensions": {},
        "created_at": "2026-04-06T15:00:00Z",
        "updated_at": "2026-04-06T15:00:00Z",
        "deleted_at": null
      },
      "batch_node": {
        "name": "Initial LOTR import",
        "description": "Imports seed entities and edges for the LOTR plugin.",
        "description_json": null,
        "source": "plugin:lotr",
        "metadata": {
          "dataset": "lotr"
        }
      },
      "nodes": [
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
      ],
      "edges": [
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
      ]
    }
  ]
}
```

## Entity Envelope
----
RID: `req-grift-envelope`
Status: `Implemented`

Every batch, node, and edge object carries an `entity`-style envelope containing canonical entity metadata from the TAP entity spine.

### Envelope Fields

Required:

- `entity_id`: UUIDv7 string
- `entity_type`: string
- `dimensions`: object

Optional:

- `name`: non-empty string
- `created_at`: RFC 3339 UTC datetime string
- `updated_at`: RFC 3339 UTC datetime string
- `deleted_at`: RFC 3339 UTC datetime string or `null`

### Envelope Rules

- `entity_id` is the sole identity key. Identity matching is by `entity_id` only.
- `dimensions` is always present, even when empty.
- `dimensions` is a flat string-to-string map.
- `name` is the canonical human-readable identifier when present.
- If `name` is present it must not be an empty string.
- `created_at`, `updated_at`, and `deleted_at` are optional in v0, but if present they are imported and validated.
- A batch envelope must use `entity_type == "batch"`.
- An edge envelope must use `entity_type == "edge"`.

### Timestamp Sanity Rules

If present:

- `updated_at >= created_at`
- `deleted_at >= updated_at`
- `deleted_at` may not exist unless `updated_at` also exists

If `created_at` is absent, no inferred creation time is assumed by the file format.

## Batch Container
----
RID: `req-grift-batch`
Status: `Implemented`

GRIFT batches preserve serialized TAP batch structure and group imported nodes and edges under their originating batch.

### Batch Shape

Each item in `batches` is an object with exactly these keys:

- `batch_entity`
- `batch_node`
- `nodes`
- `edges`

Unknown keys are invalid.

`batch_entity` is an entity envelope for the batch itself.

`batch_node` is the batch model payload.

`nodes` is an array of node objects and is always present.

`edges` is an array of edge objects and is always present.

### Batch Payload

`batch_node` is validated as a full-object payload against the `batch` model field contract:

- validate field shapes using the model's `FIELD_SCHEMA`
- required fields are `REPLACE_REQUIRED` if declared, otherwise `CREATE_REQUIRED`
- patch-only fields are excluded from GRIFT payload validation

In current TAP implementations this may be realized by validating against the synthesized `SERVICE_SCHEMAS["replace"]` schema, but that is an implementation detail rather than the canonical GRIFT contract.

### Batch Field Semantics

In v0:

- actor identity is omitted from the serialized batch object
- batch naming uses the `name` field on both `batch_entity` and `batch_node`
- `batch_entity.entity_type` must be `"batch"`

### Example Batch Container

```json
{
  "batch_entity": {
    "entity_id": "01962ebd-f9d4-7f8a-9b4e-0e4f4d2dc001",
    "entity_type": "batch",
    "name": "Initial LOTR import",
    "dimensions": {},
    "created_at": "2026-04-06T15:00:00Z",
    "updated_at": "2026-04-06T15:00:00Z",
    "deleted_at": null
  },
  "batch_node": {
    "name": "Initial LOTR import",
    "description": "Imports seed entities and edges for the LOTR plugin.",
    "description_json": null,
    "source": "plugin:lotr",
    "metadata": {
      "dataset": "lotr"
    }
  },
  "nodes": [],
  "edges": []
}
```

### Batch Timestamp Rules

If present:

- `started_at` and `closed_at` must be RFC 3339 UTC datetimes
- `closed_at >= started_at`

Consistency rules:

- `status == "open"` forbids `closed_at`
- `status == "closed"` requires `closed_at`
- `status == "failed"` requires `closed_at`
- `error_message` is only allowed when `status == "failed"`

## Node Object
----
RID: `req-grift-node`
Status: `Implemented`

Each node object is a full serialized TAP node.

### Node Shape

Each item in `nodes` is an object with exactly these keys:

- `entity`
- `node`

Unknown keys are invalid.

`entity` is an entity envelope.

`node` is the typed model payload.

### Node Validation

`node` is validated as a full-object payload against the model's field contract:

- validate field shapes using the model's `FIELD_SCHEMA`
- required fields are `REPLACE_REQUIRED` if declared, otherwise `CREATE_REQUIRED`
- `PATCH_EXTRA_FIELDS` are excluded from GRIFT payload validation

In current TAP implementations this may be realized by validating against the synthesized `SERVICE_SCHEMAS["replace"]` schema.

### Example Node Object

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

## Edge Object
----
RID: `req-grift-edge`
Status: `Implemented`

Each edge object is a full serialized TAP edge with its own backing entity and explicit endpoint references.

### Edge Shape

Each item in `edges` is an object with exactly these keys:

- `entity`
- `edge`

Unknown keys are invalid.

`entity` is an entity envelope for the edge's backing entity.

`edge` contains:

- `from_entity_id`: UUID string, required
- `to_entity_id`: UUID string, required
- `edge_type`: string, required
- `properties`: object, required

### Edge Validation

- `from_entity_id`, `to_entity_id`, and `edge_type` are GRIFT-level required fields
- `properties` is always present, even when empty
- `properties` is validated as a full-object payload against the edge model field contract
- patch-only fields are excluded from GRIFT payload validation
- `entity.entity_type` must be `"edge"`

In current TAP implementations this may be realized by validating `properties` against the synthesized `SERVICE_SCHEMAS["replace"]` schema for the edge model.

### Example Edge Object

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

## Validation Rules
----
RID: `req-grift-validation`
Status: `Implemented`

GRIFT v0 is intentionally strict.

### General Rules

- Unknown keys are rejected at every level except `_reserved`
- `_reserved` is reserved for future extension; v0 importers must ignore its contents
- All wrapper keys are part of validation, not informal hints
- Duplicate `entity_id` values anywhere in the file are invalid
- Duplicate batch `entity_id` values are invalid
- Wrapper arrays are always present, even when empty

Importer workflow, reference resolution, datetime comparison timing, and batch execution behavior are defined separately in the GRIFT importer specification.

## Canonical Export Ordering
----
RID: `req-grift-order`
Status: `Backlog`

GRIFT exports should be stable and diff-friendly.

Recommended canonical ordering:

- batches sorted by `started_at`
- nodes sorted by `entity.entity_id`
- edges sorted by `entity.entity_id`

Recommended formatting:

- UTF-8 encoded JSON
- pretty-printed
- two-space indentation
- trailing newline
- stable key ordering

These formatting requirements support human readability for type-based plugin data files while still allowing large mixed-type imports.

## v0 Non-Goals
----
RID: `req-grift-v0-nongoals`
Status: `Implemented`

GRIFT v0 explicitly does not define:

- history replay import
- FLIP transport or import
- host transaction timestamp transport
- semantic dedupe beyond `entity_id`
- content hashing for batch equivalence
- source plugin metadata
- actor federation across grids

Future versions may extend `_reserved`, document metadata, and batch comparison behavior without changing the basic entity-envelope-plus-payload model introduced here.
