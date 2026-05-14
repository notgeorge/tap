"""CARES Collector Table panel — homepage view of registered collectors.

Renders the collectors table for the CARES homepage and handles the HTMX
Run button POST that triggers `tap_cares.services.run_collection`.

Spec: tap_cares/specs/spec-tap-cares-administrivia.md
  req-tap-cares-administrivia-collector-table
  req-tap-cares-administrivia-manual-run
  req-tap-cares-administrivia-htmx-trigger

Data loading is via the Django ORM in v0 because we aggregate the latest
CollectionJob per Collector (last status, last_run_at, last summary),
which is awkward to express in gryphon as of v0. Tracked as a future
gryphon-traversable query when the aggregation primitives land.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from django.http import HttpResponse
from django.shortcuts import render

from tap_cares.exceptions import CollectorNotFoundError
from tap_cares.models import CollectionJob, CollectionJobStatus, Collector
from tap_cares.registry import get_collector
from tap_cares.services import run_collection

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel

logger = logging.getLogger(__name__)


def _scope_from_registry_key(registry_key: str) -> str:
    """Extract the scope half from a fully-qualified scope:key registry value."""
    if ":" not in registry_key:
        return ""
    return registry_key.split(":", 1)[0]


def _runner_available(registry_key: str) -> bool:
    """True if the collector_registry currently has a runner for this key."""
    try:
        get_collector(registry_key)
    except CollectorNotFoundError:
        return False
    return True


def _row_for_collector(collector: Collector) -> dict[str, Any]:
    """Build one table-row dict for the collector listing.

    Aggregates the latest CollectionJob per collector via the HAS_JOB edge —
    we look up the edge set to find connected jobs and pick the most recently
    enqueued one. Empty/none for never-run collectors.
    """
    from tap_grid.models import Edge

    job_ids = list(
        Edge.objects.filter(
            from_entity_id=collector.entity_id,
            edge_type="HAS_JOB",
        ).values_list("to_entity_id", flat=True)
    )

    latest = None
    if job_ids:
        latest = (
            CollectionJob.objects.filter(entity_id__in=job_ids)
            .order_by("-enqueued_at")
            .first()
        )

    latest_finished = None
    if latest is not None:
        latest_finished = (
            CollectionJob.objects.filter(
                entity_id__in=job_ids,
                finished_at__isnull=False,
            )
            .order_by("-finished_at")
            .first()
        )

    return {
        "entity_id": str(collector.entity_id),
        "name": collector.name,
        "description": collector.description,
        "registry_key": collector.collector_registry,
        "source_plugin": _scope_from_registry_key(collector.collector_registry),
        "available": _runner_available(collector.collector_registry),
        "current_status": latest.status if latest is not None else "",
        "current_status_display": latest.get_status_display() if latest is not None else "",
        "last_run_status": latest_finished.status if latest_finished is not None else "",
        "last_run_status_display": latest_finished.get_status_display() if latest_finished is not None else "",
        "last_run_at": latest_finished.finished_at if latest_finished is not None else None,
        "last_summary": latest_finished.summary if latest_finished is not None else "",
        "is_running": bool(
            latest is not None and latest.status == CollectionJobStatus.RUNNING.value
        ),
    }


def _build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-row state into the summary strip values.

    Per req-tap-cares-administrivia-homepage-3.
    """
    total = len(rows)
    available = sum(1 for r in rows if r["available"])
    missing = total - available
    running = sum(1 for r in rows if r["is_running"])
    failed_last = sum(1 for r in rows if r["last_run_status"] == CollectionJobStatus.FAILED.value)
    last_success_at = max(
        (r["last_run_at"] for r in rows if r["last_run_status"] == CollectionJobStatus.SUCCESSFUL.value and r["last_run_at"] is not None),
        default=None,
    )
    return {
        "total": total,
        "available": available,
        "missing": missing,
        "running": running,
        "failed_last": failed_last,
        "last_success_at": last_success_at,
    }


class CollectorTablePanelType:
    slug = "cares_collector_table"
    label = "CARES Collector Table"
    view = "administrivia/panels/collector_table.html"
    css: ClassVar[list[str]] = ["administrivia/css/cares_collector_table.css"]
    js: ClassVar[list[str]] = []
    editor_view = ""
    config_defaults: ClassVar[dict[str, Any]] = {}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        collectors = list(Collector.objects.select_related("entity").order_by("name"))
        rows = [_row_for_collector(c) for c in collectors]
        summary = _build_summary(rows)
        return {
            "collector_rows": rows,
            "collector_summary": summary,
        }

    @classmethod
    def handle_post(cls, panel: Panel, request: HttpRequest) -> HttpResponse:
        """Handle the Run button POST.

        Form fields:
          action="run_collector"
          collector_entity_id=<uuid>

        On success or failure, re-renders the full panel fragment so the row
        reflects the new state. Errors surface as `run_message` in the panel
        context with a per-row class so the user sees what happened.

        Current Deviation (v0): this handler calls `run_collection` directly.
        The eventual flow inserts the scheduler subsystem between the
        Administrivia panel POST and run_collection — see
        req-tap-cares-collector-run-collection and
        req-tap-cares-administrivia-manual-run.
        """
        run_message = ""
        run_error = ""

        action = request.POST.get("action", "")
        collector_entity_id = request.POST.get("collector_entity_id", "")

        if action != "run_collector":
            run_error = f"Unknown action '{action}'."
        elif not collector_entity_id:
            run_error = "Missing collector_entity_id."
        else:
            try:
                collector = Collector.objects.get(entity_id=collector_entity_id)
            except Collector.DoesNotExist:
                run_error = f"Collector '{collector_entity_id}' not found."
            else:
                if not _runner_available(collector.collector_registry):
                    run_error = (
                        f"Collector '{collector.name}' has no registered runner for "
                        f"'{collector.collector_registry}'."
                    )
                else:
                    try:
                        job = run_collection(
                            collector,
                            manual_run=True,
                            manual_run_source="administrivia.collector_table",
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.exception(
                            "run_collection failed for collector %s", collector.entity_id
                        )
                        run_error = f"Failed to enqueue: {type(exc).__name__}: {exc}"
                    else:
                        run_message = (
                            f"Triggered '{collector.name}'. Latest job: "
                            f"{job.get_status_display()}."
                        )

        # Re-render the full panel so the row reflects the new lifecycle state.
        ctx = cls.get_view_context(panel, request)
        ctx["run_message"] = run_message
        ctx["run_error"] = run_error
        return render(
            request,
            cls.view,
            {
                "panel": panel,
                **ctx,
            },
        )
