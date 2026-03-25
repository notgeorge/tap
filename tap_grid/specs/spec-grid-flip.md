# Grid FLIP Specification

## Philosophy

FLIP (Field-Level Information Provenance) explains the auditable sources of the current canonical data on a TAP object. FLIP is intentionally scoped to present state: it tells us which batch is responsible for the current value of each tracked field path. If a caller wants to know how that provenance changed over time, they must consult history.

## Goals

|    |              |                                                                                         |
| :---: | ---       | ---                                                                                     |
| 1. | Current      | FLIP explains provenance for the currently stored canonical values                       |
| 2. | Simple       | FLIP remains lightweight enough to update in normal write paths                          |
| 3. | Immutable    | FLIP points at immutable batch records rather than mutable provenance blobs              |
| 4. | Independent  | FLIP does not require history reconstruction and does not depend on perspective storage   |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-grid-flip-map | [FLIP Field-Path Map](#flip-field-path-map) | Implemented | Canonical objects store a field-path-to-batch mapping for current values |
| req-grid-flip-batch | [FLIP Batch Anchoring](#flip-batch-anchoring) | Implemented | FLIP points to immutable batch ids rather than duplicating source metadata |
| req-grid-flip-scope | [FLIP Scope and Field Selection](#flip-scope-and-field-selection) | Implemented | Models and edge types choose which field paths participate in FLIP |
| req-grid-flip-separation | [FLIP and History Separation](#flip-and-history-separation) | Implemented | FLIP answers present-state provenance only; historical provenance lives in history |

## Explanation

FLIP is a current-state provenance index attached to canonical objects. It should be fast to read, cheap to update during normal writes, and easy to explain: for any tracked field path on the current object, TAP can identify which batch last set that value. The batch then provides immutable audit context such as actor, source, metadata, and timing.

This deliberately does not make FLIP a full provenance ledger. The ledger already exists in batch records and history. FLIP is the shortcut that makes current provenance inexpensive and explicit.

### FLIP Field-Path Map
----
RID: `req-grid-flip-map`
Status: `Implemented`

Every FLIP-enabled canonical object stores a field-path map describing the batch responsible for each currently tracked field value.

#### Status Details
Implemented. `flip_map` JSONField on `BaseModel`; updated by `batch_context` writes. Viewer surfaces FLIP rows via `object_view` in `tap_web/views.py`.

#### Implementation
The FLIP payload should be a JSON object or equivalent keyed by field path:

```json
{
  "ip_address": "0195f5c6-2c6f-7f8d-a631-1d1d6e6f6d4a",
  "service.banner": "0195f5c6-2c6f-7f8d-a631-1d1d6e6f6d4a",
  "owner.team": "0195f5c7-3a14-7488-b3da-6b1f3d1c2ef9"
}
```

Rules:

1. Keys are field paths, not just top-level field names.
2. Values are batch ids for the batch that last set the current canonical value at that field path.
3. The FLIP map lives with the canonical object whose current values it describes.
4. Updating a tracked canonical field updates the corresponding FLIP entry.

#### Development
Using field paths instead of only top-level field names keeps the model viable if TAP tracks provenance inside structured fields. This is worth deciding up front because changing FLIP key shape later would be painful.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-flip-map-1 | Field Paths Not Just Field Names | Implemented | FLIP keys are stored as field paths so nested tracked values can be represented. | `flip_map` keys are dot-delimited field paths |
| req-grid-flip-map-2 | Current Value Mapping | Implemented | Every FLIP entry points to the batch responsible for the currently stored canonical value at that field path. | Values are batch UUIDs from `batch_context` |
| req-grid-flip-map-3 | Canonical Object Locality | Implemented | The FLIP map is stored on the canonical object it describes rather than in a detached side table for v1. | `flip_map` JSONField on `BaseModel` |

#### Future
If FLIP maps become large or need independent indexing, TAP may later split them into a dedicated table while preserving the same logical contract.

### FLIP Batch Anchoring
----
RID: `req-grid-flip-batch`
Status: `Implemented`

FLIP should anchor provenance to immutable batch records rather than duplicating actor, source, or timing metadata per field path.

#### Status Details
Implemented. `Batch` records in `tap_flip` are immutable once closed. FLIP map values are batch UUIDs; actor/source/timing are read from the batch at display time.

#### Implementation
The batch id referenced by FLIP is the immutable join point for provenance lookup. Batch records should supply:

1. Actor identity where available.
2. Source or tool metadata.
3. Operational timing such as batch start and close times.
4. Any additional immutable context needed for audit.

FLIP itself should not duplicate this metadata. Its job is only to identify the responsible batch for each tracked field path.

#### Development
This is a good layering boundary because batch is already designed as sub-grid immutable operational context. Reusing it avoids inventing a second provenance store that would drift from batch truth over time.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-flip-batch-1 | Batch Id As Provenance Pointer | Implemented | FLIP entries point to batch ids rather than embedding full actor/source metadata inline. | `flip_map` values are batch UUIDs |
| req-grid-flip-batch-2 | Immutable Join Target | Implemented | The batch referenced by FLIP is immutable and suitable for audit joins. | `Batch` records are closed and not mutated after write |
| req-grid-flip-batch-3 | Shared Batch Reuse | Implemented | Multiple field paths updated by the same operation may legitimately point to the same batch id. | All fields saved in one `batch_context` share the same batch UUID |

#### Future
If TAP later needs to attribute current fields to a finer-grained unit than a batch, it may introduce a batch-event pointer while preserving batch as the minimum required join target.

### FLIP Scope and Field Selection
----
RID: `req-grid-flip-scope`
Status: `Implemented`

FLIP must be selectively configurable so models and edge types can choose which field paths are tracked.

#### Status Details
Implemented. `FLIP_CONFIG` on `BaseModel` subclasses enables FLIP and declares tracked fields. `batch_context` writes only update `flip_map` for fields declared in `FLIP_CONFIG`.

#### Implementation
FLIP policy should allow each model or edge type to define:

1. Whether FLIP is enabled.
2. Which field paths are tracked.
3. Whether the whole object is tracked by default or only an explicit allow-list.
4. How structured fields are addressed by field path.

FLIP enablement must be independent from history and perspective. A model may choose any combination that makes sense for its data.

#### Development
Selective tracking matters because not every field needs current provenance. Keeping this configurable makes FLIP practical while leaving room for future per-plugin nuance.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-flip-scope-1 | Explicit Enablement | Implemented | FLIP can be enabled or disabled per model or edge type. | `FLIP_CONFIG = {"enabled": True}` on `BaseModel` subclasses |
| req-grid-flip-scope-2 | Field Selection Policy | Implemented | FLIP policy can specify which field paths participate in the FLIP map. | `FLIP_CONFIG["fields"]` declares tracked field paths |
| req-grid-flip-scope-3 | Independent Customization | Implemented | FLIP field selection may differ from history and perspective settings for the same model type. | `FLIP_CONFIG` is independent of any history or perspective config |

#### Future
Future work may add wildcard field-path patterns or schema-derived defaults once the first explicit policy model is proven.

### FLIP and History Separation
----
RID: `req-grid-flip-separation`
Status: `Implemented`

FLIP answers current provenance only. Historical provenance analysis belongs to the history layer.

#### Status Details
Implemented. FLIP map stores only the most recent batch per field path; no history replay is required to read current provenance. History system is tracked separately in `spec-grid-history-DRAFT.md`.

#### Implementation
The required semantics are:

1. FLIP always describes the current canonical object state.
2. A FLIP read must not require replaying or scanning object history.
3. If a caller wants to know prior provenance states, they must consult history.
4. History may explain how FLIP changed over time, but FLIP does not implement that behavior itself.

#### Development
This separation keeps FLIP useful and cheap. It also preserves the option to change history backend later without redefining what FLIP means.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-grid-flip-separation-1 | Current-State Only | Implemented | FLIP reads describe provenance for the current canonical values only. | `flip_map` is overwritten on each save; not a log |
| req-grid-flip-separation-2 | No History Replay Required | Implemented | TAP can answer FLIP queries without reconstructing provenance from object history. | `flip_map` is directly readable; no scan required |
| req-grid-flip-separation-3 | Historical Provenance Delegates To History | Implemented | Requests for provenance-over-time are explicitly served by history, not by FLIP itself. | History system is a separate deferred concern |

#### Future
If TAP later exposes "FLIP as of time X", that feature should be implemented as a composition of history and FLIP semantics rather than by expanding FLIP into its own historical ledger.
