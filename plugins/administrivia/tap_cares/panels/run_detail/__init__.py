"""CARES Run Detail panel — single-CollectionJob deep-dive view.

Renders one CollectionJob identified by ?entity_id=<uuid>. Sections:
  - Run header (collector name, status, durations, summary)
  - Counts strip (info / warn / error / grift batches)
  - Structured event sections (info, warn, error) with full site / code / message / context

Spec: tap_cares/specs/spec-tap-cares-administrivia.md
  req-tap-cares-administrivia-run-observability

The page is reached by clicking through from a CARES Collector Detail run-history
row; the row passes ?entity_id=<job_uuid>. No write actions; this is a read-only
deep-dive surface.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar

from tap_cares.models import CollectionJob, CollectionJobStatus, Collector

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tap_web.models import Panel


def _format_duration(started_at: Any, finished_at: Any) -> str | None:
    if not (started_at and finished_at):
        return None
    delta = finished_at - started_at
    total_seconds = delta.total_seconds()
    if total_seconds < 1:
        return f"{int(total_seconds * 1000)} ms"
    if total_seconds < 60:
        return f"{total_seconds:.2f} s"
    return f"{int(total_seconds // 60)}m {int(total_seconds % 60)}s"


def _pretty_context(ctx: Any) -> str:
    """Best-effort pretty-print of an entry's context dict for the template.

    Falls back to repr() for anything that doesn't serialize cleanly so we
    never lose information; the template wraps the result in <pre>.
    """
    if ctx is None or ctx == {}:
        return ""
    try:
        return json.dumps(ctx, indent=2, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return repr(ctx)


def _entries(results: dict[str, Any] | None, level: str) -> list[dict[str, Any]]:
    if not isinstance(results, dict):
        return []
    raw = results.get(level) or []
    out: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        out.append(
            {
                "site": entry.get("site", ""),
                "code": entry.get("code", ""),
                "message": entry.get("message", ""),
                "context": _pretty_context(entry.get("context")),
                "has_context": bool(entry.get("context")),
            }
        )
    return out


def _collector_for(job: CollectionJob) -> Collector | None:
    """Resolve the Collector that produced `job` via the HAS_JOB inverse."""
    from tap_grid.models import Edge

    collector_id = (
        Edge.objects.filter(to_entity_id=job.entity_id, edge_type="HAS_JOB")
        .values_list("from_entity_id", flat=True)
        .first()
    )
    if not collector_id:
        return None
    return Collector.objects.filter(entity_id=collector_id).first()


def _build_context(job_entity_id: str) -> dict[str, Any]:
    if not job_entity_id:
        return {"job": None, "detail_error": "No entity_id provided. Open this page via a run-history row."}

    try:
        job = CollectionJob.objects.get(entity_id=job_entity_id)
    except CollectionJob.DoesNotExist:
        return {"job": None, "detail_error": f"CollectionJob '{job_entity_id}' not found."}

    collector = _collector_for(job)
    results = job.results or {}
    grift = job.grift_batches or {}
    info_entries = _entries(results, "info")
    warn_entries = _entries(results, "warn")
    error_entries = _entries(results, "error")
    imported = grift.get("imported", []) or []
    skipped = grift.get("skipped", []) or []

    return {
        "job": {
            "entity_id": str(job.entity_id),
            "name": job.name,
            "status": job.status,
            "status_display": job.get_status_display(),
            "is_running": job.status == CollectionJobStatus.RUNNING.value,
            "is_failed": job.status == CollectionJobStatus.FAILED.value,
            "is_successful": job.status == CollectionJobStatus.SUCCESSFUL.value,
            "enqueued_at": job.enqueued_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "duration": _format_duration(job.started_at, job.finished_at),
            "task_result_id": job.task_result_id,
            "summary": job.summary,
        },
        "collector": (
            {
                "entity_id": str(collector.entity_id),
                "name": collector.name,
                "registry_key": collector.collector_registry,
            }
            if collector is not None
            else None
        ),
        "counts": {
            "info": len(info_entries),
            "warn": len(warn_entries),
            "error": len(error_entries),
            "grift_imported": len(imported),
            "grift_skipped": len(skipped),
        },
        "info_entries": info_entries,
        "warn_entries": warn_entries,
        "error_entries": error_entries,
        "grift_imported": imported,
        "grift_skipped": skipped,
        "detail_error": "",
    }


class RunDetailPanelType:
    slug = "cares_run_detail"
    label = "CARES Run Detail"
    view = "administrivia/panels/run_detail.html"
    css: ClassVar[list[str]] = ["administrivia/css/cares_run_detail.css"]
    js: ClassVar[list[str]] = []
    editor_view = ""
    config_defaults: ClassVar[dict[str, Any]] = {}

    @classmethod
    def get_view_context(cls, panel: Panel, request: HttpRequest) -> dict[str, Any]:
        entity_id = request.GET.get("entity_id", "")
        return _build_context(entity_id)
