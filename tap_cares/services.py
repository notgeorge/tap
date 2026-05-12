"""tap_cares orchestration services.

`enqueue_collection` is the public entrypoint for starting a collector run. It
creates the on-grid CollectionJob, links it to the Collector via HAS_JOB, then
enqueues the Django Task that will execute the registered collector class.

Per req-tap-cares-collector-job-lifecycle-3, collector module classes never
mutate the CollectionJob — the orchestration service and the task do.
"""

from __future__ import annotations

from datetime import UTC, datetime

from tap_cares.models import CollectionJob, CollectionJobStatus, Collector
from tap_cares.tasks import run_collector
from tap_grid.caller_context import CallerContext
from tap_grid.services import create_edge


def enqueue_collection(
    collector: Collector,
    *,
    caller_context: CallerContext | None = None,
) -> CollectionJob:
    """Create a CollectionJob for `collector`, link it via HAS_JOB, and enqueue execution.

    Returns the CollectionJob in its post-enqueue state. With the immediate
    task backend (v0 default) the job will already reflect the final task
    outcome by the time this returns; with a worker backend, the job will be
    RUNNING (or still READY if the worker hasn't picked it up).
    """
    ctx = caller_context or CallerContext()

    job = CollectionJob.objects.create(
        name=f"{collector.name or 'Collection'} {datetime.now(UTC).isoformat()}",
        status=CollectionJobStatus.READY,
        enqueued_at=datetime.now(UTC),
    )

    create_edge(
        from_entity=collector.entity,
        to_entity=job.entity,
        edge_type="HAS_JOB",
        caller_context=ctx,
    )

    result = run_collector.enqueue(
        str(collector.entity_id),
        str(job.entity_id),
    )

    job.refresh_from_db()
    if not job.task_result_id and result is not None:
        job.task_result_id = result.id
        job.save(update_fields=["task_result_id"])

    return job
