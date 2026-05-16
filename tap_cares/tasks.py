"""Django Tasks runtime for tap_cares collectors.

req-tap-cares-collector-task-execution, req-tap-cares-collector-job-sole-writer,
req-tap-cares-collector-failure-mode, req-tap-cares-collector-self-test
(spec-tap-cares-collector.md).

A single task — `run_collector` — runs a `CollectionJob` as two phases:

  - **Phase 1 — self-test.** Always runs (default-on gate,
    req-tap-cares-collector-self-test-10). Calls the
    `self_test_collector(collector)` service entry point and records the
    structured result onto `CollectionJob.self_test`. A non-runnable result
    fails the job via the standard collector failure mode before any
    external work. A `self_test_only` job stops here SUCCESSFUL.
  - **Phase 2 — collect.** Only for a `full`, runnable job: looks up the
    registered collector class, builds a CollectorConfig, instantiates,
    invokes run(), and writes terminal state.

The task body is the sole writer to CollectionJob after row creation. Writes
per run:
  - run_collection writes the row at READY (kickoff)
  - this task body writes RUNNING + started_at (task start)
  - this task body writes the terminal SUCCESSFUL or FAILED state +
    finished_at + summary + results + grift_batches + self_test (task end)

The collector instance accumulates `self.results`, `self.grift_batches`, and
`self.summary` in memory during run(); the task body reads them at terminal
state and persists them in the terminal patch alongside the phase-1
`self_test` result.
"""

from __future__ import annotations

from datetime import UTC, datetime

from django.tasks import task

from tap_cares.collectors.config import CollectorConfig
from tap_cares.exceptions import CollectorNotReadyError
from tap_cares.models import (
    CollectionJob,
    CollectionJobRunMode,
    CollectionJobStatus,
    Collector,
)
from tap_cares.registry import get_collector
from tap_grid.services import _patch_node_internal

_SUMMARY_CAP = 2048

_EMPTY_RESULTS: dict[str, list] = {"info": [], "warn": [], "error": []}
_EMPTY_GRIFT_BATCHES: dict[str, list] = {"imported": [], "skipped": []}


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
    _patch_node_internal(
        collection_job_entity_id,
        {
            "status": CollectionJobStatus.RUNNING.value,
            "started_at": now.isoformat(),
        },
    )

    # Resolve the CollectionJob (for run_mode) and Collector node. A missing
    # Collector node (deleted between enqueue and pickup) fails the job via
    # the standard failure mode before phase 1 — self_test never ran, so it
    # is not written.
    job = CollectionJob.objects.get(entity_id=collection_job_entity_id)
    try:
        collector = Collector.objects.get(entity_id=collector_entity_id)
    except Collector.DoesNotExist as exc:
        _patch_node_internal(
            collection_job_entity_id,
            {
                "status": CollectionJobStatus.FAILED.value,
                "finished_at": datetime.now(UTC).isoformat(),
                "summary": _safe_summary(exc),
                "results": dict(_EMPTY_RESULTS),
                "grift_batches": dict(_EMPTY_GRIFT_BATCHES),
            },
        )
        raise

    # ------------------------------------------------------------------
    # Phase 1 — self-test. Default-on gate for every CollectionJob
    # (req-tap-cares-collector-self-test-10). The service entry point owns
    # registry resolution (RUNNER_UNAVAILABLE), exception trapping
    # (SELF_TEST_EXCEPTION), stamping, and the redaction-safe site-ID log;
    # it returns the result, never persists. Local import: services.py
    # imports run_collector, so a module-level import here is circular.
    # ------------------------------------------------------------------
    from tap_cares.services import self_test_collector

    readiness = self_test_collector(collector)
    self_test_payload = readiness.to_dict()

    if not readiness.runnable:
        # Non-runnable ⇒ standard collector failure mode
        # (req-tap-cares-collector-failure-mode): one terminal FAILED patch
        # carrying the self-test summary and the full self_test detail; no
        # phase-2 work, no GRIFT, no partial writes.
        _patch_node_internal(
            collection_job_entity_id,
            {
                "status": CollectionJobStatus.FAILED.value,
                "finished_at": datetime.now(UTC).isoformat(),
                "summary": (readiness.summary or "")[:_SUMMARY_CAP],
                "results": dict(_EMPTY_RESULTS),
                "grift_batches": dict(_EMPTY_GRIFT_BATCHES),
                "self_test": self_test_payload,
            },
        )
        # Re-raise so Django Tasks' own failure machinery sees the failure
        # (req-tap-cares-collector-failure-mode-5). The exception carries
        # only the operator-facing summary — no secret-bearing detail.
        raise CollectorNotReadyError(readiness.summary)

    if job.run_mode == CollectionJobRunMode.SELF_TEST_ONLY:
        # self_test_only ⇒ phase 1 passed; stop here SUCCESSFUL with no
        # collection performed (req-tap-cares-collector-self-test-16).
        _patch_node_internal(
            collection_job_entity_id,
            {
                "status": CollectionJobStatus.SUCCESSFUL.value,
                "finished_at": datetime.now(UTC).isoformat(),
                "summary": "Self-test passed; no collection performed.",
                "results": dict(_EMPTY_RESULTS),
                "grift_batches": dict(_EMPTY_GRIFT_BATCHES),
                "self_test": self_test_payload,
            },
        )
        return

    # ------------------------------------------------------------------
    # Phase 2 — collect (full + runnable only). The instance reference is
    # bound inside the try so that even pre-run() failures (collector
    # resolution, instantiation) flow through the same FAILED terminal-patch
    # path. The phase-1 self_test result rides on every phase-2 terminal
    # patch so readiness stays queryable on a failed run too.
    # ------------------------------------------------------------------
    instance = None
    try:
        # Resolve the collector class and instantiate. The instance owns its
        # own accumulator state (self.results, self.grift_batches, self.summary).
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
        # itself. If the instance never got constructed (registry /
        # instantiation failure), use empty defaults for the accumulators.
        if instance is not None:
            summary = _derive_failure_summary(instance, exc)
            results = instance.results
            grift_batches = instance.grift_batches
        else:
            summary = _safe_summary(exc)
            results = dict(_EMPTY_RESULTS)
            grift_batches = dict(_EMPTY_GRIFT_BATCHES)
        _patch_node_internal(
            collection_job_entity_id,
            {
                "status": CollectionJobStatus.FAILED.value,
                "finished_at": datetime.now(UTC).isoformat(),
                "summary": summary,
                "results": results,
                "grift_batches": grift_batches,
                "self_test": self_test_payload,
            },
        )
        # Re-raise so Django Tasks' own failure machinery sees the failure
        # (req-tap-cares-collector-failure-mode-5).
        raise

    # Terminal write: SUCCESSFUL. One patch carries the full accumulator,
    # including whatever the collector wrote to self.summary, plus the
    # phase-1 self_test result.
    _patch_node_internal(
        collection_job_entity_id,
        {
            "status": CollectionJobStatus.SUCCESSFUL.value,
            "finished_at": datetime.now(UTC).isoformat(),
            "summary": (instance.summary or "")[:_SUMMARY_CAP],
            "results": instance.results,
            "grift_batches": instance.grift_batches,
            "self_test": self_test_payload,
        },
    )
