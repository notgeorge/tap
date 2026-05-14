"""tap_cares Steady Queue recurring-task declarations.

Replaces the prior `tap_cares/huey_tasks.py`. The single recurring task
declared here is the once-per-minute scheduler tick that calls
`tap_cares.scheduler.evaluate_tick()`. The Steady Queue supervisor's
scheduler dispatches it on the `scheduler` queue, which is served by a
dedicated worker process so a backed-up collector pool cannot starve the
clock (see `tap_cares/specs/spec-tap-cares-task-backend.md`
`req-tap-cares-task-backend-queue-isolation`).

**Single-`@recurring` rule.** This module declares exactly one
`@recurring`-decorated task. Future scheduling needs always route through
the on-grid `Schedule` entity, never through new `@recurring` decorators.
The rule is enforced by `tap_cares/tests/test_recurring_uniqueness.py`
(req-tap-cares-task-backend-recurring-scope-4).
"""

from __future__ import annotations

import logging

from django.tasks import task
from steady_queue.recurring_task import recurring

logger = logging.getLogger(__name__)


@recurring(
    schedule="* * * * *",
    key="tap_cares_scheduler_tick",
    queue_name="scheduler",
    description="TAP scheduler — evaluates on-grid Schedule entities every minute.",
)
@task()
def scheduler_tick() -> None:
    """Once-per-minute scheduler evaluation tick.

    Defers all logic to `tap_cares.scheduler.evaluate_tick()`. Exceptions
    are logged and swallowed — one bad tick must not stop the next one.
    """
    # Import lazily so the module is importable in Django startup contexts
    # where the tap_cares app graph isn't fully ready yet.
    from tap_cares.scheduler import evaluate_tick

    try:
        fires = evaluate_tick()
    except Exception:  # noqa: BLE001
        logger.exception("scheduler_tick: evaluate_tick raised")
        return

    if fires:
        logger.info("scheduler_tick: produced %d fire(s)", len(fires))
