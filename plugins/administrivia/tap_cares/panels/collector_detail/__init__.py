"""CARES Collector Detail panel — single-collector detail + run history.

Renders the detail view for one Collector identified by ?entity_id=<uuid>.
Sections:
  - Identity (name, description, entity_id)
  - Registry details (full key, scope, key, runner availability)
  - Latest run summary
  - Manual Run button (HTMX POST)
  - Run history table

Spec: tap_cares/specs/spec-tap-cares-administrivia.md
  req-tap-cares-administrivia-collector-detail
  req-tap-cares-administrivia-run-observability
  req-tap-cares-administrivia-manual-run

Reuses the collector_table panel's run-button POST handling shape; both
adapter helpers (`run_collection`, `get_collector`) and the Current Deviation
note about direct calls (req-tap-cares-collector-run-collection) apply here
identically.
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


def _scope_and_key(registry_key: str) -> tuple[str, str]:
    """Split scope:key for display."""
    if ":" not in registry_key:
        return "", registry_key
    scope, key = registry_key.split(":", 1)
    return scope, key


def _runner_available(registry_key: str) -> bool:
    try:
        get_collector(registry_key)
    except CollectorNotFoundError:
        return False
    return True


def _job_rows(collector_entity_id: str) -> list[dict[str, Any]]:
    """Run history rows for the detail page, newest first.

    Per req-tap-cares-administrivia-run-observability columns: name, status,
    enqueued/started/finished, duration, task_result_id, grift_batches counts,
    summary.
    """
    from tap_grid.models import Edge

    job_ids = list(
        Edge.objects.filter(
            from_entity_id=collector_entity_id,
            edge_type="HAS_JOB",
        ).values_list("to_entity_id", flat=True)
    )
    if not job_ids:
        return []

    jobs = list(
        CollectionJob.objects.filter(entity_id__in=job_ids).order_by("-enqueued_at")
    )

    rows: list[dict[str, Any]] = []
    for j in jobs:
        duration: str | None = None
        if j.started_at and j.finished_at:
            delta = j.finished_at - j.started_at
            total_seconds = delta.total_seconds()
            if total_seconds < 1:
                duration = f"{int(total_seconds * 1000)} ms"
            elif total_seconds < 60:
                duration = f"{total_seconds:.2f} s"
            else:
                duration = f"{int(total_seconds // 60)}m {int(total_seconds % 60)}s"

        imported = (j.grift_batches or {}).get("imported", []) or []
        skipped = (j.grift_batches or {}).get("skipped", []) or []

        rows.append(
            {
                "entity_id": str(j.entity_id),
                "name": j.name,
                "status": j.status,
                "status_display": j.get_status_display(),
                "enqueued_at": j.enqueued_at,
                "started_at": j.started_at,
                "finished_at": j.finished_at,
                "duration": duration,
                "task_result_id": j.task_result_id,
                "grift_imported_count": len(imported),
                "grift_skipped_count": len(skipped),
                "grift_imported": imported,
                "grift_skipped": skipped,
                "summary": j.summary,
                "is_failed": j.status == CollectionJobStatus.FAILED.value,
                "is_running": j.status == CollectionJobStatus.RUNNING.value,
                "is_successful": j.status == CollectionJobStatus.SUCCESSFUL.value,
            }
        )
    return rows


def _build_context(collector_entity_id: str, *, run_message: str = "", run_error: str = "") -> dict[str, Any]:
    """Resolve everything the detail template needs for one collector."""
    if not collector_entity_id:
        return {
            "collector": None,
            "detail_error": "No entity_id provided. Open this page via a collector row.",
            "run_message": run_message,
            "run_error": run_error,
        }

    try:
        collector = Collector.objects.select_related("entity").get(entity_id=collector_entity_id)
    except Collector.DoesNotExist:
        return {
            "collector": None,
            "detail_error": f"Collector '{collector_entity_id}' not found.",
            "run_message": run_message,
            "run_error": run_error,
        }

    scope, key = _scope_and_key(collector.collector_registry)
    available = _runner_available(collector.collector_registry)
    runs = _job_rows(str(collector.entity_id))
    latest = runs[0] if runs else None
    is_running = bool(latest and latest["is_running"])

    return {
        "collector": {
            "entity_id": str(collector.entity_id),
            "name": collector.name,
            "description": collector.description,
            "registry_key": collector.collector_registry,
            "registry_scope": scope,
            "registry_local_key": key,
            "available": available,
            "is_running": is_running,
        },
        "latest_run": latest,
        "runs": runs,
        "detail_error": "",
        "run_message": run_message,
        "run_error": run_error,
    }


class CollectorDetailPanelType:
    slug = "cares_collector_detail"
    label = "CARES Collector Detail"
    view = "administrivia/panels/collector_detail.html"
    css: ClassVar[list[str]] = ["administrivia/css/cares_collector_detail.css"]
    js: ClassVar[list[str]] = []
    editor_view = ""
    config_defaults: ClassVar[dict[str, Any]] = {}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        entity_id = request.GET.get("entity_id", "")
        return _build_context(entity_id)

    @classmethod
    def handle_post(cls, panel: Panel, request: HttpRequest) -> HttpResponse:
        """Run button POST handler — same shape as the table panel.

        Form fields:
          action="run_collector"
          collector_entity_id=<uuid>

        The detail page reads its subject from `?entity_id=`. The form posts
        with the collector_entity_id in the body so the handler doesn't need
        to inspect the page URL.

        Current Deviation (v0): direct call to run_collection. See
        req-tap-cares-collector-run-collection.
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
                            manual_run_source="administrivia.collector_detail",
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

        # Re-render with the same entity_id so the page state updates.
        ctx = _build_context(collector_entity_id, run_message=run_message, run_error=run_error)
        return render(request, cls.view, {"panel": panel, **ctx})
