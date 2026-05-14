"""tap_cares orchestration services.

`run_collection` is the public entry point for starting a collector run. It
creates the on-grid CollectionJob via `_create_node_internal` (CollectionJob
is INTERNAL_ONLY), links it to the Collector via HAS_JOB through the standard
service-layer `create_edge`, then enqueues the Django Task that will execute
the registered collector class.

Per `req-tap-cares-collector-job-sole-writer`, the task body owns all
post-creation writes to CollectionJob — `run_collection` does not write to the
row again after handing off to `.enqueue()`.

Spec: req-tap-cares-collector-run-collection (spec-tap-cares-collector.md).
"""

from __future__ import annotations

from datetime import UTC, datetime

from tap_cares.models import CollectionJob, CollectionJobStatus, Collector
from tap_cares.tasks import run_collector
from tap_grid.caller_context import CallerContext
from tap_grid.services import _create_node_internal, create_edge


def run_collection(
    collector: Collector,
    *,
    caller_context: CallerContext | None = None,
    manual_run: bool = False,
    manual_run_source: str = "",
) -> CollectionJob:
    """Start a collection run for the given Collector.

    Performs, in order:
      1. Creates a CollectionJob node via `_create_node_internal`
         (CollectionJob is INTERNAL_ONLY), persisting `manual_run` and
         `manual_run_source` on the row (req-tap-cares-collector-run-collection-9).
      2. Creates a HAS_JOB edge from collector.entity to the new job via
         `tap_grid.services.create_edge`.
      3. Enqueues the `run_collector` Django Task with the JSON-safe
         collector + job entity IDs.
      4. Returns the CollectionJob in its post-enqueue state.

    Manual surfaces (Administrivia run button today) call with
    `manual_run=True` and a short `manual_run_source` identifier. Scheduler
    invocations leave both at defaults; the scheduler-trigger relationship
    is recorded by the inbound `ScheduleFire --TRIGGERED_JOB--> CollectionJob`
    edge (req-tap-cares-scheduler-trigger-provenance-2).

    With ImmediateBackend (v0 default) the returned job will already reflect
    the terminal task outcome by the time this function returns; with a worker
    backend the job will be READY or RUNNING depending on worker pickup
    latency.
    """
    ctx = caller_context or CallerContext()
    now = datetime.now(UTC)

    job_create = _create_node_internal(
        "collection_job",
        {
            "name": f"{collector.name or 'Collection'} {now.isoformat()}",
            "status": CollectionJobStatus.READY.value,
            "enqueued_at": now.isoformat(),
            "manual_run": manual_run,
            "manual_run_source": manual_run_source,
        },
        caller_context=ctx,
    )
    if not job_create.success:
        raise RuntimeError(
            f"run_collection: CollectionJob create failed: "
            f"{[(e.code, e.message) for e in job_create.errors]}"
        )

    job = CollectionJob.objects.get(entity_id=job_create.entity_id)

    create_edge(
        from_entity=collector.entity,
        to_entity=job.entity,
        edge_type="HAS_JOB",
        caller_context=ctx,
    )

    run_collector.enqueue(
        str(collector.entity_id),
        str(job.entity_id),
    )

    # Refresh once to pick up whatever terminal state the task body wrote
    # under ImmediateBackend. Under a worker backend the row may still be in
    # READY or RUNNING at this point; either way we return the latest visible
    # state. We do NOT write to the row here — that would violate the
    # sole-writer invariant (req-tap-cares-collector-job-sole-writer).
    job.refresh_from_db()
    return job
