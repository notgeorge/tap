"""tap_cares scheduler service.

The scheduler decides *when* a collector should run. It does not own collector
execution — once a tick determines that a schedule should fire, it invokes
`tap_cares.services.run_collection(...)` and lets the collector runtime own
CollectionJob lifecycle.

Two public entry points:

- `create_schedule(...)`  — creates a Schedule and its SCHEDULED_TARGET edge.
- `set_schedule_enabled(...)` — toggles `enabled` and manages `enabled_at`.
- `evaluate_tick(...)`    — evaluates all enabled schedules against the
                            current UTC minute slot and returns the fires
                            this tick produced.

Spec: tap_cares/specs/spec-tap-cares-scheduler.md.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from croniter import croniter
from django.db import transaction
from django.db.models import Q

from tap_auth.enforcement import requires_capability
from tap_cares.models import (
    CollectionJob,
    CollectionJobStatus,
    Collector,
    Schedule,
    ScheduleFire,
    ScheduleFireStatus,
)
from tap_grid.caller_context import CallerContext
from tap_grid.models import Edge
from tap_grid.services import (
    _create_node_internal,
    _patch_node_internal,
    create_edge,
    create_node,
    patch_node,
)

logger = logging.getLogger(__name__)


def _scheduler_ctx(caller_context: CallerContext | None) -> CallerContext:
    """Resolve the acting context for scheduler writes.

    A caller that supplies its own named actor keeps it; otherwise scheduler
    bookkeeping (Schedule/ScheduleFire nodes + edges, and the automated tick)
    runs as the named tap_cares.scheduler program actor — never User=None at the
    service boundary (req-tap-auth-actor-model).
    """
    if caller_context is not None and caller_context.user is not None:
        return caller_context
    from tap_auth.actors import SCHEDULER, get_builtin_actor

    return CallerContext(
        user=get_builtin_actor(SCHEDULER),
        batch_id=caller_context.batch_id if caller_context is not None else None,
    )


class SchedulerError(RuntimeError):
    """Raised when the scheduler service hits an unrecoverable internal state."""


def _floor_to_minute(dt: datetime) -> datetime:
    """Truncate a datetime to minute precision in UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return dt.replace(second=0, microsecond=0)


def _matches_slot(cron_expression: str, slot: datetime) -> bool:
    """True if the cron expression matches the given UTC minute slot.

    croniter.match accepts a datetime and returns True if it lies on a
    matching slot at minute precision.
    """
    return croniter.match(cron_expression, slot)


def _missed_count(
    cron_expression: str,
    lower_bound: datetime | None,
    current_slot: datetime,
) -> int:
    """Count cron slots strictly between lower_bound and current_slot.

    Uses croniter to iterate matching slots (req-tap-cares-scheduler-missed-count-5).
    Returns 0 when lower_bound is None (brand-new schedule's first fire).
    """
    if lower_bound is None:
        return 0
    if lower_bound >= current_slot:
        return 0
    itr = croniter(cron_expression, lower_bound)
    count = 0
    while True:
        nxt = itr.get_next(datetime)
        if nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=UTC)
        if nxt >= current_slot:
            break
        count += 1
        # Defensive bound: even an every-minute schedule walking a full year
        # is only ~525k slots. A runaway loop here would be a croniter bug.
        if count > 1_000_000:
            raise SchedulerError(
                f"missed_count exceeded 1,000,000 walking {cron_expression!r} "
                f"from {lower_bound} to {current_slot}; aborting"
            )
    return count


def _target_collector(schedule: Schedule) -> Collector:
    """Resolve the single Collector linked via SCHEDULED_TARGET.

    v0 requires exactly one SCHEDULED_TARGET edge per Schedule
    (req-tap-cares-scheduler-edges-2). Raises if zero or more than one.
    """
    edges = list(
        Edge.objects.filter(
            from_entity_id=schedule.entity_id,
            edge_type="SCHEDULED_TARGET",
        )
    )
    if not edges:
        raise SchedulerError(f"Schedule {schedule.entity_id} has no SCHEDULED_TARGET edge")
    if len(edges) > 1:
        raise SchedulerError(
            f"Schedule {schedule.entity_id} has {len(edges)} SCHEDULED_TARGET " "edges; v0 requires exactly one"
        )
    return Collector.objects.get(entity_id=edges[0].to_entity_id)


