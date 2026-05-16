"""CARES Schedule Table panel — homepage view of registered schedules.

Renders the schedules table that mounts on the CARES homepage below the
collectors table. Read-only in v0: no toggles, no run actions, no edit forms.

Spec: tap_cares/specs/spec-tap-cares-administrivia.md
  req-tap-cares-administrivia-schedule-table

Data loading is via the Django ORM in v0. Per-schedule fire / job lookups
walk the edge tables directly (`SCHEDULED_TARGET`, `HAS_FIRED`,
`TRIGGERED_JOB`); same trade-off the collector_table panel made — pulls
that the gryphon traversal language does not yet express ergonomically.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from tap_cares.exceptions import CollectorNotFoundError
from tap_cares.models import (
    CollectionJob,
    CollectionJobStatus,
    Collector,
    Schedule,
    ScheduleFire,
)
from tap_cares.registry import get_collector
from tap_grid.models import Edge

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel

logger = logging.getLogger(__name__)


def _runner_available(registry_key: str) -> bool:
    """True if the collector_registry currently has a runner for this key."""
    try:
        get_collector(registry_key)
    except CollectorNotFoundError:
        return False
    return True


def _target_collector_for(schedule: Schedule) -> Collector | None:
    """Resolve the schedule's target Collector via SCHEDULED_TARGET.

    Returns None when the edge is missing — the table surfaces that as a
    misconfiguration without raising (req-tap-cares-administrivia-schedule-table-7).
    """
    edge = Edge.objects.filter(
        from_entity_id=schedule.entity_id,
        edge_type="SCHEDULED_TARGET",
    ).first()
    if edge is None:
        return None
    return Collector.objects.filter(entity_id=edge.to_entity_id).first()


def _latest_fire(schedule: Schedule) -> ScheduleFire | None:
    """Most recent ScheduleFire for this schedule, by scheduled_for."""
    fire_ids = list(
        Edge.objects.filter(
            from_entity_id=schedule.entity_id,
            edge_type="HAS_FIRED",
        ).values_list("to_entity_id", flat=True)
    )
    if not fire_ids:
        return None
    return ScheduleFire.objects.filter(entity_id__in=fire_ids).order_by("-scheduled_for").first()


def _active_run_count(schedule: Schedule) -> int:
    """In-flight CollectionJob count triggered by this schedule.

    Walks Schedule -HAS_FIRED-> ScheduleFire -TRIGGERED_JOB-> CollectionJob
    and counts jobs whose status is READY or RUNNING — same definition the
    scheduler uses for its overlap guard
    (`req-tap-cares-scheduler-concurrency-2`).
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


def _row_for_schedule(schedule: Schedule) -> dict[str, Any]:
    target = _target_collector_for(schedule)
    target_available = _runner_available(target.collector_registry) if target is not None else False
    latest = _latest_fire(schedule)
    active = _active_run_count(schedule)

    return {
        "entity_id": str(schedule.entity_id),
        "name": schedule.name,
        "description": schedule.description,
        "cron_expression": schedule.cron_expression,
        "enabled": schedule.enabled,
        "max_active_runs": schedule.max_active_runs,
        "target": (
            {
                "entity_id": str(target.entity_id),
                "name": target.name,
                "available": target_available,
            }
            if target is not None
            else None
        ),
        "latest_fire": (
            {
                "status": latest.status,
                "status_display": latest.get_status_display(),
                "scheduled_for": latest.scheduled_for,
                "summary": latest.summary,
                "missed_count": latest.missed_count,
            }
            if latest is not None
            else None
        ),
        "active_runs": active,
        "misconfigured": target is None or not target_available,
    }


class ScheduleTablePanelType:
    slug = "cares_schedule_table"
    label = "CARES Schedule Table"
    view = "administrivia/panels/schedule_table.html"
    css: ClassVar[list[str]] = ["administrivia/css/cares_schedule_table.css"]
    js: ClassVar[list[str]] = []
    editor_view = ""
    config_defaults: ClassVar[dict[str, Any]] = {}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        schedules = list(Schedule.objects.select_related("entity").order_by("name"))
        rows = [_row_for_schedule(s) for s in schedules]
        return {"schedule_rows": rows}
