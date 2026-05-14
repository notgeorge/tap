"""Huey periodic tasks for tap_cares.

The single registered task wakes once per minute and calls
`tap_cares.scheduler.evaluate_tick()` — per spec-tap-cares-scheduler.md
req-tap-cares-scheduler-huey.

Imported from `TapCaresConfig.ready()` so the task is discovered at Django
startup. The Huey consumer (`manage.py run_huey`) is the only process that
actually executes this task; the web process imports the module but the
periodic schedule is only run by the consumer.
"""

from __future__ import annotations

import logging

from huey import crontab
from huey.contrib.djhuey import periodic_task

logger = logging.getLogger(__name__)


@periodic_task(crontab(minute="*"))
def scheduler_tick() -> None:
    """Once-per-minute scheduler evaluation tick.

    Defers all logic to `tap_cares.scheduler.evaluate_tick()`. Exceptions are
    logged and swallowed — one bad tick must not stop the next one.
    """
    # Import lazily so the module is importable in environments where the
    # tap_cares app graph isn't fully ready yet (e.g. plain `manage.py shell`
    # during the Django startup window).
    from tap_cares.scheduler import evaluate_tick

    try:
        fires = evaluate_tick()
    except Exception:  # noqa: BLE001
        logger.exception("scheduler_tick: evaluate_tick raised")
        return

    if fires:
        logger.info("scheduler_tick: produced %d fire(s)", len(fires))