def _active_run_count(schedule: Schedule) -> int:
    """Count in-flight CollectionJobs triggered by this schedule.

    Walks Schedule -HAS_FIRED-> ScheduleFire -TRIGGERED_JOB-> CollectionJob
    and counts jobs whose status is READY or RUNNING
    (req-tap-cares-scheduler-concurrency-2).
    """
    fire_ids = Edge.objects.filter(
        from_entity_id=schedule.entity_id,
        edge_type="HAS_FIRED",
    ).values_list("to_entity_id", flat=True)

    job_ids = Edge.objects.filter(
        from_entity_id__in=list(fire_ids),
        edge_type="TRIGGERED_JOB",
    ).values_list("to_entity_id", flat=True)

    return CollectionJob.objects.filter(
        entity_id__in=list(job_ids),
        status__in=[
            CollectionJobStatus.READY.value,
            CollectionJobStatus.RUNNING.value,
        ],
    ).count()


@requires_capability("cares.manage_schedules")
def create_schedule(
    *,
    name: str,
    cron_expression: str,
    collector: Collector,
    description: str = "",
    enabled: bool = True,
    max_active_runs: int = 1,
    caller_context: CallerContext | None = None,
) -> Schedule:
    """Create a Schedule and its SCHEDULED_TARGET edge.

    Cron validation happens at write time (Schedule.validate() runs croniter
    on every save — req-tap-cares-scheduler-model-7). `enabled_at` is stamped
    automatically by Schedule.save() when `enabled=True`
    (req-tap-cares-scheduler-model-8); not passed in the payload because the
    field is scheduler-owned and intentionally absent from FIELD_CRUD_SCHEMA.
    """
    ctx = _scheduler_ctx(caller_context)

    payload: dict[str, Any] = {
        "name": name,
        "description": description,
        "enabled": enabled,
        "cron_expression": cron_expression,
        "max_active_runs": max_active_runs,
    }

    result = create_node("schedule", payload, caller_context=ctx)
    if not result.success:
        raise SchedulerError(f"create_schedule failed: {[(e.code, e.message) for e in result.errors]}")

    schedule = Schedule.objects.get(entity_id=result.entity_id)
    create_edge(
        from_entity=schedule.entity,
        to_entity=collector.entity,
        edge_type="SCHEDULED_TARGET",
        caller_context=ctx,
    )
    return schedule


@requires_capability("cares.toggle_schedules")
def set_schedule_enabled(
    schedule: Schedule,
    enabled: bool,
    *,
    caller_context: CallerContext | None = None,
) -> Schedule:
    """Toggle a schedule's `enabled` flag, updating `enabled_at` on transitions.

    Transitioning False -> True sets `enabled_at` to the current UTC time so
    the missed-count walk's lower bound excludes the disabled stretch
    (req-tap-cares-scheduler-missed-count-4).

    The `enabled` flip goes through `patch_node` so the policy change shows
    up in history. The `enabled_at` stamp on transitions goes through direct
    ORM `.update()` because the field is scheduler-owned and intentionally
    absent from FIELD_CRUD_SCHEMA (same pattern as `last_schedule_fired` in
    the atomic claim). The two writes are wrapped in one transaction so a
    failure between them doesn't leave the schedule with a stale cursor.
    """
    ctx = _scheduler_ctx(caller_context)
    transitioning = enabled and not schedule.enabled

    with transaction.atomic():
        result = patch_node(schedule.entity_id, {"enabled": enabled}, caller_context=ctx)
        if not result.success:
            raise SchedulerError(f"set_schedule_enabled failed: " f"{[(e.code, e.message) for e in result.errors]}")
        if transitioning:
            Schedule.objects.filter(pk=schedule.pk).update(
                enabled_at=datetime.now(UTC)
            )  # TAP-WRITE-COV: program-actor scheduler enabled_at bookkeeping
    schedule.refresh_from_db()
    return schedule


