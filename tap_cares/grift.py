"""GRIFT import surface for collector results.

req-tap-cares-collector-grift-import (spec-tap-cares-collector.md).

`submit_collector_grift(job, document)` is the approved path for collector
modules to push collected results into the grid. It wraps `grift_import()`
and records the resulting batch entity IDs on the CollectionJob so the run
can be correlated with the batches it produced.

Collector modules must not bypass this helper and call `write_batch()`,
node/edge write helpers, or direct ORM saves to mutate TAP-managed graph
state (req-tap-cares-collector-read-boundary-1).
"""

from __future__ import annotations

from typing import Any

from tap_cares.models import CollectionJob
from tap_grid.grift import GriftImportResult, grift_import


def submit_collector_grift(
    job: CollectionJob,
    document: dict[str, Any] | str | bytes,
    *,
    actor: Any = None,
    dangling_edge_mode: str = "strict",
) -> GriftImportResult:
    """Import a GRIFT document as a collector result and correlate to the job.

    The import runs through `tap_grid.grift.grift_import` — the standard
    GRIFT importer with all its validation, idempotency, and service-layer
    write semantics. The resulting batch entity IDs (imported + skipped) are
    stored on `job.grift_batches` so the CollectionJob can be linked back to
    the batches it produced.

    Args:
        job: The CollectionJob node owning this submission.
        document: GRIFT document (parsed dict, JSON string, or bytes).
        actor: Optional User passed through to `grift_import`.
        dangling_edge_mode: Passed through to `grift_import`.

    Returns:
        The raw GriftImportResult; callers may inspect counts / errors /
        warnings without going through `job.grift_batches`.
    """
    result = grift_import(
        document,
        dangling_edge_mode=dangling_edge_mode,  # type: ignore[arg-type]
        actor=actor,
    )

    imported_ids = [b.batch_entity_id for b in result.imported_batches]
    skipped_ids = [b.batch_entity_id for b in result.skipped_batches]

    existing = job.grift_batches or {}
    merged_imported = list(existing.get("imported", [])) + imported_ids
    merged_skipped = list(existing.get("skipped", [])) + skipped_ids
    job.grift_batches = {
        "imported": merged_imported,
        "skipped": merged_skipped,
    }
    job.save(update_fields=["grift_batches"])

    return result
