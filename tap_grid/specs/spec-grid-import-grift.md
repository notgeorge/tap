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
| req-grid-import-grift-force-reimport | [Force Re-Import](#force-re-import) | Proposed | Explicit bypass of the skip-if-exists batch guard, DEBUG-gated |
| req-grid-import-grift-batch-scoped-sweep | [Batch-Scoped Sweep](#batch-scoped-sweep) | Proposed | Tombstone orphaned entities created by a force-reimported batch; optional strict mode aborts on any guardrail miss |
| req-grid-import-grift-sweep-purge | [Sweep Purge](#sweep-purge) | Proposed | Hard-delete escalation of batch-scoped sweep, DEBUG-gated |
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
- the skip behavior may be bypassed explicitly via `req-grid-import-grift-force-reimport`; default behavior remains skip-if-exists

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

## Force Re-Import
----
RID: `req-grid-import-grift-force-reimport`
Status: `Proposed`

The importer must expose an explicit, opt-in path to re-execute a batch whose `batch_entity.entity_id` is already present locally. Default behavior (skip-if-exists, per `req-grid-import-grift-identity`) is unchanged.

This is the escape valve promised by *"Future versions may add content-hash or semantic batch comparison, but v0 does not."* It exists for development iteration on GRIFT files — editing content, re-running the importer, and seeing the new state reflected without generating a fresh `batch_entity.entity_id` and bumping plugin contracts.

### Invocation

- The command line or programmatic API must accept a `--force-batches=<batch_entity_id>[,<batch_entity_id>...]` argument. No flag is permitted to force an entire file or plugin in one call.
- The argument names `batch_entity` identities explicitly. Anything not in the list follows normal skip-if-exists semantics.
- An empty or missing `--force-batches` argument means the feature is inactive; the importer behaves as today.

### Execution

- For each named batch, the importer bypasses the skip check and runs the full batch execution path (`req-grid-import-grift-batch`).
- The batch's node and edge writes go through the service layer with `CallerContext.batch_id = batch_entity.entity_id` — the **original** id, unchanged. Force re-import does not mint a new batch; it re-applies the existing one.
- Upsert semantics apply: existing nodes with matching `entity_id` are updated; new nodes introduced in the revised content are created; unchanged nodes are no-ops.
- Removals — entities that existed under this batch previously but are absent from the revised content — are NOT handled by this requirement. Removal behavior is defined by `req-grid-import-grift-batch-scoped-sweep`.

### Environment Gate

**Invariant:** Force re-import is permitted if and only if Django's `DEBUG` setting is `True` at the moment of invocation. There is no alternate flag, override, settings key, environment variable, or command-line argument that enables it in any other configuration. This invariant is binding on every requirement that builds on force re-import (`req-grid-import-grift-batch-scoped-sweep`, `req-grid-import-grift-sweep-purge`).

- When `DEBUG` is `False`, the importer must refuse the invocation with a dedicated error code (e.g. `force_reimport_refused_production`) distinct from "batch not found" or "invalid argument" errors, so the operator can see exactly why it was rejected.
- The gate is not a security boundary — an operator who can flip `DEBUG` can already read and write the database directly. The gate exists solely to prevent accidental use of dev ergonomics in production deploy scripts. It is not a substitute for deployment discipline and must not be treated as one.
- Future proposals to relax or conditionally bypass this gate (e.g. "staging environments should allow force re-import") must land as explicit, named requirements. This requirement does not anticipate such cases.

### Audit Trail

- Each force re-import must emit a `BatchEvent` (or equivalently-structured event record) of type `FORCE_REIMPORT` against the batch, with:
  - timestamp of the re-import
  - actor (per `req-grid-import-grift-provenance`)
  - count of nodes updated, nodes created, edges updated, edges created, entities swept (per `req-grid-import-grift-batch-scoped-sweep` when that applies)
- The original ingestion's batch events remain untouched. The audit reads as a sequence: initial ingest → force re-import(s) → further activity.
- A batch that has been force-reimported is still the same batch entity. It retains its original `entity_id`, batch metadata, and service-layer ownership semantics.

### Non-Goals

- Force re-import does not compare content hashes, compute semantic diffs, or flag drift proactively. It runs exactly when asked, and only when asked.
- It does not bypass preflight validation. A force-reimported batch still passes through schema validation, reference analysis, and dangling-edge checks.

## Batch-Scoped Sweep
----
RID: `req-grid-import-grift-batch-scoped-sweep`
Status: `Proposed`

When a batch is force re-imported (`req-grid-import-grift-force-reimport`), the revised content may omit nodes or edges that the original ingestion created. The sweep detects those orphans and tombstones them via the service-layer delete path, bounded strictly to entities this batch originally created.

### Sweep Candidates

A candidate for sweep is an entity meeting all of:

- the entity's **creation history row** (first historical record) carries `batch_id == <the batch being force-reimported>`
- the entity's current `entity_id` does not appear in the revised batch's node or edge set

Candidates are computed after the revised batch's upserts have been staged (so the new node/edge set is known) but before any deletions are applied.

### Guardrails

A candidate is only swept if **both** guardrails pass:

**Guardrail A — Ownership**

No history row exists for this entity with `batch_id != <this batch>`. If any other batch has written to the entity (create, update, or delete), skip it. The entity has left this batch's exclusive ownership and the sweep must not reclaim it.

**Guardrail B — Referential Integrity**

After the sweep's proposed deletions are applied, no edge exists that is connected to this entity — in either direction. An edge survives the sweep and references the candidate if:

- the edge exists in the current graph AND is not itself being swept, OR
- the edge is newly created by the revised batch content and points at this candidate (a content bug in the revision — preflight should catch it, but the guardrail provides a second line of defense)

If any such edge survives, skip the candidate. The entity remains structurally connected to the post-apply graph and must not be removed.

The two guardrails are independent. A candidate skipped by A is reported under reason code `sweep_skipped_external_write`. A candidate skipped by B is reported under `sweep_skipped_referenced`. A candidate skipped by both is reported under A (ownership is the stronger signal).

### Default Action

Swept entities are tombstoned via the service-layer delete path (`Entity.deleted_at`, with cascade to connected edges per the standard tombstone semantics). History rows are preserved. Edges attached to the swept entity that originated in this same batch are tombstoned in the cascade.

### Strict Mode

The importer must expose an optional `--sweep-strict` flag that changes when the sweep executes, not what it does. In strict mode, **any candidate that would fail either guardrail aborts the entire force re-import before any writes occur**.

**Invocation:**

- `--sweep-strict` is only meaningful alongside `--force-batches`. Passing it without force re-import is an invocation error.
- Orthogonal to `--purge` — the two flags combine cleanly. `--force-batches=<id> --sweep-strict --purge` means *"hard-delete the orphans, but only if I can do so cleanly."*
- Inherits the `DEBUG=True` invariant from `req-grid-import-grift-force-reimport`; no additional gate required.

**Execution:**

- Sweep candidates are computed and guardrails evaluated as usual.
- If **any** candidate fails Guardrail A or Guardrail B, the entire force re-import aborts. No node upserts, no edge upserts, no tombstones, no purges are written. The database state is unchanged.
- If all candidates pass both guardrails (or if there are no candidates), the force re-import proceeds exactly as it would have without `--sweep-strict`.
- The abort surfaces as a dedicated error code (e.g. `sweep_strict_aborted`) with a structured report of every candidate that would have been skipped and its reason.

**Rationale:**

Default sweep behavior (skip-with-report) favors completing the operation and surfacing the skips afterward. That's the right default for normal iteration. Strict mode inverts the tradeoff: when the operator expects a clean sweep ("this batch is fully mine, nothing external has touched it"), a silent partial success is worse than no change at all, because it leaves the grid in an ambiguous half-applied state. Strict mode refuses to create that state and forces the operator to resolve ownership or reference issues first.

### Reporting

The importer's force-reimport report must include:

- `swept_entities`: list of `{entity_id, entity_type, reason: "orphaned"}` objects for entities tombstoned
- `sweep_skipped`: list of `{entity_id, entity_type, reason}` objects for candidates that failed a guardrail, with reason codes from the guardrail text above
- `sweep_strict_aborted`: boolean; `true` if `--sweep-strict` was set and the run aborted due to skipped candidates. When `true`, `swept_entities` must be empty and `sweep_skipped` carries the full list of offending candidates.

### Non-Goals

- The sweep does not touch entities whose creation history is not owned by this batch. Dimensional authority, cross-plugin cleanup, and importer-declared ownership over a dimension are out of scope and tracked as a future concern (see *Future* below).
- The sweep does not re-tombstone already-tombstoned entities, and does not restore tombstoned entities.
- The sweep does not observe edge-only creation records. Edges created by this batch that point at entities owned by other batches stay put unless the edge itself is absent from the revised content; in that case the edge is an ordinary upsert-delete target and handled by batch-standard cascade behavior, not by the sweep.

### Future

Authoritative-importer semantics — "this importer owns dimension X; sweep anything present in X not in this import" — is a related but distinct concern. The common case (a recurring AWS pull that wants its absences honored as deletions) is expected to be solvable by using a stable `batch_entity.entity_id` per source and force re-importing on each pull: the batch-scoped sweep then naturally handles absences. If a use case emerges that cannot be expressed this way, a separate `req-grid-import-grift-authoritative` extension can land.

## Sweep Purge
----
RID: `req-grid-import-grift-sweep-purge`
Status: `Proposed`

An optional escalation of `req-grid-import-grift-batch-scoped-sweep` that replaces tombstone with hard-delete for swept entities. Intended for rapid development iteration where accumulated tombstones from ephemeral grift-file edits would obscure rather than document the grid's durable state.

### Invocation

- The command line or programmatic API must accept a `--purge` flag alongside `--force-batches`. `--purge` without `--force-batches` is an invocation error.
- `--purge` applies to the entire force re-import invocation. There is no per-batch toggle; the operator decides purge-or-tombstone at the command level and it applies to every swept entity in the run.

### Environment Gate

**Invariant:** `--purge` is permitted if and only if Django's `DEBUG` setting is `True` at the moment of invocation. This is the same binding invariant as `req-grid-import-grift-force-reimport`'s environment gate, applied independently here so there is no ambiguity when reading this requirement in isolation. There is no alternate flag, override, settings key, environment variable, or command-line argument that enables `--purge` in any other configuration.

- When `DEBUG` is `False`, passing `--purge` must surface a dedicated error code (e.g. `sweep_purge_refused_production`) distinct from other refusal or invocation errors.
- The grid invariant that "history is preserved" is protected by this gate. `--purge` is the single exception to that invariant and is bounded by this requirement alone; no other requirement may delegate hard-delete behavior to this one without its own explicit gate.
- Future proposals to relax this gate must land as explicit, named requirements. This requirement does not anticipate such cases.

### Guardrails

The purge uses **exactly the same guardrails** as the default sweep (Ownership and Referential Integrity) and **exactly the same strict-mode semantics** if `--sweep-strict` is also set. Purge does not relax or bypass either guardrail, and does not alter strict-mode's abort behavior. A candidate that fails a guardrail is skipped in both modes with the same reason code; if `--sweep-strict` and `--purge` are both set and any candidate fails, the entire run aborts before any writes.

### Hard-Delete Action

For each swept candidate, when `--purge` is set:

- The entity row is hard-deleted from the database (not tombstoned).
- Historical records for this entity with `batch_id == <the force-reimported batch>` are hard-deleted. These records are bounded to this batch's lifecycle by Guardrail A.
- Historical records for this entity with `batch_id != <this batch>` must not exist per Guardrail A. If any are found during execution (a spec-bug case), the purge must abort with a loud error rather than deleting them.
- Edges owned by this same batch that were connected to the swept entity are cascade-hard-deleted along with their `batch_id == <this batch>` history rows.
- Edges owned by other batches would have triggered Guardrail B, so the candidate would have been skipped. If one is found during execution (a spec-bug case), the purge must abort with a loud error.

### Audit Trail

- The `BatchEvent` of type `FORCE_REIMPORT` records `purge: true` and lists the `purged_entities: [entity_id, ...]` ids.
- The entities themselves are gone from the DB after purge, so the BatchEvent is the only remaining record that they existed. This is accepted for the narrow use case and cannot be expanded without re-specifying.
- A batch whose purge has executed is still the same batch entity. The batch row and its event history persist; only its ephemeral content is removed.

### Reporting

The importer's force-reimport report must include:

- `purged_entities`: list of `{entity_id, entity_type}` objects for entities hard-deleted (empty when `--purge` is not set)

### Non-Goals

- `--purge` does not enable deletion of entities created by other batches. Guardrail A still applies.
- `--purge` does not purge batch metadata or other batches' records. Scope is strictly the sweep's output for this invocation.
- `--purge` is not a general-purpose hard-delete tool. Any other hard-delete use case must be proposed as a separate requirement with its own gating.

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
- if the incoming batch already carries `description_json` with a format other than `tap.grift.import.v0`, the importer preserves the caller's `format` string verbatim at the top level and nests importer metadata under the reserved key `data._tap_grift_import` to avoid collision with caller-owned data keys
- if the imported batch metadata already uses `format == "tap.grift.import.v0"`, the importer may overwrite that format block with the new local import metadata rather than nesting ambiguous duplicate copies
- if the incoming batch carries no `description_json`, has an empty one, or has a malformed shape, the importer emits `{"format": "tap.grift.import.v0", "data": <importer metadata>}`
- the reserved key `_tap_grift_import` inside `description_json.data` is owned by the importer; callers must not use it for their own content
- source batch timestamps from the GRIFT payload must be preserved in importer metadata rather than treated as the local batch creation timestamps
- local batch lifecycle timestamps remain local infrastructure timestamps owned by the importing grid
- when present in the GRIFT batch payload or batch envelope, source batch timestamps must be copied into the importer metadata block (either flat at `description_json.data` when the importer owns the whole block, or nested at `description_json.data._tap_grift_import` when preserving a caller format) under source-prefixed keys
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