def _claim_and_create_fire(
    schedule: Schedule,
    current_slot: datetime,
    missed: int,
    fired_at: datetime,
    caller_context: CallerContext,
) -> ScheduleFire | None:
    """Stage 1: atomic claim + provisional PENDING fire + HAS_FIRED edge.

    Returns the fire if the claim succeeded; None if another worker won the race
    (req-tap-cares-scheduler-dedupe).
    """
    with transaction.atomic():
        claimed = (
            Schedule.objects.filter(
                pk=schedule.pk
            )  # TAP-WRITE-COV: atomic compare-and-set claim must be one SQL UPDATE (req-tap-cares-scheduler-dedupe)
            .filter(Q(last_schedule_fired__lt=current_slot) | Q(last_schedule_fired__isnull=True))
            .update(last_schedule_fired=current_slot)
        )
        if claimed == 0:
            return None

        fire_result = _create_node_internal(  # TAP-AUTHZ-COV: bound tap_cares.scheduler via _scheduler_ctx; grid.write re-checked at the write backstop
            "schedule_fire",
            {
                "name": f"{schedule.name} fire {current_slot.isoformat()}",
                "description": (
                    f"Scheduler decision for {schedule.name!r} at cron " f"slot {current_slot.isoformat()}."
                ),
                "scheduled_for": current_slot.isoformat(),
                "fired_at": fired_at.isoformat(),
                "missed_count": missed,
                "status": ScheduleFireStatus.PENDING.value,
                "summary": "",
            },
            caller_context=caller_context,
        )
        if not fire_result.success:
            raise SchedulerError(f"ScheduleFire create failed: " f"{[(e.code, e.message) for e in fire_result.errors]}")
        fire = ScheduleFire.objects.get(entity_id=fire_result.entity_id)

        create_edge(
            from_entity=schedule.entity,
            to_entity=fire.entity,
            edge_type="HAS_FIRED",
            caller_context=caller_context,
        )
        return fire


def _finalize_fire_skipped(
    fire: ScheduleFire,
    summary: str,
    caller_context: CallerContext,
) -> None:
    """Stage 2 SKIPPED transition. PENDING -> SKIPPED with a summary."""
    result = _patch_node_internal(  # TAP-AUTHZ-COV: bound tap_cares.scheduler via _scheduler_ctx; grid.write re-checked at the write backstop
        fire.entity_id,
        {"status": ScheduleFireStatus.SKIPPED.value, "summary": summary},
        caller_context=caller_context,
    )
    if not result.success:
        logger.exception(
            "[14b5] scheduler: SKIPPED patch failed for fire %s: %s",
            fire.entity_id,
            result.errors,
        )


def _finalize_fire_failed(
    fire: ScheduleFire,
    summary: str,
    caller_context: CallerContext,
) -> None:
    """Stage 2 FAILED transition. PENDING -> FAILED with a summary."""
    result = _patch_node_internal(  # TAP-AUTHZ-COV: bound tap_cares.scheduler via _scheduler_ctx; grid.write re-checked at the write backstop
        fire.entity_id,
        {"status": ScheduleFireStatus.FAILED.value, "summary": summary},
        caller_context=caller_context,
    )
    if not result.success:
        logger.exception(
            "[cd53] scheduler: FAILED patch failed for fire %s: %s",
            fire.entity_id,
            result.errors,
        )


