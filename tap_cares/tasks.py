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
    + summary + results + grift_batches (task end)

The collector instance accumulates `self.results`, `self.grift_batches`, and
`self.summary` in memory during run(); the task body reads them at terminal
state and persists them in the terminal patch.
"""

from __future__ import annotations

from datetime import UTC, datetime

from django.tasks import task

from tap_cares.collectors.config import CollectorConfig
from tap_cares.models import CollectionJob, CollectionJobStatus, Collector
from tap_cares.registry import get_collector
from tap_grid.services import _patch_node_internal

_SUMMARY_CAP = 2048


def _safe_summary(exc: BaseException) -> str:
    msg = f"{type(exc).__name__}: {exc}"
    if len(msg) > _SUMMARY_CAP:
        msg = msg[:_SUMMARY_CAP]
    return msg


def _derive_failure_summary(instance: object, exc: BaseException) -> str:
    """Compose the at-a-glance summary for a FAILED terminal patch.

    Precedence:
        1. collector-set instance.summary, if any
        2. count of recorded error events — "Failed with N error(s)"
        3. exception class + message fallback

    A collector that knows what went wrong should set self.summary directly;
    when it doesn't, the count-derived fallback gives operators "how bad was
    it" at a glance, and the structured detail in results["error"] is where
    they dig in. Per req-tap-cares-collector-failure-mode-3.
    """
    explicit = getattr(instance, "summary", "")
    if explicit:
        return explicit[:_SUMMARY_CAP]
    results = getattr(instance, "results", None)
    if isinstance(results, dict):
        errors = results.get("error") or []
        if errors:
            n = len(errors)
            return f"Failed with {n} error{'s' if n != 1 else ''}"
    return _safe_summary(exc)


@task()
def run_collector(
    collector_entity_id: str,
    collection_job_entity_id: str,
) -> None:
    """Execute one collector run.

    Args:
        collector_entity_id: UUIDv7 of the Collector node (as string).
        collection_job_entity_id: UUIDv7 of the CollectionJob node (as string).

    Note on `takes_context`: this task does NOT use Django Tasks'
    `takes_context=True` mechanism. Steady Queue 0.2.0 doesn't honor that
    flag — its `ClaimedExecution.perform()` calls `task.func(*args, **kwargs)`
    without injecting a `TaskContext`, so a context-taking task fails with
    a "missing positional argument" error when picked up by a steady_queue
    worker. We capture `task_result.id` on the enqueue side instead
    (see `tap_cares.services.run_collection`). Restore `takes_context=True`
    once upstream gains support.
    """
    # Task start: RUNNING transition. Patches status + started_at; the
    # task_result_id is set on the enqueue side in run_collection so this
    # task body doesn't depend on backend-specific context plumbing.
    now = datetime.now(UTC)
    start_payload: dict[str, str] = {
        "status": CollectionJobStatus.RUNNING.value,
        "started_at": now.isoformat(),
    }

    _patch_node_internal(collection_job_entity_id, start_payload)

    # The instance reference is bound inside the try so that even pre-run()
    # failures (collector resolution, instantiation) flow through the same
    # FAILED terminal-patch path. accumulator state is then read off the
    # instance if it exists, or filled with empty defaults otherwise.
    instance = None
    try:
        # Resolve the collector class and instantiate. The instance owns its
        # own accumulator state (self.results, self.grift_batches, self.summary).
        collector = Collector.objects.get(entity_id=collector_entity_id)
        cls = get_collector(collector.collector_registry)
        config = CollectorConfig(
            collector_entity_id=collector.entity_id,
            collection_job_entity_id=collection_job_entity_id,
        )
        instance = cls(config)
        # Run the collector. It accumulates results/grift_batches/summary on
        # itself; nothing it does touches the CollectionJob row.
        instance.run()
    except Exception as exc:
        # Terminal write: FAILED. One patch carries the full accumulator. If
        # the collector set self.summary, that wins; otherwise derive a count
        # summary from results["error"], finally falling back to the exception
        # itself. If the instance never got constructed (resolution / registry
        # / instantiation failure), use empty defaults for the accumulators.
        if instance is not None:
            summary = _derive_failure_summary(instance, exc)
            results = instance.results
            grift_batches = instance.grift_batches
        else:
            summary = _safe_summary(exc)
            results = {"info": [], "warn": [], "error": []}
            grift_batches = {"imported": [], "skipped": []}
        _patch_node_internal(
            collection_job_entity_id,
            {
                "status": CollectionJobStatus.FAILED.value,
                "finished_at": datetime.now(UTC).isoformat(),
                "summary": summary,
                "results": results,
                "grift_batches": grift_batches,
            },
        )
        # Re-raise so Django Tasks' own failure machinery sees the failure
        # (req-tap-cares-collector-failure-mode-5).
        raise

    # Terminal write: SUCCESSFUL. One patch carries the full accumulator,
    # including whatever the collector wrote to self.summary.
    _patch_node_internal(
        collection_job_entity_id,
        {
            "status": CollectionJobStatus.SUCCESSFUL.value,
            "finished_at": datetime.now(UTC).isoformat(),
            "summary": (instance.summary or "")[:_SUMMARY_CAP],
            "results": instance.results,
            "grift_batches": instance.grift_batches,
        },
    )
