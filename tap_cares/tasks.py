"""Django Tasks runtime for tap_cares collectors.

req-tap-cares-collector-task-execution (spec-tap-cares-collector.md).

A single task — `run_collector` — receives the JSON-safe identifiers of the
Collector node and the CollectionJob node, looks up the registered collector
class, builds a CollectorConfig, instantiates the class, and invokes its
run() method. The task owns CollectionJob lifecycle updates
(req-tap-cares-collector-job-lifecycle-2,3,4); the collector class never
touches the job directly.
"""

from __future__ import annotations

from datetime import UTC, datetime

from django.tasks import TaskContext, task

from tap_cares.collectors.config import CollectorConfig
from tap_cares.models import CollectionJob, CollectionJobStatus, Collector
from tap_cares.registry import get_collector

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
    job = CollectionJob.objects.get(entity_id=collection_job_entity_id)

    now = datetime.now(UTC)
    job.status = CollectionJobStatus.RUNNING
    job.started_at = now
    fields_to_save = ["status", "started_at"]
    if not job.task_result_id and context.task_result is not None:
        job.task_result_id = context.task_result.id
        fields_to_save.append("task_result_id")
    job.save(update_fields=fields_to_save)

    try:
        collector = Collector.objects.get(entity_id=collector_entity_id)
        cls = get_collector(collector.collector_registry)
        config = CollectorConfig(
            collector_entity_id=collector.entity_id,
            collection_job_entity_id=job.entity_id,
        )
        instance = cls(config)
        # The collector may update its own job (e.g. via submit_collector_grift
        # writing grift_batches). We only own lifecycle fields, so the final
        # save below uses update_fields to avoid clobbering collector-owned
        # state.
        instance.run()
    except Exception as exc:
        job.status = CollectionJobStatus.FAILED
        job.error_summary = _safe_error_summary(exc)
        job.finished_at = datetime.now(UTC)
        job.save(update_fields=["status", "error_summary", "finished_at"])
        raise
    else:
        job.status = CollectionJobStatus.SUCCESSFUL
        job.finished_at = datetime.now(UTC)
        job.save(update_fields=["status", "finished_at"])
