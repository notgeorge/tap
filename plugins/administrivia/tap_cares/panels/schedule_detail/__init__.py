"""CARES Schedule Detail panel — single-schedule detail + fire history.

Renders the detail view for one Schedule identified by ?entity_id=<uuid>.
Sections:
  - Identity (name, description, entity_id)
  - Configuration (cron_expression, enabled, enabled_at, max_active_runs,
    last_schedule_fired)
  - Target collector (link to its detail page; "missing runner" / "no target"
    callouts when applicable)
  - Fire history table (last 100 fires)

Spec: tap_cares/specs/spec-tap-cares-administrivia.md
  req-tap-cares-administrivia-schedule-detail
  req-tap-cares-administrivia-fire-history

Read-only in v0: no enable/disable toggle, no edit form, no delete.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from tap_cares.exceptions import CollectorNotFoundError
from tap_cares.models import (
    CollectionJob,
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

# req-tap-cares-administrivia-fire-history-6: cap the displayed fires at the
# most recent N until retention policy lands in the scheduler spec.
FIRE_HISTORY_CAP = 100


def _runner_available(registry_key: str) -> bool:
    try:
        get_collector(registry_key)
    except CollectorNotFoundError:
        return False
    return True


def _target_collector(schedule: Schedule) -> Collector | None:
    edge = Edge.objects.filter(
        from_entity_id=schedule.entity_id,
        edge_type="SCHEDULED_TARGET",
    ).first()
    if edge is None:
        return None
    return Collector.objects.filter(entity_id=edge.to_entity_id).first()


def _job_for_fire(fire_entity_id: str) -> CollectionJob | None:
    """The CollectionJob a TRIGGERED fire produced, if any.

    Non-TRIGGERED fires don't have a TRIGGERED_JOB edge, so this returns None.
    """
    edge = Edge.objects.filter(
        from_entity_id=fire_entity_id,
        edge_type="TRIGGERED_JOB",
    ).first()
    if edge is None:
        return None
    return CollectionJob.objects.filter(entity_id=edge.to_entity_id).first()


def _fire_rows(schedule_entity_id: str) -> list[dict[str, Any]]:
    """Fire history rows for the detail page, newest first, capped.

    Per req-tap-cares-administrivia-fire-history.
    """
    fire_ids = list(
        Edge.objects.filter(
            from_entity_id=schedule_entity_id,
            edge_type="HAS_FIRED",
        ).values_list("to_entity_id", flat=True)
    )
    if not fire_ids:
        return []

    fires = list(
        ScheduleFire.objects.filter(entity_id__in=fire_ids)
        .order_by("-scheduled_for")[:FIRE_HISTORY_CAP]
    )

    rows: list[dict[str, Any]] = []
    for f in fires:
        job = _job_for_fire(str(f.entity_id))
        rows.append(
            {
                "entity_id": str(f.entity_id),
                "scheduled_for": f.scheduled_for,
                "fired_at": f.fired_at,
                "status": f.status,
                "status_display": f.get_status_display(),
                "missed_count": f.missed_count,
                "summary": f.summary,
                "job_entity_id": str(job.entity_id) if job else "",
                "job_name": job.name if job else "",
                "job_status": job.status if job else "",
                "job_status_display": job.get_status_display() if job else "",
            }
        )
    return rows


def _build_context(schedule_entity_id: str) -> dict[str, Any]:
    if not schedule_entity_id:
        return {
            "schedule": None,
            "detail_error": "No entity_id provided. Open this page via a schedule row.",
        }

    try:
        schedule = Schedule.objects.select_related("entity").get(
            entity_id=schedule_entity_id
        )
    except Schedule.DoesNotExist:
        return {
            "schedule": None,
            "detail_error": f"Schedule '{schedule_entity_id}' not found.",
        }

    target = _target_collector(schedule)
    target_available = (
        _runner_available(target.collector_registry) if target is not None else False
    )
    fires = _fire_rows(str(schedule.entity_id))
    capped = len(fires) >= FIRE_HISTORY_CAP

    return {
        "schedule": {
            "entity_id": str(schedule.entity_id),
            "name": schedule.name,
            "description": schedule.description,
            "cron_expression": schedule.cron_expression,
            "enabled": schedule.enabled,
            "enabled_at": schedule.enabled_at,
            "max_active_runs": schedule.max_active_runs,
            "last_schedule_fired": schedule.last_schedule_fired,
        },
        "target": (
            {
                "entity_id": str(target.entity_id),
                "name": target.name,
                "description": target.description,
                "registry_key": target.collector_registry,
                "available": target_available,
            }
            if target is not None
            else None
        ),
        "fires": fires,
        "fires_capped": capped,
        "fire_history_cap": FIRE_HISTORY_CAP,
        "detail_error": "",
    }


class ScheduleDetailPanelType:
    slug = "cares_schedule_detail"
    label = "CARES Schedule Detail"
    view = "administrivia/panels/schedule_detail.html"
    css: ClassVar[list[str]] = ["administrivia/css/cares_schedule_detail.css"]
    js: ClassVar[list[str]] = []
    editor_view = ""
    config_defaults: ClassVar[dict[str, Any]] = {}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        entity_id = request.GET.get("entity_id", "")
        return _build_context(entity_id)
