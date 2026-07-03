"""tap_cares orchestration services.

`run_collection` is the public entry point for starting a collector run. It
creates the on-grid CollectionJob via `_create_node_internal` (CollectionJob
is INTERNAL_ONLY), links it to the Collector via HAS_COLLECTION_JOB through the standard
service-layer `create_edge`, then enqueues the Django Task that will execute
the registered collector class.

Per `req-tap-cares-collector-job-sole-writer`, the task body owns all
post-creation writes to CollectionJob — `run_collection` does not write to the
row again after handing off to `.enqueue()`.

Spec: req-tap-cares-collector-run-collection (spec-tap-cares-collector.md).
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from django.db import transaction

from tap_auth.enforcement import requires_capability
from tap_cares.collectors.readiness import (
    CollectorReadinessStatus,
    CollectorSelfTestResult,
    check_fail,
)
from tap_cares.exceptions import CollectorNotFoundError
from tap_cares.models import (
    CollectionJob,
    CollectionJobRunMode,
    CollectionJobStatus,
    Collector,
)
from tap_cares.registry import get_collector
from tap_cares.tasks import run_collector
from tap_grid.caller_context import CallerContext
from tap_grid.services import _create_node_internal, _patch_node_internal, create_edge

logger = logging.getLogger(__name__)

# Gateway export manifest (spec-service-layer-boundary.md req-service-boundary-contract-surface):
# the reviewable list of gated collector-execution operations, and nothing else. Every name
# here carries a capability gate — the service-boundary guard fails the build on any ungated
# entry, and on any ungated public function defined in this gateway whether or not it is listed.
# (Scheduler/registry grid operations join the gateway in a follow-on increment.)
__all__ = [
    "run_collection",
    "self_test_collector",
    "fire_collector_and_await",
]

# Loud, self-diagnosing detail for the RUNNER_UNAVAILABLE readiness failure.
# This failure is most often NOT a real misconfiguration: the Steady Queue
# supervisor is long-lived and forks workers from its boot-time memory image,
# and Steady Queue does not hot-reload (req-tap-cares-task-backend-deployment-3).
# A collector registered AFTER the supervisor booted is therefore absent from
# every worker it forks, surfacing here as a confusing mid-job failure on a
# collector that demonstrably works from a fresh `manage.py` process. Name the
# likely cause and the one-line fix at the point of failure rather than leaving
# the next operator to rediscover it. (Resolution stays trusted-startup only —
# this never imports from Collector node data; see
# req-tap-cares-collector-registry-6.)
_RUNNER_UNAVAILABLE_DETAIL = (
    "No collector runner is registered for {key!r} in this worker process. "
    "If this collector exists in the codebase, the most likely cause is a "
    "stale Steady Queue supervisor: it forks workers from its boot-time image "
    "and does not hot-reload (req-tap-cares-task-backend-deployment-3), so a "
    "collector registered after the supervisor started is absent from every "
    "worker it forks. Fix: restart the supervisor to pick up newly-registered "
    "collectors — `scripts/dc restart web`. If the collector genuinely does "
    "not exist in the codebase, this is a real Collector-node misconfiguration."
)
_RUNNER_UNAVAILABLE_SUMMARY = (
    "Collector runner is not registered in this worker process — most likely a "
    "stale Steady Queue supervisor; restart it: `scripts/dc restart web` "
    "(req-tap-cares-task-backend-deployment-3)."
)


@requires_capability("cares.self_test_collectors")
def self_test_collector(
    collector: Collector,
    *,
    caller_context: CallerContext | None = None,
) -> CollectorSelfTestResult:
    """Run a collector's readiness self-test and return a normalized result.

    Single caller-facing entry point (req-tap-cares-collector-self-test-11).
    Owns the cross-cutting concerns the pure hook deliberately excludes:
    registry resolution (`RUNNER_UNAVAILABLE`), exception trapping
    (`SELF_TEST_EXCEPTION`), stamping (`collector_registry` + `checked_at`),
    and the redaction-safe site-ID log summary.

    Returns the result synchronously; it does NOT write the grid. The
    run-task body records it onto `CollectionJob.self_test` and, on a
    non-runnable result, fails the job via the standard failure mode — that
    preserves the `CollectionJob` sole-writer invariant.
    """
    now = datetime.now(UTC)
    try:
        cls = get_collector(collector.collector_registry)
    except CollectorNotFoundError:
        result = CollectorSelfTestResult.from_checks(
            [
                check_fail(
                    "RUNNER_UNAVAILABLE",
                    _RUNNER_UNAVAILABLE_DETAIL.format(key=collector.collector_registry),
                    readiness_status=CollectorReadinessStatus.ERROR,
                    context={"collector_registry": collector.collector_registry},
                )
            ],
            summary=_RUNNER_UNAVAILABLE_SUMMARY,
            collector_registry=collector.collector_registry,
        )
    else:
        try:
            result = cls.self_test().with_collector_registry(collector.collector_registry)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "[8797] collector_self_test_failed collector=%s registry=%s",
                collector.entity_id,
                collector.collector_registry,
            )
            result = CollectorSelfTestResult.from_checks(
                [
                    check_fail(
                        "SELF_TEST_EXCEPTION",
                        f"Collector self-test failed with {type(exc).__name__}: {exc}",
                        readiness_status=CollectorReadinessStatus.ERROR,
                        context={
                            "collector_registry": collector.collector_registry,
                            "exception_type": type(exc).__name__,
                        },
                    )
                ],
                summary="Collector self-test raised an exception.",
                collector_registry=collector.collector_registry,
            )

    # Stamp collector_registry + checked_at so every branch (success,
    # RUNNER_UNAVAILABLE, SELF_TEST_EXCEPTION) returns a self-describing
    # result carrying one authoritative instant
    # (req-tap-cares-collector-self-test-11, stamping).
    result = result.with_collector_registry(collector.collector_registry).with_checked_at(now)

    # One redaction-safe site-ID summary per invocation
    # (req-tap-cares-collector-self-test-8): INFO when runnable, WARNING
    # when not. Per-check detail is DEBUG only.
    counts = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
    for check in result.checks:
        counts[check.status.value] = counts.get(check.status.value, 0) + 1
    log = logger.info if result.runnable else logger.warning
    log(
        "[fa20] collector_self_test collector=%s registry=%s status=%s " "pass=%s warn=%s fail=%s skip=%s summary=%s",
        collector.entity_id,
        collector.collector_registry,
        result.status.value,
        counts["pass"],
        counts["warn"],
        counts["fail"],
        counts["skip"],
        result.summary,
    )
    return result


@requires_capability("cares.run_collectors")
def run_collection(
    collector: Collector,
    *,
    caller_context: CallerContext | None = None,
    manual_run: bool = False,
    manual_run_source: str = "",
    run_mode: str = CollectionJobRunMode.FULL,
) -> CollectionJob:
    """Start a collection run for the given Collector.

    Two authorization decisions, never collapsed (req-tap-auth-actor-model):

      1. **Trigger gate** — `@requires_capability("cares.run_collectors")` checks
         the *triggering* actor: the request user (passed through from tap_web's
         middleware-bound `CallerContext`), the `tap_cares.scheduler` on a tick, or
         the `tap_bootloader` firing boot collectors. tap_web is a pure pass-through
         here — it adds no actor of its own; it hands its request context to this
         service, which confirms that actor may run collectors.
      2. **Execution identity** — the collection itself then runs as the
         least-privilege `tap_cares.collector` program actor (the swap below), never
         as the triggering actor, so the collector's blast radius is bounded
         regardless of who triggered it (the Kubernetes-CronJob ServiceAccount
         model).

    `run_collection` is the sole creator of `CollectionJob` rows
    (req-tap-cares-collector-job-model-18). `run_mode` selects the vehicle:
    `full` (phase 1 → phase 2 if runnable) or `self_test_only` (phase 1 →
    stop) — a one-off readiness probe is just a `self_test_only` job on the
    same async path (req-tap-cares-collector-self-test-16). Manual Run and
    the scheduler use the default `full`.

    Performs, in order:
      1. Creates a CollectionJob node via `_create_node_internal`
         (CollectionJob is INTERNAL_ONLY), persisting `manual_run`,
         `manual_run_source`, and `run_mode` on the row
         (req-tap-cares-collector-run-collection-9).
      2. Creates a HAS_COLLECTION_JOB edge from collector.entity to the new job via
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
    # Collection ALWAYS runs as the least-privilege tap_cares.collector program actor —
    # never as the human or schedule that triggered it (model 2: own service
    # identity, like a Kubernetes CronJob's ServiceAccount). The trigger is
    # recorded as metadata (manual_run / manual_run_source; the schedule's
    # HAS_FIRED/TRIGGERED_JOB provenance), not as the runtime principal, so the
    # collector's blast radius is bounded regardless of who set it up. We keep any
    # batch scope the caller supplied. (req-tap-auth-actor-model; the on-behalf-of
    # delegation alternative is deferred — req-tap-auth-ai-placeholder.)
    from tap_auth.actors import COLLECTOR, get_builtin_actor

    ctx = CallerContext(
        user=get_builtin_actor(COLLECTOR),
        batch_id=caller_context.batch_id if caller_context is not None else None,
    )
    now = datetime.now(UTC)

    if run_mode not in CollectionJobRunMode.values:
        raise ValueError(
            f"run_collection: invalid run_mode {run_mode!r}; " f"expected one of {CollectionJobRunMode.values}."
        )
    # Normalize enum-member or string input to the canonical stored string,
    # mirroring how `status` is persisted as its `.value`.
    run_mode = CollectionJobRunMode(run_mode).value

    collector_label = collector.name or "Collection"
    if run_mode == CollectionJobRunMode.SELF_TEST_ONLY:
        description = f"Self-test-only run of {collector_label!r} enqueued at {now.isoformat()}."
    elif manual_run and manual_run_source:
        description = f"Manual run of {collector_label!r} triggered from " f"{manual_run_source} at {now.isoformat()}."
    elif manual_run:
        description = f"Manual run of {collector_label!r} at {now.isoformat()}."
    else:
        description = f"Collection run of {collector_label!r} enqueued at {now.isoformat()}."

    job_create = _create_node_internal(
        "collection_job",
        {
            "name": f"{collector_label} {now.isoformat()}",
            "description": description,
            "status": CollectionJobStatus.READY.value,
            "run_mode": run_mode,
            "enqueued_at": now.isoformat(),
            "manual_run": manual_run,
            "manual_run_source": manual_run_source,
        },
        caller_context=ctx,
    )
    if not job_create.success:
        raise RuntimeError(
            f"run_collection: CollectionJob create failed: " f"{[(e.code, e.message) for e in job_create.errors]}"
        )

    job = CollectionJob.objects.get(entity_id=job_create.entity_id)

    create_edge(
        from_entity=collector.entity,
        to_entity=job.entity,
        edge_type="HAS_COLLECTION_JOB",
        caller_context=ctx,
    )

    # Defer the enqueue until any surrounding transaction commits, so the
    # Steady Queue worker (on a separate DB connection) never picks up a
    # task whose CollectionJob row hasn't been flushed yet
    # (req-tap-cares-task-backend-transactional-integrity-1). With no
    # outer transaction in progress, transaction.on_commit fires the
    # callback immediately — preserving current behavior for the
    # Administrivia handlers and scheduler Stage 2 call sites.
    #
    # Also captures task_result.id from the returned TaskResult and
    # patches it onto CollectionJob.task_result_id. We do it on the
    # enqueue side rather than from inside run_collector because
    # Steady Queue 0.2.0 doesn't honor takes_context=True; see the
    # comment on run_collector in tap_cares/tasks.py.
    collector_entity_id = str(collector.entity_id)
    job_entity_id = str(job.entity_id)

    def _enqueue_and_record_task_id() -> None:
        task_result = run_collector.enqueue(collector_entity_id, job_entity_id)
        if task_result.id:
            # This on-commit callback fires after the request/task context has
            # been torn down, so the ambient actor is gone. Pass the resolved
            # tap_cares.collector ctx explicitly so this bookkeeping write still
            # binds a named actor (the on-commit analogue of the prod-break the
            # task-body acting_as binding closes).
            _patch_node_internal(job_entity_id, {"task_result_id": task_result.id}, caller_context=ctx)

    transaction.on_commit(_enqueue_and_record_task_id)

    # Refresh once to pick up whatever terminal state the task body wrote
    # under ImmediateBackend. Under a worker backend the row may still be in
    # READY or RUNNING at this point; either way we return the latest visible
    # state. We do NOT write to the row here — that would violate the
    # sole-writer invariant (req-tap-cares-collector-job-sole-writer).
    job.refresh_from_db()
    return job


