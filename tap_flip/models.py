"""tap_flip models — Batch and BatchEvent for FLIP Phase 2.

Batch: Entity representing a logical operation group (extends BaseModel).
BatchEvent: Append-only log table for audit (standalone, not an Entity).
"""

import uuid
from typing import Any, ClassVar

from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

from tap_flip.history.context import get_history_user
from tap_grid.models import BaseModel


class BatchStatus(models.TextChoices):
    """Batch lifecycle states."""

    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"
    FAILED = "failed", "Failed"


class Batch(BaseModel):
    """A logical operation group (ingestion run, bulk update, etc.).

    Batch extends BaseModel, making it a first-class Entity in the TAP graph.
    Batches can be queried, linked, and traversed like any other entity.

    IMPORTANT: Batch disables batch tracking for itself to prevent infinite
    recursion (a Batch cannot belong to another Batch).
    """

    ENTITY_TYPE: ClassVar[str] = "batch"

    # actor and closed_at are managed by service methods, not user payload.
    # started_at is auto_now_add; status/error_message managed via close_batch/fail_batch.
    SERVICE_SCHEMAS: ClassVar[dict[str, dict]] = {
        "create": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "source": {"type": "string"},
                "metadata": {"type": "object"},
            },
        },
        "patch": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "source": {"type": "string"},
                "metadata": {"type": "object"},
                "status": {"type": "string", "enum": ["open", "closed", "failed"]},
                "error_message": {"type": "string"},
            },
        },
        "replace": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "source": {"type": "string"},
                "metadata": {"type": "object"},
            },
        },
    }

    # Batch disables batch tracking to prevent self-reference.
    # History is enabled directly via the HistoricalRecords manager below.
    FLIP_CONFIG: ClassVar[dict[str, Any]] = {
        "batch": {"enabled": False},
    }

    # History tracking (explicit per Phase 1 lesson learned)
    history = HistoricalRecords(get_user=get_history_user)

    status = models.CharField(
        max_length=20,
        choices=BatchStatus.choices,
        default=BatchStatus.OPEN,
        db_index=True,
    )
    source = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Source identifier (e.g., 'scanner:aws', 'import:csv', 'api:v1').",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Free-form metadata about the batch (parameters, counts, etc.).",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="batches",
        help_text="User who initiated the batch (if applicable).",
    )
    started_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the batch was opened.",
    )
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the batch was closed or failed.",
    )
    error_message = models.TextField(
        blank=True,
        default="",
        help_text="Error details if status is 'failed'.",
    )

    class Meta(BaseModel.Meta):
        db_table = "tap_batch"
        ordering = ["-started_at"]

    def __str__(self) -> str:
        display = self.entity.name or str(self.entity.id)
        return f"Batch {display} ({self.status})"


class BatchEventType(models.TextChoices):
    """Event types for BatchEvent."""

    CREATE = "create", "Create"
    UPDATE = "update", "Update"
    DELETE = "delete", "Delete"
    LINK = "link", "Link (edge creation)"
    UNLINK = "unlink", "Unlink (edge deletion)"


class BatchEvent(models.Model):
    """Append-only log of changes within a batch.

    BatchEvent is standalone (not an Entity) because it is internal bookkeeping.
    These records are immutable after creation and enable replay/audit.

    Design: One BatchEvent per atomic operation (create, update, delete).
    Delta storage is NOT included here - django-simple-history handles that.
    BatchEvent's job is correlation (what batch), not reconstruction (what changed).
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )
    batch = models.ForeignKey(
        Batch,
        on_delete=models.CASCADE,
        related_name="events",
    )
    event_type = models.CharField(
        max_length=20,
        choices=BatchEventType.choices,
        db_index=True,
    )
    entity_id = models.UUIDField(
        db_index=True,
        help_text="The Entity that was affected by this operation.",
    )
    entity_type = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Type of the affected entity (for quick filtering).",
    )
    model_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="ORM model class name if applicable (e.g., 'Concept').",
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="batch_events",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional context (edge endpoints, etc.).",
    )

    class Meta:
        db_table = "tap_batch_event"
        ordering = ["timestamp"]
        indexes = [
            models.Index(fields=["batch", "timestamp"], name="idx_batchevent_batch_ts"),
            models.Index(fields=["entity_id", "timestamp"], name="idx_batchevent_entity_ts"),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} on {self.entity_type}:{self.entity_id}"