def _finalize_fire_triggered(
    fire: ScheduleFire,
    job: CollectionJob,
    summary: str,
    caller_context: CallerContext,
) -> None:
    """Stage 2 TRIGGERED transition: status patch + TRIGGERED_JOB edge.

    Wrapped in one transaction so the status and the edge cannot diverge.
    """
    with transaction.atomic():
        result = _patch_node_internal(  # TAP-AUTHZ-COV: bound tap_cares.scheduler via _scheduler_ctx; grid.write re-checked at the write backstop
            fire.entity_id,
            {"status": ScheduleFireStatus.TRIGGERED.value, "summary": summary},
            caller_context=caller_context,
        )
        if not result.success:
            raise SchedulerError(
                f"TRIGGERED patch failed for fire {fire.entity_id}: " f"{[(e.code, e.message) for e in result.errors]}"
            )
        create_edge(
            from_entity=fire.entity,
            to_entity=job.entity,
            edge_type="TRIGGERED_JOB",
            caller_context=caller_context,
        )


@requires_capability("cares.run_scheduler")
def evaluate_tick(
    now: datetime | None = None,
    *,
    caller_context: CallerContext | None = None,
) -> list[ScheduleFire]:
    """Evaluate all enabled schedules against the current UTC minute slot.

    Returns the fires this tick produced (zero or more). The list reflects
    fires whose Stage 1 claim succeeded — Stage 2 transitions may have
    already updated them to TRIGGERED, SKIPPED, or FAILED by the time this
    function returns.

    Caller (Huey periodic task) invokes this once per minute. Multiple workers
    may race: the atomic claim in Stage 1 guarantees one fire per slot.
    """
    ctx = _scheduler_ctx(caller_context)
    wallclock = now if now is not None else datetime.now(UTC)
    current_slot = _floor_to_minute(wallclock)

    fires: list[ScheduleFire] = []

    enabled_schedules = list(Schedule.objects.filter(enabled=True))
    for schedule in enabled_schedules:
        if not _matches_slot(schedule.cron_expression, current_slot):
            continue

        # Compute the missed-count lower bound: max(last_schedule_fired, enabled_at)
        lower_bound: datetime | None = None
        for candidate in (schedule.last_schedule_fired, schedule.enabled_at):
            if candidate is None:
                continue
            if lower_bound is None or candidate > lower_bound:
                lower_bound = candidate

        missed = _missed_count(schedule.cron_expression, lower_bound, current_slot)

        # Stage 1: atomic claim + PENDING fire + HAS_FIRED edge.
        try:
            fire = _claim_and_create_fire(
                schedule=schedule,
                current_slot=current_slot,
                missed=missed,
                fired_at=wallclock,
                caller_context=ctx,
            )
        except Exception:
            logger.exception(
                "[0cd1] scheduler: Stage 1 failed for schedule %s slot %s",
                schedule.entity_id,
                current_slot.isoformat(),
            )
            continue

        if fire is None:
            # Duplicate slot — another worker won the claim. No-op.
            continue
        fires.append(fire)

        # Stage 2: concurrency check + dispatch (outside the claim transaction).
        try:
            active = _active_run_count(schedule)
            if active >= schedule.max_active_runs:
                _finalize_fire_skipped(
                    fire,
                    f"Skipped: max_active_runs reached ({active} active).",
                    ctx,
                )
                continue

            collector = _target_collector(schedule)
            try:
                # Local import: scheduler.py lives inside the tap_cares.services package
                # now, and run_collection is defined in the package __init__ — a top-level
                # import would be circular at package initialization. Imported at the use
                # site (the established lazy-import pattern in this app).
                from tap_cares.services import run_collection

                job = run_collection(collector, caller_context=ctx)
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "[48df] scheduler: run_collection raised for schedule %s",
                    schedule.entity_id,
                )
                _finalize_fire_failed(
                    fire,
                    f"Scheduler error: {type(exc).__name__}: {exc}",
                    ctx,
                )
                continue

            _finalize_fire_triggered(
                fire,
                job,
                f"Triggered run for {schedule.name!r}.",
                ctx,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "[9f18] scheduler: Stage 2 failed for fire %s",
                fire.entity_id,
            )
            try:
                _finalize_fire_failed(
                    fire,
                    f"Scheduler error: {type(exc).__name__}: {exc}",
                    ctx,
                )
            except Exception:
                logger.exception(
                    "[0b38] scheduler: even fire FAILED patch failed for %s",
                    fire.entity_id,
                )

    return fires
