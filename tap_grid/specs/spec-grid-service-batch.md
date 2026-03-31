# Grid Service Batch Specification

## Philosophy

Batching is the write execution model for the TAP service layer. Treating all writes, including single-object writes, as batch-backed operations keeps provenance and execution semantics consistent while allowing dry-run, per-item diagnostics, and transactional all-or-nothing behavior.

Batch records should also be legible as first-class change events. They need enough human-readable and machine-readable metadata to explain what a batch represents, why it happened, and how it can be related back to upstream systems such as source control, scanners, import jobs, and other structured change producers.

## Goals

|    |                  |                                                                                 |
| :---: | ---           | ---                                                                             |
| 1. | Unified           | All writes participate in the same batch semantics                              |
| 2. | Transactional     | Multi-operation writes can be validated and committed consistently              |
| 3. | Inspectable       | Dry-run and per-item diagnostics support humans and bots before commit          |


## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-grid-service-batch-all | [All Writes Are Batch-Backed](#all-writes-are-batch-backed) | Implemented | Single and multi-object writes share batch semantics |
| req-grid-service-batch-metadata | [Batch Metadata Fields](#batch-metadata-fields) | Implemented | Human-readable and machine-readable batch metadata |
| req-grid-service-batch-infra | [Batch ID As Infrastructure](#batch-id-as-infrastructure) | Implemented | CallerContext introduced; batch_id threading via ContextVar implemented |
| req-grid-service-batch-signals | [Signal Elimination](#signal-elimination) | Implemented | tap_flip/batch/signals.py deleted; provenance in BaseModel.save() |
| req-grid-service-batch-dryrun | [Dry-Run Behavior](#dry-run-behavior) | Implemented | Full validation without persistence |
| req-grid-service-batch-diag | [Per-Item Diagnostics](#per-item-diagnostics) | Implemented | Batch partial diagnostics and reporting |
| req-grid-service-batch-tx | [Transactional Commit Behavior](#transactional-commit-behavior) | Implemented | All-or-nothing commit model |


### All Writes Are Batch-Backed
----
RID: `req-grid-service-batch-all`
Status: `Implemented`

Every service-layer write participates in batch semantics, including single-object writes.

#### Status Details
This requirement captures the decision to use one consistent batch model rather than a split system for “simple writes” versus “real batches.”

#### Implementation
Single-object writes are represented as one-operation batches. Multi-object write flows are represented as multi-operation batches. If TAP later needs to distinguish batch kinds, that can be modeled as a batch property rather than a separate write system.

**Exemption:** Batch ID creation itself is an infrastructure-level operation and is explicitly exempt from this requirement. The service layer creates a batch_id before executing writes; that creation does not recursively require its own batch context. See `req-grid-service-batch-infra`.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-batch-all-1 | Single Writes Use Batch Semantics | Implemented | Single-object writes are treated as batch-backed operations. | |
| req-grid-service-batch-all-2 | Multi Writes Use Same Batch Model | Implemented | Multi-object writes use the same batch abstraction rather than a separate execution system. | |
| req-grid-service-batch-all-3 | Batch Creation Is Exempt | Implemented | The infrastructure operation of creating a batch_id is explicitly exempt from the batch-backed requirement. | |

#### Future
Add batch-type metadata if later operational needs require distinguishing import, user edit, sync, or admin-driven batch categories.


### Batch Metadata Fields
----
RID: `req-grid-service-batch-metadata`
Status: `Implemented`

Batch records should carry a small, explicit metadata surface that supports both human understanding and machine-usable correlation.

#### Status Details
This requirement introduces richer batch metadata beyond batch identity alone. It is intended to make batches useful as contextual change records for humans, bots, and future search/reporting surfaces.

#### Implementation
A batch should support these metadata fields:

- `title`: required short human-readable summary of what the batch represents
- `description`: optional longer free-form human-readable description
- `description_json`: optional structured metadata object supplied by the batch creator

`title` should be stored as a standard short text field such as a `CharField`.

`description` should be stored as a free-form text field.

`description_json` should be constrained to this fixed top-level shape:

```json
{
  "format": "git",
  "data": {
    "commit": "abc123"
  }
}
```

Rules for `description_json`:

- top-level value must be an object
- top-level keys are fixed to `format` and `data`
- `format` is a required non-empty string describing the payload format
- `data` is a required object
- `additionalProperties` is false at the top level
- callers may add arbitrary format-specific fields inside `data`

`description_json` is caller-supplied metadata. TAP does not impose a canonical domain schema beyond the fixed top-level wrapper and object-only requirements.

This structure gives TAP a stable discriminator for parsing, rendering, search, and downstream automation without forcing all callers into one shared domain-specific schema.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-batch-metadata-1 | Title Required | Implemented | Each batch stores a required human-readable `title`. | Intended for humans and AI context. |
| req-grid-service-batch-metadata-2 | Description Optional | Implemented | Each batch may store an optional longer-form `description`. | |
| req-grid-service-batch-metadata-3 | Description JSON Optional | Implemented | Each batch may store optional structured `description_json` metadata. | |
| req-grid-service-batch-metadata-4 | Fixed Top-Level JSON Shape | Implemented | `description_json`, when present, must be an object with exactly `format` and `data` keys. | No additional top-level keys. |
| req-grid-service-batch-metadata-5 | Data Object Only | Implemented | `description_json.data` must itself be an object. | |
| req-grid-service-batch-metadata-6 | Format String Required | Implemented | `description_json.format` must be a non-empty string describing the metadata format. | |

#### Future
Define whether TAP should publish a registry of known batch metadata formats and whether specific formats should get richer search/rendering helpers.


### Batch ID As Infrastructure
----
RID: `req-grid-service-batch-infra`
Status: `Implemented`

The service layer is responsible for generating a batch_id at the start of every write operation and threading it downstream to models. Models consume the batch_id; they do not create it.

#### Status Details
This requirement formalises the boundary between the service layer's orchestration responsibility and the model's provenance responsibility. It replaces the previous approach where batch context was managed via a thread-local context manager in `tap_flip`.

#### Implementation
At the start of every write pipeline execution the service layer:

1. Checks CallerContext for an existing batch_id (for callers that have pre-established a batch scope).
2. If none is present, generates a new UUIDv7 as the batch_id for this operation.
3. Places the batch_id in the CallerContext that flows through the rest of the pipeline.

Models receive batch_id through CallerContext and use it to update `flip_map` and any other provenance fields during `save()`. Models do not call out to a batch service to register or track the batch; they only record the identifier they were given.

Batch_id creation does not require persisting a Batch entity before writes can proceed. Any Batch audit entity is an optional append-only artifact that may be written after the primary write completes, not a prerequisite for it.

The previous `batch_context()` context manager in `tap_flip.batch.service` is superseded by this mechanism and should be removed during the FLIP simplification pass.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-batch-infra-1 | Service Layer Generates Batch ID | Implemented | The service layer generates a batch_id at the start of each write pipeline execution if none is present in CallerContext. | |
| req-grid-service-batch-infra-2 | Batch ID Flows Via Context | Implemented | batch_id reaches models through CallerContext rather than a thread-local or separate context manager. | |
| req-grid-service-batch-infra-3 | Models Consume Not Create | Implemented | Models use the batch_id provided to them; they do not initiate batch creation. | |
| req-grid-service-batch-infra-4 | No Batch Entity Prerequisite | Implemented | A Batch audit entity is not required to exist before writes can proceed; it is an optional post-write artifact. | |

#### Future
Define whether Batch audit entities are written synchronously after each pipeline execution or asynchronously, and what their retention policy is.


### Signal Elimination
----
RID: `req-grid-service-batch-signals`
Status: `Implemented`

Signal-based batch event recording is eliminated. Provenance is recorded directly in `BaseModel.save()` using the batch_id from CallerContext.

#### Status Details
The previous implementation used Django signals (`tap_flip.batch.signals`) to intercept model saves and record `BatchEvent` records. This approach is being replaced because:

- Signals fire outside the service layer pipeline, making them invisible to dry-run, authz, and other pipeline stages.
- Signal ordering is fragile and difficult to test in isolation.
- The service layer's batch_id threading model makes signals unnecessary.

#### Implementation
`BaseModel.save()` consumes the batch_id from the active CallerContext directly and updates `flip_map`. No signal handlers are needed for this path.

The existing signal registration in `tap_flip.batch.signals` should be removed during the FLIP simplification pass. Any `BatchEvent` append behavior that needs to survive should be moved into a method called explicitly within `BaseModel.save()` or the service layer pipeline step 10 (provenance recording).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-batch-signals-1 | No Signal-Based Batch Recording | Implemented | Batch provenance recording does not rely on Django post-save signals. | |
| req-grid-service-batch-signals-2 | Provenance In Save | Implemented | `BaseModel.save()` handles flip_map updates using batch_id from CallerContext. | |
| req-grid-service-batch-signals-3 | Legacy Signals Removed | Implemented | `tap_flip.batch.signals` signal handlers are removed during the FLIP simplification pass. | |

#### Future
Evaluate whether any observability events (not provenance) benefit from a lightweight signal or hook after the primary write pipeline stabilises.


### Dry-Run Behavior
----
RID: `req-grid-service-batch-dryrun`
Status: `Implemented`

The batch system should support dry-run execution for both single-object and multi-object writes.

#### Status Details
This requirement reflects the preferred development and operational workflow for safe validation-first execution.

#### Implementation
Dry-run mode:

- runs the full validation stack
- produces per-item diagnostics
- does not persist changes
- does not commit the transaction

Dry-run is a request-time flag, not a separate API family.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-batch-dryrun-1 | Dry Run Available For All Writes | Implemented | Dry-run mode is available for single-object and multi-object write execution. | |
| req-grid-service-batch-dryrun-2 | Full Validation In Dry Run | Implemented | Dry-run mode executes the same validation stack as a real write. | |
| req-grid-service-batch-dryrun-3 | No Persistence In Dry Run | Implemented | Dry-run mode performs no durable writes. | |

#### Future
Clarify whether dry-run should record ephemeral observability events once the instrumentation story is designed.


### Per-Item Diagnostics
----
RID: `req-grid-service-batch-diag`
Status: `Implemented`

Batch execution should return structured per-item diagnostics so callers can understand which requested operations would fail and why.

#### Status Details
This requirement defines “batch partial diagnostics” even when commit behavior remains all-or-nothing.

#### Implementation
Per-item diagnostics should support, at minimum:

- requested operation
- target object/type
- status
- stable error code when failed
- safe human-readable message
- machine-usable detail payload
- correlation/debug reference where applicable

These diagnostics are especially important for dry-run flows but also useful for failed committed batches.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-batch-diag-1 | Operation Identified Per Item | Implemented | Batch diagnostics identify the requested operation for each item. | `WriteResult.operation` |
| req-grid-service-batch-diag-2 | Safe Message And Stable Code | Implemented | Failed item diagnostics include a safe message and stable error code. | |
| req-grid-service-batch-diag-3 | Machine Detail Payload | Implemented | Diagnostics include structured machine-usable detail payloads for automation and tooling. | |

#### Future
Define how verbose result mode enriches per-item diagnostics with deeper references for admin and bot workflows.


### Transactional Commit Behavior
----
RID: `req-grid-service-batch-tx`
Status: `Implemented`

Committed batch writes should use all-or-nothing transaction semantics.

#### Status Details
This requirement captures the current intended commit model.

#### Implementation
If a committed batch fails validation or persistence for any operation, the batch does not partially commit graph changes. Dry-run diagnostics may still report which operations would have failed, but real commit behavior remains transactional.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-service-batch-tx-1 | All Or Nothing Commit | Implemented | A committed batch either fully succeeds or fully rolls back. | |
| req-grid-service-batch-tx-2 | Diagnostics Survive Failure | Implemented | Failed committed batches still return structured diagnostics explaining the failure set. | |

#### Future
Revisit partial commit models only if a concrete operational need emerges; they are not part of the v1 batch contract.


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
