"""Shared real-backend drain for the dev-validation surfaces.

The load-bearing mechanism proven by the Phase-0 spike
(`tap_cares/management/commands/dev_validation_spike.py`) and now reused by the
Phase-1 cold-boot gate (`tap_boot` `cold_boot_gate`): drive an enqueued
collection `Job` to a terminal state through the **real** DB-backed Steady Queue
backend — never the pytest `ImmediateBackend` substitute — with an in-process
synchronous drain.

The drain is the production Steady Queue primitives minus the supervisor / fork /
thread-pool / polling-loop that normally *drive* them:

    ScheduledExecution.dispatch_next_batch()   # promote scheduled -> ready
    ReadyExecution.objects.claim(queues, ...)  # real FOR UPDATE SKIP LOCKED
    ClaimedExecution.perform()                 # real deserialize + task.func

`ReadyExecution.claim` short-circuits to `[]` on a `None` process_id, so the
drain registers a synthetic `Process` (no fork / heartbeat / supervisor) and
deregisters it afterward. This is genuinely distinct from `ImmediateBackend`
(which runs the task inline in the enqueuing transaction and so masks the
cross-connection-visibility bug class this exists to catch) and from the deferred
out-of-process real-worker tiers (`spec-tap-cares-task-backend.md`
`req-tap-cares-task-backend-backlog-2`).

Spec: `specs/spec-dev-validation.md` (`req-dev-validation-real-backend`).
"""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)

# Queues the drain services: collector jobs land on "default"; the scheduler
# promotes recurring work onto "scheduler".
DRAIN_QUEUES = ["default", "scheduler"]


class DrainTimeout(Exception):
    """The ready set did not empty before the deadline — a delivery hang."""


def drain_ready_executions(*, deadline: float, batch: int = 100) -> int:
    """Synchronously drain the real Steady Queue ready set until empty or `deadline`.

    Registers a synthetic drain `Process` (claim requires a non-null process_id),
    loops dispatch → claim → perform until no work remains and nothing is
    scheduled, then deregisters. Returns the number of executions performed.

    Raises:
        DrainTimeout: if work is still pending when `deadline` (a
            `time.monotonic()` value) passes — a real delivery-hang failure.
    """
    from steady_queue.models.process import Process
    from steady_queue.models.ready_execution import ReadyExecution
    from steady_queue.models.scheduled_execution import ScheduledExecution

    performed = 0
    proc = Process.register(
        kind="DevValidationDrain",
        name=f"dev-validation-drain-{os.getpid()}",
        pid=os.getpid(),
        hostname="dev-validation-drain",
        metadata={},
    )
    try:
        while True:
            ScheduledExecution.dispatch_next_batch(batch)
            claimed = ReadyExecution.objects.claim(DRAIN_QUEUES, batch, proc.id)
            for execution in claimed:
                execution.perform()
                performed += 1
            if time.monotonic() > deadline:
                raise DrainTimeout(
                    f"drain exceeded deadline after performing {performed} execution(s); "
                    f"queue not draining (delivery hang)."
                )
            if not claimed and ScheduledExecution.objects.count() == 0:
                logger.info("[c7a2] dev-validation drain empty after %d execution(s)", performed)
                return performed
    finally:
        proc.deregister()
