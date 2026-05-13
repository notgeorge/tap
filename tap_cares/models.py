"""tap_cares models.

req-tap-cares-collector-model, req-tap-cares-collector-job-model,
req-tap-cares-collector-job-edge, req-tap-cares-collector-job-lifecycle
(spec-tap-cares-collector.md).

The Collector model is the on-grid representation of a tap_cares collector
capability. The CollectionJob model is the run record for one attempted
execution of a collector. Collector --HAS_JOB--> CollectionJob ties the two
together. Status mirrors Django's TaskResultStatus for v0; future TAP-specific
states extend the local TextChoices rather than the upstream Django enum.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.core.exceptions import ValidationError
from django.db import models

from tap_cares.exceptions import InvalidCollectorRegistryKeyError
from tap_cares.registry import _validate_collector_token
from tap_grid.models import BaseModel


class Collector(BaseModel):
    """An on-grid tap_cares collector capability.

    The collector_registry field stores a `scope:key` referencing a registered
    CollectorBase subclass. Persisting a Collector with a short key (no `:`),
    a malformed scope/key, or a duplicate collector_registry value all fail
    validation. The Python class itself is never resolved or imported at
    persist time — that happens at execution time via
    `tap_cares.registry.get_collector`.

    Spec: tap_cares/specs/spec-tap-cares-collector.md
    """

    ENTITY_TYPE: ClassVar[str] = "collector"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap_cares": "collector"}
    INTERNAL_ONLY: ClassVar[bool] = True

    OUTBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {"nodes": [{"type": "collection_job"}], "edges": [{"type": "HAS_JOB"}]},
    ]

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, dict[str, Any]]] = {
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "collector_registry": {"type": "string", "minLength": 1},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name", "collector_registry"]

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, dict[str, Any]]] = {
        "name": {
            "validation": "jsonschema",
            "schema": {"type": "string", "minLength": 1},
        },
        "description": {
            "validation": "jsonschema",
            "schema": {"type": "string"},
        },
        "collector_registry": {
            "validation": "jsonschema",
            # Loose JSON-schema check; the strict scope:key format check lives in
            # validate() so the error speaks in terms of scope/key rather than regex.
            "schema": {"type": "string", "minLength": 3},
        },
    }

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    collector_registry = models.CharField(max_length=512, unique=True)

    class Meta(BaseModel.Meta):
        db_table = "tap_cares_collector"

    def get_name(self) -> str:
        return self.name or ""

    def __str__(self) -> str:
        return self.name

    def validate(self) -> None:
        """Enforce the scope:key format on collector_registry.

        Short keys (no `:`) are rejected per req-tap-cares-collector-model-4.
        Both halves of the scope:key are validated with
        `_validate_collector_token`, the same helper the registry calls — so
        model-side and registry-side enforcement cannot drift
        (req-tap-cares-collector-registry-10).
        """
        value = self.collector_registry or ""
        if ":" not in value:
            raise ValidationError(
                {
                    "collector_registry": [
                        "Must use scope:key format; short keys are not allowed.",
                    ]
                }
            )
        scope_part, key_part = value.rsplit(":", 1)
        try:
            _validate_collector_token(scope_part)
            _validate_collector_token(key_part)
        except InvalidCollectorRegistryKeyError as exc:
            raise ValidationError({"collector_registry": [str(exc)]}) from exc


def _empty_results_dict() -> dict[str, list]:
    """Default for `CollectionJob.results`.

    Module-level callable so Django migrations can import it by path. Returns a
    fresh dict per call (mutable defaults must never be shared).
    """
    return {"info": [], "warn": [], "error": []}


def _empty_grift_batches() -> dict[str, list]:
    """Default for `CollectionJob.grift_batches`.

    Same pattern as `_empty_results_dict`: the field's shape is always
    `{"imported": [...], "skipped": [...]}`, even before any GRIFT activity,
    so consumers don't have to `.get("imported", [])` defensively.
    """
    return {"imported": [], "skipped": []}


class CollectionJobStatus(models.TextChoices):
    """v0 CollectionJob lifecycle states — mirror django.tasks.TaskResultStatus.

    req-tap-cares-collector-job-lifecycle. Stored values are uppercase to match
    Django Tasks; display labels are title-case. Future TAP-specific states
    (`CANCEL_REQUESTED`, `CANCELLED`, `BLOCKED`, `PARTIAL`, etc.) extend this
    local enum rather than depending on Django's set evolving
    (req-tap-cares-collector-job-lifecycle-7).
    """

    READY = "READY", "Ready"
    RUNNING = "RUNNING", "Running"
    FAILED = "FAILED", "Failed"
    SUCCESSFUL = "SUCCESSFUL", "Successful"


class CollectionJob(BaseModel):
    """The on-grid run record for one attempted execution of a Collector.

    Created by the tap_cares orchestration service when a collector is
    enqueued; updated as the Django task transitions through its lifecycle.
    Collector module classes do not write to CollectionJob directly
    (req-tap-cares-collector-job-lifecycle-3) — the runtime owns lifecycle
    updates.

    `task_result_id` is the string identifier returned by Django Tasks'
    `TaskResult.id` — not a UUID. The built-in `immediate` / `dummy` backends
    use 32-char random strings; database-backed or third-party backends are
    free to choose another format. Stored as `CharField(max_length=128)` to
    accommodate any of them while staying index-friendly. Empty string means
    the task was not enqueued or enqueue raised
    (req-tap-cares-collector-job-model-6).

    Spec: tap_cares/specs/spec-tap-cares-collector.md
    """

    ENTITY_TYPE: ClassVar[str] = "collection_job"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap_cares": "collection_job"}
    INTERNAL_ONLY: ClassVar[bool] = True

    INBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {"nodes": [{"type": "collector"}], "edges": [{"type": "HAS_JOB"}]},
    ]

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, dict[str, Any]]] = {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "status": {"type": "string", "enum": [s.value for s in CollectionJobStatus]},
        "task_result_id": {"type": "string"},
        "summary": {"type": "string"},
        # Lifecycle timestamps — set by run_collection (enqueued_at) and the
        # run_collector task body (started_at, finished_at). Datetimes flow in
        # as ISO-8601 strings through the service-layer patch path; Django's
        # DateTimeField parses them on save.
        "enqueued_at": {"type": ["string", "null"], "format": "date-time"},
        "started_at": {"type": ["string", "null"], "format": "date-time"},
        "finished_at": {"type": ["string", "null"], "format": "date-time"},
        # Accumulators — written once at terminal state by the task body from
        # the collector instance's self.results / self.grift_batches.
        "results": {"type": "object"},
        "grift_batches": {"type": "object"},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, dict[str, Any]]] = {
        "status": {
            "validation": "jsonschema",
            "schema": {"type": "string", "enum": [s.value for s in CollectionJobStatus]},
        },
        "task_result_id": {
            "validation": "jsonschema",
            "schema": {"type": "string", "maxLength": 128},
        },
        "summary": {
            "validation": "jsonschema",
            "schema": {"type": "string", "maxLength": 2048},
        },
    }

    name = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=16,
        choices=CollectionJobStatus.choices,
        default=CollectionJobStatus.READY,
        db_index=True,
    )
    task_result_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    summary = models.CharField(max_length=2048, blank=True, default="")
    enqueued_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    # GRIFT batch entity IDs produced by this collection run.
    # Populated by `tap_cares.grift.submit_collector_grift` from the
    # GriftImportResult returned by `grift_import()`. Shape:
    #     {"imported": ["<uuidv7>", ...], "skipped": ["<uuidv7>", ...]}
    # Per req-tap-cares-collector-grift-import-4 — minimal correlation in v0.
    grift_batches = models.JSONField(default=_empty_grift_batches, blank=True)
    # Structured per-event log for this run; appended by tap_cares.results
    # record_info / record_warn / record_error helpers. Pinned shape lives at
    # tap_cares/schemas/collection_job_results.schema.json. Per
    # req-tap-cares-collector-job-model-9 through -16.
    results = models.JSONField(default=_empty_results_dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "tap_cares_collection_job"

    def get_name(self) -> str:
        return self.name or f"Collection {self.entity_id}" if self.entity_id else (self.name or "Collection")

    def __str__(self) -> str:
        return self.get_name()

    @property
    def status_display(self) -> str:
        """Title-case human label for `status`.

        Companion to the raw `status` value (req-tap-cares-collector-job-model-8).
        Equivalent to Django's auto-generated `get_status_display()`; exposed as
        a property so serializers and templates can use either spelling.
        """
        return self.get_status_display()