@requires_capability("cares.run_collectors")
def fire_collector_and_await(
    collector: Collector,
    *,
    caller_context: CallerContext | None = None,
    run_mode: str = CollectionJobRunMode.FULL,
    manual_run_source: str = "boot",
    timeout_seconds: float = 600.0,
    poll_interval_seconds: float = 2.0,
) -> tuple[bool, CollectionJob]:
    """Fire one collector via `run_collection` and block until its job is terminal.

    The reusable fire-collector mechanic shared by `tap_boot`'s population phase
    (`fire-collector` step, req-boot-population) and the dev `fire_boot_collectors`
    command. A real Steady Queue worker drains the job out-of-process, so this
    polls `CollectionJob.status` to a terminal state rather than reading an inline
    result; under ImmediateBackend the first check already sees the terminal state.

    Boot-agnostic: it inherits the ambient actor context the caller bound (the
    trigger gate checks that actor; the collection itself swaps to
    `tap_cares.collector` inside `run_collection`). Returns `(succeeded, job)` —
    `succeeded` is True iff the job reached SUCCESSFUL within `timeout_seconds`.
    """
    job = run_collection(
        collector,
        caller_context=caller_context,
        manual_run=True,
        manual_run_source=manual_run_source,
        run_mode=run_mode,
    )

    terminal = (CollectionJobStatus.SUCCESSFUL.value, CollectionJobStatus.FAILED.value)
    deadline = time.monotonic() + timeout_seconds
    while True:
        job.refresh_from_db()
        if job.status in terminal:
            break
        if time.monotonic() >= deadline:
            return False, job
        time.sleep(poll_interval_seconds)

    return job.status == CollectionJobStatus.SUCCESSFUL.value, job
