# TAP FLIP Design

## Purpose

FLIP (Field Level Information Provenance) defines how TAP tracks:

1. Object history.
2. Batch/update lineage.
3. Agreement (consensus) over competing assertions.

This document is the implementation reference for initial build-out. The goal is
to avoid ad hoc code decisions and keep architecture stable while we iterate.

## Guiding Principles

1. Make it work, make it right, make it fast.
2. Prefer proven components first, replace only with clear evidence.
3. Keep provenance data append-only where possible.
4. Separate concerns: history, batch lineage, and agreement are distinct layers.
5. Keep model-level behavior explicit via configuration, not hidden conventions.

## Scope: Initial Build

### In Scope Now

1. Base object history using `django-simple-history`.
2. Batch/update tracking with append-only records and user attribution.
3. A model configuration shape that controls:
   - history behavior,
   - batch support,
   - consensus enablement flag (placeholder only for now).

### Out of Scope Now

1. Building a custom replacement for `django-simple-history`.
2. Full field-level provenance graph for every column/value.
3. Final consensus/coordination algorithm implementation.
4. Performance tuning beyond basic correctness.

## Key Decision: History Backend

Use `django-simple-history` as the initial history backend.

Rationale:

1. Fastest path to reliable audit/version tracking.
2. Lower implementation and correctness risk than custom history storage.
3. Lets FLIP focus early effort on batch lineage and provenance interfaces.

Switch away from `django-simple-history` only when we have concrete blockers
(throughput, query shape, compliance guarantees, etc.).

## Architecture (First Pass)

### 1) History Layer

`django-simple-history` provides per-model historical snapshots.

Responsibilities:

1. Track create/update/delete snapshots.
2. Record actor where available (`history_user`).
3. Expose model timeline and diffs for audit and debugging.

Implementation notes:

1. Integrate through a small FLIP history service/adapter, not direct calls
   throughout business code.
2. Keep future backend swap possible behind this adapter.
3. Treat history retention depth as policy configured by FLIP (cleanup jobs can
   enforce it, since per-model depth is not native in simple-history config).

### 2) Batch/Update Layer

Add FLIP-native append-only batch lineage.

Responsibilities:

1. Identify ingestion/update batches (`batch_id`).
2. Associate each change event to:
   - batch,
   - actor (user or service principal),
   - source metadata (scanner/log/connector/etc.),
   - timestamps,
   - affected object types which can be used for quick lookups of all changed components later.
3. Preserve immutable event log for replay and audit.
4. Batch applies to all updates, including singleton events - which are a batch of one.

Data model direction (initial):

1. `Batch`: one logical operation group (ingest or update run).
2. `BatchEvent`: append-only change/provenance events belonging to a batch.
3. Optional reference fields from domain objects to latest/applied batch where
   useful for query convenience (without replacing event log truth).
4. `Batch` and `BatchEvent` are Entityies and follows the same rules as all entities re entity ID, registration in modules table, Entity spine
5.  Update BaseModel with the necessary column for batch_id to associate the most recent change with which batch it was included in.

### 3) Agreement Layer (Placeholder)

Agreement will be edge-based and may produce an "emerged view" per object.

Status: placeholder only in this phase.

Do now:

1. Reserve config shape and extension points.
2. Ensure history and batch artifacts can later be represented as graph nodes.
3. Avoid schema choices that block edge-based agreement.

Do not implement now:

1. Policy engine.
2. Conflict resolution algorithm.
3. Final emerged-view materialization strategy.

## Model Configuration Standard

Every FLIP-capable model should expose an explicit configuration block, merged
with base defaults from `BaseModel`.

Example shape:

```python
FLIP_CONFIG = {
    "history": {
        "enabled": True,
        "depth_revisions": None,
        "depth_days": None,
    },
    "batch": {
        "enabled": True,
    },
    "consensus": {
        "enabled": False,
        "policy": None,
    },
}
```

Why explicit `enabled` flags:

1. Removes ambiguity between "unset" and "disabled".
2. Supports safe base defaults and explicit per-model overrides.
3. Simplifies runtime gating logic.
4. Improves auditability of intent.

## Initial Milestones

1. Add FLIP config defaults + per-model override pattern on base/domain models.
2. Integrate `django-simple-history` in selected models and verify audit flows.
3. Introduce `Batch` and `BatchEvent` append-only tables with user attribution.
4. Wire batch context through service-layer write paths.
5. Add tests for:
   - history row creation,
   - batch/event append behavior,
   - user attribution,
   - config gating (`enabled` semantics).
6. Document retention job approach for history depth policies.

## Open Questions (Track Here)

1. Service principal representation: extend user model or dedicated actor model?
2. Canonical event taxonomy for `BatchEvent` types?
3. Required source metadata schema (free-form JSON vs constrained fields)?
4. How and when to map history/batch records into explicit graph nodes?

## Agreement Placeholder (Detailed Spec Pending)

TBD: final agreement protocol and policy schema.

Expected direction:

1. Edge-centric representation of assertions and supporting evidence.
2. Object-level or project-level policy selection.
3. Initial policy likely weighted-source precedence.
4. Produced output should support "emerged view" per object.

## App Boundaries

1. `tap_core`: Entity, Edge, BaseModel, core graph structure.
2. `tap_flip`: FLIP configuration, history integration, batch lineage, future agreement.
3. `tap_plugins`: domain models extending `BaseModel`.
4. `tap_api`: API surface exposing FLIP capabilities.
