"""Django Tasks runtime for tap_cares collectors.

req-tap-cares-collector-task-execution, req-tap-cares-collector-job-sole-writer,
req-tap-cares-collector-failure-mode (spec-tap-cares-collector.md).

A single task — `run_collector` — receives the JSON-safe identifiers of the
Collector node and the CollectionJob node, looks up the registered collector
class, builds a CollectorConfig, instantiates the class, invokes its run()
method, and writes the terminal state to the CollectionJob in a single patch.

The task body is the sole writer to CollectionJob after row creation. Three
writes per run total:
  - run_collection writes the row at READY (kickoff)
  - this task body writes RUNNING + started_at + task_result_id (task start)
  - this task body writes the terminal SUCCESSFUL or FAILED state + finished_at
    + error_summary + results + grift_batches (task end)

The collector instance accumulates `self.results`, `self.grift_batches`, and
`self.error_summary` in memory during run(); the task body reads them at
terminal state and persists them in the terminal patch.
"""

from __future__ import annotations

from datetime import UTC, datetime

from django.tasks import TaskContext, task

from tap_cares.collectors.config import CollectorConfig
from tap_cares.models import CollectionJob, CollectionJobStatus, Collector
from tap_cares.registry import get_collector
from tap_grid.services import _patch_node_internal

_ERROR_SUMMARY_CAP = 2048


def _safe_error_summary(exc: BaseException) -> str:
    msg = f"{type(exc).__name__}: {exc}"
    if len(msg) > _ERROR_SUMMARY_CAP:
        msg = msg[:_ERROR_SUMMARY_CAP]
    return msg


@task(takes_context=True)
def run_collector(
    context: TaskContext,
    collector_entity_id: str,
    collection_job_entity_id: str,
) -> None:
    """Execute one collector run.

    Args:
        context: Django Tasks context — `context.task_result.id` is the
            backend-defined string identifier persisted on
            `CollectionJob.task_result_id`.
        collector_entity_id: UUIDv7 of the Collector node (as string).
        collection_job_entity_id: UUIDv7 of the CollectionJob node (as string).
    """
    # Task start: RUNNING transition. One patch carries status, started_at,
    # and (if available) task_result_id. No long-lived job instance is held
    # across collector.run() — each patch is a fresh service-layer round trip.
    now = datetime.now(UTC)
    start_payload: dict[str, str] = {
        "status": CollectionJobStatus.RUNNING.value,
        "started_at": now.isoformat(),
    }
    if context.task_result is not None:
        start_payload["task_result_id"] = context.task_result.id

    _patch_node_internal(collection_job_entity_id, start_payload)

    # The instance reference is bound inside the try so that even pre-run()
    # failures (collector resolution, instantiation) flow through the same
    # FAILED terminal-patch path. accumulator state is then read off the
    # instance if it exists, or filled with empty defaults otherwise.
    instance = None
    try:
        # Resolve the collector class and instantiate. The instance owns its
        # own accumulator state (self.results, self.grift_batches, self.error_summary).
        collector = Collector.objects.get(entity_id=collector_entity_id)
        cls = get_collector(collector.collector_registry)
        config = CollectorConfig(
            collector_entity_id=collector.entity_id,
            collection_job_entity_id=collection_job_entity_id,
        )
        instance = cls(config)
        # Run the collector. It accumulates results/grift_batches/error_summary
        # on itself; nothing it does touches the CollectionJob row.
        instance.run()
    except Exception as exc:
        # Terminal write: FAILED. One patch carries the full accumulator. If
        # the collector set self.error_summary, that wins; otherwise derive a
        # one-liner from the exception itself. If the instance never got
        # constructed (resolution / registry / instantiation failure), use
        # empty defaults for the accumulators.
        if instance is not None:
            error_summary = instance.error_summary or _safe_error_summary(exc)
            results = instance.results
            grift_batches = instance.grift_batches
        else:
            error_summary = _safe_error_summary(exc)
            results = {"info": [], "warn": [], "error": []}
            grift_batches = {"imported": [], "skipped": []}
        _patch_node_internal(
            collection_job_entity_id,
            {
                "status": CollectionJobStatus.FAILED.value,
                "finished_at": datetime.now(UTC).isoformat(),
                "error_summary": error_summary,
                "results": results,
                "grift_batches": grift_batches,
            },
        )
        # Re-raise so Django Tasks' own failure machinery sees the failure
        # (req-tap-cares-collector-failure-mode-5).
        raise

    # Terminal write: SUCCESSFUL. One patch carries the full accumulator.
    _patch_node_internal(
        collection_job_entity_id,
        {
            "status": CollectionJobStatus.SUCCESSFUL.value,
            "finished_at": datetime.now(UTC).isoformat(),
            "results": instance.results,
            "grift_batches": instance.grift_batches,
        },
    )
