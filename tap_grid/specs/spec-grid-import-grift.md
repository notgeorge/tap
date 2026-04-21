# GRIFT Import Specification

## Philosophy

GRIFT defines the interchange document. The GRIFT importer specification defines how TAP consumes that document safely, consistently, and idempotently.

This separation is deliberate. The file format should stay stable and portable, while importer behavior can evolve around preflight checks, execution modes, provenance recording, and plugin-loading workflows without muddying the document contract itself.

## Goals

|    |              |                                                                 |
| :---: | ---       | ---                                                             |
| 1. | Safe          | Validate the full file before mutation begins                   |
| 2. | Idempotent    | Skip already-imported batches by batch identity                 |
| 3. | Deterministic | Use one reference time and one preflight result per file        |
| 4. | Configurable  | Support strict and permissive dangling-edge handling            |
| 5. | Local         | Preserve GRIFT identity while recording import-side provenance  |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-grid-import-grift-scope | [Importer Scope](#importer-scope) | Implemented | GRIFT importer responsibilities |
| req-grid-import-grift-preflight | [File Preflight](#file-preflight) | Implemented | Parse, schema validation, duplicate detection, reference analysis |
| req-grid-import-grift-time | [Reference Time](#reference-time) | Implemented | Single datetime comparison point per file |
| req-grid-import-grift-identity | [Identity And Matching](#identity-and-matching) | Implemented | Entity and batch identity rules |
| req-grid-import-grift-batch | [Batch Execution](#batch-execution) | Implemented | Per-batch transactional import behavior |
| req-grid-import-grift-dangling | [Dangling Edge Modes](#dangling-edge-modes) | Implemented | Strict and permissive handling |
| req-grid-import-grift-provenance | [Import-Side Provenance](#import-side-provenance) | Implemented | Local actor/history behavior |
| req-grid-import-grift-results | [Import Results](#import-results) | Implemented | Structured reporting expectations |

## Importer Scope
----
RID: `req-grid-import-grift-scope`
Status: `Implemented`

The GRIFT importer is responsible for:

- reading a GRIFT document
- validating the document against the GRIFT format contract
- validating typed payloads against the local TAP model registry and field contract
- performing file-level preflight checks before mutation
- deciding batch execution behavior
- recording local import-side provenance

The GRIFT importer is not responsible for redefining the GRIFT document structure. That remains in `spec-grift-v0.md`.

## File Preflight
----
RID: `req-grid-import-grift-preflight`
Status: `Implemented`

Before any mutation begins, the importer must complete a full-file preflight pass.

### Preflight Steps

1. Parse the file as raw JSON.
2. Validate the top-level document and container structure against the GRIFT schemas.
3. Validate every batch, node, and edge wrapper shape.
4. Validate typed payloads against the local TAP model registry and field contract:
   - field shapes from `FIELD_CRUD_SCHEMA`
   - required fields from `REPLACE_REQUIRED` if declared, otherwise `CREATE_REQUIRED`
   - patch-only fields excluded
5. Detect duplicate `entity_id` values across the entire file.
6. Detect duplicate batch `entity_id` values.
7. Resolve all edge endpoint references against:
   - entities present in the same file
   - entities already present in the local grid
8. Determine which batches already exist locally.
9. Produce one preflight result that drives the execution phase.

### Preflight Rule

No batch transaction may begin until the full file has passed preflight, except for dangling-edge handling in permissive mode, where the importer may proceed with a precomputed skip list.

### Identity Sanity

- the importer must sanity-check that the resolved local model type matches the envelope `entity_type`
- if an object payload format ever redundantly carries its own entity identity fields, those values must match the enclosing entity envelope exactly

## Reference Time
----
RID: `req-grid-import-grift-time`
Status: `Implemented`

The importer must capture one reference time at file-import start.

### Rules

- all GRIFT datetime comparisons use that single reference time
- the reference time applies to entity envelope timestamps and batch timestamps
- imported datetimes must be less than or equal to the reference time
- no explicit clock-skew allowance is defined in v0

This keeps file validation deterministic and avoids per-record timing drift during large imports.

## Identity And Matching
----
RID: `req-grid-import-grift-identity`
Status: `Implemented`

### Entity Identity

- `entity_id` is universal identity and is preserved across grids
- import matching is by `entity_id` only
- v0 performs no semantic dedupe beyond `entity_id`

### Batch Identity

- batch identity is the `entity_id` carried in `batch_entity`
- if a local object with that ID exists but is not a batch, import must fail
- if a local batch with that ID already exists, the importer assumes that batch has already been imported and skips it

Future versions may add content-hash or semantic batch comparison, but v0 does not.

## Batch Execution
----
RID: `req-grid-import-grift-batch`
Status: `Implemented`

Each GRIFT batch executes as its own import unit after successful file preflight.

### Execution Rules

- batches may be executed in file order or reordered internally if behavior is equivalent
- each batch should execute in its own transaction
- within a batch, nodes must be processed before edges
- skipped batches do not run any mutation logic
- node and edge mutations must route through the TAP service layer rather than direct ORM writes
- the imported GRIFT batch `batch_entity.entity_id` becomes the `batch_id` placed into `CallerContext` for the service-layer write execution
- the GRIFT batch is therefore the live service-layer batch context for the imported node and edge writes

### Import Modes

GRIFT itself is neutral about create, replace, patch, or upsert semantics. The importer may expose one or more execution modes, but whichever mode it chooses must operate on the canonical GRIFT identities and validated full-object payloads produced by preflight.

## Dangling Edge Modes
----
RID: `req-grid-import-grift-dangling`
Status: `Implemented`

The importer should support two dangling-edge modes.

### Strict Mode

- any dangling edge is a preflight failure
- no batch transaction begins

### Permissive Mode

- preflight records each dangling edge
- execution skips only the offending edges
- each skipped edge is logged
- valid nodes and valid edges may still import

In both modes, dangling-edge analysis is completed during preflight, not discovered opportunistically mid-transaction.

## Import-Side Provenance
----
RID: `req-grid-import-grift-provenance`
Status: `Implemented`

GRIFT carries originating identities and batch metadata, but import-side provenance is owned by the importing grid.

### Rules

- the importing grid records its own actor, history, and batch-side effects locally
- serialized batch actor identity is omitted in v0 and must not be required for import
- local patching or upsert behavior is tracked in the importing grid's own history systems
- GRIFT v0 does not replay foreign history or FLIP state

### Batch Description JSON

The importer should record importer metadata in the local batch `description_json` using the existing TAP structured-description wrapper:

```json
{
  "format": "tap.grift.import.v0",
  "data": {
    "importer": "grift",
    "grift_version": "0",
    "import_mode": "upsert",
    "dangling_edge_mode": "permissive",
    "imported_at": "2026-04-06T16:00:00Z",
    "source_batch_entity_id": "01962ebd-f9d4-7f8a-9b4e-0e4f4d2dc001"
  }
}
```

Rules:

- importer metadata uses `format == "tap.grift.import.v0"`
- if the incoming batch already carries `description_json`, the importer preserves it and merges importer metadata into the local batch description data
- if the imported batch metadata already uses `format == "tap.grift.import.v0"`, the importer may overwrite that format block with the new local import metadata rather than nesting ambiguous duplicate copies
- source batch timestamps from the GRIFT payload must be preserved in importer metadata rather than treated as the local batch creation timestamps
- local batch lifecycle timestamps remain local infrastructure timestamps owned by the importing grid
- when present in the GRIFT batch payload or batch envelope, source batch timestamps must be copied into `description_json.data` under source-prefixed keys
- the importer must not assign GRIFT-provided source batch timestamps to the local `Batch.started_at` or `Batch.closed_at` fields

Recommended preserved source timestamp keys:

- `source_started_at`
- `source_closed_at`
- `source_created_at`
- `source_updated_at`

## Import Results
----
RID: `req-grid-import-grift-results`
Status: `Implemented`

The importer should return a structured result describing what happened.

### Result Shape

At minimum the result should include:

- `success`: overall boolean
- `grift_version`: file version string
- `import_mode`: importer mode string
- `dangling_edge_mode`: importer dangling-edge mode string
- `reference_time`: RFC 3339 UTC datetime string
- `counts`: aggregate counts object
- `imported_batches`: array
- `skipped_batches`: array
- `errors`: array
- `warnings`: array

### Issue Object

`errors` and `warnings` share one issue object shape.

Every issue object should include:

- `code`: stable machine-readable code
- `message`: human-readable message
- `phase`: one of `parse`, `schema`, `validation`, `preflight`, `execution`
- `path`: simple JSONPath string
- `entity_id`: UUID string or `null`
- `batch_entity_id`: UUID string or `null`
- `entity_type`: string or `null`
- `operation`: string or `null`

Optional edge context when relevant:

- `from_entity_id`
- `to_entity_id`
- `edge_entity_id`

Rules:

- every non-file-level issue should include an `entity_id` when the affected object can be identified
- every issue must include a `path`
- file-level issues use `path == "$"` and `entity_id == null`
- one issue is emitted per violated field, not one giant grouped object per entity

### Batch Summary Object

Each entry in `imported_batches` should include:

- `batch_entity_id`
- `path`
- `nodes_imported`
- `edges_imported`
- `edges_skipped`
- `errors_count`
- `warnings_count`

Each entry in `skipped_batches` should include:

- `batch_entity_id`
- `path`
- `reason`

### Counts Object

Recommended aggregate counts:

- `batches_imported`
- `batches_skipped`
- `nodes_imported`
- `edges_imported`
- `edges_skipped`
- `errors`
- `warnings`

### Error Code Taxonomy

v0 should define stable codes for common importer outcomes, including:

- `invalid_json`
- `schema_validation_failed`
- `duplicate_entity_id`
- `duplicate_batch_id`
- `unknown_entity_type`
- `payload_validation_failed`
- `timestamp_in_future`
- `timestamp_order_invalid`
- `entity_type_mismatch`
- `dangling_edge`
- `batch_already_imported`
- `execution_failed`

### Result Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:tap:grift-import:v0:result",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "success",
    "grift_version",
    "import_mode",
    "dangling_edge_mode",
    "reference_time",
    "counts",
    "imported_batches",
    "skipped_batches",
    "errors",
    "warnings"
  ],
  "properties": {
    "success": {
      "type": "boolean"
    },
    "grift_version": {
      "type": "string",
      "minLength": 1
    },
    "import_mode": {
      "type": "string",
      "minLength": 1
    },
    "dangling_edge_mode": {
      "type": "string",
      "enum": ["strict", "permissive"]
    },
    "reference_time": {
      "type": "string",
      "format": "date-time"
    },
    "counts": {
      "$ref": "#/$defs/Counts"
    },
    "imported_batches": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/ImportedBatch"
      }
    },
    "skipped_batches": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/SkippedBatch"
      }
    },
    "errors": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/Issue"
      }
    },
    "warnings": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/Issue"
      }
    }
  },
  "$defs": {
    "Counts": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "batches_imported",
        "batches_skipped",
        "nodes_imported",
        "edges_imported",
        "edges_skipped",
        "errors",
        "warnings"
      ],
      "properties": {
        "batches_imported": {"type": "integer", "minimum": 0},
        "batches_skipped": {"type": "integer", "minimum": 0},
        "nodes_imported": {"type": "integer", "minimum": 0},
        "edges_imported": {"type": "integer", "minimum": 0},
        "edges_skipped": {"type": "integer", "minimum": 0},
        "errors": {"type": "integer", "minimum": 0},
        "warnings": {"type": "integer", "minimum": 0}
      }
    },
    "Issue": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "code",
        "message",
        "phase",
        "path",
        "entity_id",
        "batch_entity_id",
        "entity_type",
        "operation"
      ],
      "properties": {
        "code": {
          "type": "string",
          "minLength": 1
        },
        "message": {
          "type": "string",
          "minLength": 1
        },
        "phase": {
          "type": "string",
          "enum": ["parse", "schema", "validation", "preflight", "execution"]
        },
        "path": {
          "type": "string",
          "minLength": 1
        },
        "entity_id": {
          "oneOf": [
            {"type": "null"},
            {"type": "string", "format": "uuid"}
          ]
        },
        "batch_entity_id": {
          "oneOf": [
            {"type": "null"},
            {"type": "string", "format": "uuid"}
          ]
        },
        "entity_type": {
          "oneOf": [
            {"type": "null"},
            {"type": "string", "minLength": 1}
          ]
        },
        "operation": {
          "oneOf": [
            {"type": "null"},
            {"type": "string", "minLength": 1}
          ]
        },
        "from_entity_id": {
          "type": "string",
          "format": "uuid"
        },
        "to_entity_id": {
          "type": "string",
          "format": "uuid"
        },
        "edge_entity_id": {
          "type": "string",
          "format": "uuid"
        }
      }
    },
    "ImportedBatch": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "batch_entity_id",
        "path",
        "nodes_imported",
        "edges_imported",
        "edges_skipped",
        "errors_count",
        "warnings_count"
      ],
      "properties": {
        "batch_entity_id": {"type": "string", "format": "uuid"},
        "path": {"type": "string", "minLength": 1},
        "nodes_imported": {"type": "integer", "minimum": 0},
        "edges_imported": {"type": "integer", "minimum": 0},
        "edges_skipped": {"type": "integer", "minimum": 0},
        "errors_count": {"type": "integer", "minimum": 0},
        "warnings_count": {"type": "integer", "minimum": 0}
      }
    },
    "SkippedBatch": {
      "type": "object",
      "additionalProperties": false,
      "required": ["batch_entity_id", "path", "reason"],
      "properties": {
        "batch_entity_id": {"type": "string", "format": "uuid"},
        "path": {"type": "string", "minLength": 1},
        "reason": {"type": "string", "minLength": 1}
      }
    }
  }
}
```
