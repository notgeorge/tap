"""Batch service layer — batch lifecycle and event recording.

This module provides the API for:
1. Creating and managing batches
2. Recording batch events
3. Querying batch history

Note: batch_context() has been removed. Batch lifecycle is now managed by the
service layer, which generates a batch_id and threads it via CallerContext.
See req-grid-service-batch-infra and req-grid-service-batch-signals.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from django.utils import timezone

from tap_grid.context import get_batch_id
from tap_grid.history import get_history_user
from tap_grid.services import create_entity

if TYPE_CHECKING:
    from tap_grid.models import Batch, BatchEvent, Entity, User


def create_batch(
    source: str = "",
    actor: User | None = None,
    name: str = "",
    description: str = "",
    description_json: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    entity_id: uuid.UUID | str | None = None,
) -> Batch:
    """Create a new batch.

    Args:
        source: Source identifier (e.g., 'scanner:aws').
        actor: User initiating the batch (falls back to context user).
        name: Human-readable batch name; also used as the backing Entity name.
        description: Long-form description of the batch purpose.
        description_json: Structured description payload with format and data keys.
        metadata: Additional context for the batch.
        entity_id: Optional pre-specified UUID for the backing Entity (e.g. GRIFT import).
            When omitted, a new UUIDv7 is generated.

    Returns:
        The created Batch instance.
    """
    from tap_grid.models import Batch, Entity

    actor = actor or get_history_user()

    resolved_name = name or f"Batch {datetime.now().isoformat()}"

    # Create backing Entity for the Batch, optionally with a pre-specified ID.
    if entity_id is not None:
        resolved_id = uuid.UUID(str(entity_id)) if not isinstance(entity_id, uuid.UUID) else entity_id
        entity = Entity.objects.create(
            id=resolved_id,
            entity_type="batch",
            name=resolved_name,
        )
    else:
        entity = create_entity(
            entity_type="batch",
            name=resolved_name,
        )

    return Batch.objects.create(
        entity=entity,
        source=source,
        actor=actor,
        name=resolved_name,
        description=description,
        description_json=description_json,
        metadata=metadata or {},
    )


def close_batch(batch: Batch) -> Batch:
    """Close a batch successfully.

    Args:
        batch: The batch to close.

    Returns:
        The updated batch.

    Raises:
        ValueError: If batch is not open.
    """
    from tap_grid.models import BatchStatus

    if batch.status != BatchStatus.OPEN:
        raise ValueError(f"Cannot close batch in status '{batch.status}'")

    batch.status = BatchStatus.CLOSED
    batch.closed_at = timezone.now()
    batch.save(update_fields=["status", "closed_at"])
    return batch


def fail_batch(batch: Batch, error_message: str = "") -> Batch:
    """Mark a batch as failed.

    Args:
        batch: The batch to fail.
        error_message: Description of the failure.

    Returns:
        The updated batch.

    Raises:
        ValueError: If batch is not open.
    """
    from tap_grid.models import BatchStatus

    if batch.status != BatchStatus.OPEN:
        raise ValueError(f"Cannot fail batch in status '{batch.status}'")

    batch.status = BatchStatus.FAILED
    batch.closed_at = timezone.now()
    batch.error_message = error_message
    batch.save(update_fields=["status", "closed_at", "error_message"])
    return batch


def record_batch_event(
    entity: Entity,
    event_type: str,
    model_name: str = "",
    actor: User | None = None,
    metadata: dict[str, Any] | None = None,
    batch_id: str | None = None,
) -> BatchEvent | None:
    """Record a change event in the current batch.

    Args:
        entity: The Entity that was affected.
        event_type: Type of change (create, update, delete, link, unlink).
        model_name: ORM model class name if applicable.
        actor: User making the change (falls back to context user).
        metadata: Additional context.
        batch_id: Explicit batch ID (falls back to context batch_id).

    Returns:
        The created BatchEvent, or None if no batch context.
    """
    from tap_grid.models import Batch, BatchEvent

    # Resolve batch_id: explicit param > context > None
    resolved_batch_id = batch_id or get_batch_id()
    if not resolved_batch_id:
        return None

    try:
        batch = Batch.objects.get(entity_id=resolved_batch_id)
    except Batch.DoesNotExist:
        return None

    actor = actor or get_history_user()

    return BatchEvent.objects.create(
        batch=batch,
        event_type=event_type,
        entity_id=entity.id,
        entity_type=entity.entity_type,
        model_name=model_name,
        actor=actor,
        metadata=metadata or {},
    )


def get_batch(batch_id: str) -> Batch | None:
    """Retrieve a batch by its entity ID.

    Args:
        batch_id: The entity ID of the batch (string UUID).

    Returns:
        The Batch instance, or None if not found.
    """
    from tap_grid.models import Batch

    try:
        return Batch.objects.select_related("entity", "actor").get(entity_id=batch_id)
    except Batch.DoesNotExist:
        return None


def get_batch_events(batch_id: str) -> list[BatchEvent]:
    """Get all events for a batch.

    Args:
        batch_id: The entity ID of the batch (string UUID).

    Returns:
        List of BatchEvent instances, or empty list if batch not found.
    """
    from tap_grid.models import Batch

    try:
        batch = Batch.objects.get(entity_id=batch_id)
        return list(batch.events.all())
    except Batch.DoesNotExist:
        return []


def get_entity_batches(entity_id: uuid.UUID) -> list[Batch]:
    """Get all batches that affected a specific entity.

    Args:
        entity_id: The UUID of the entity.

    Returns:
        List of Batch instances that have events for this entity.
    """
    from tap_grid.models import Batch, BatchEvent

    batch_ids = BatchEvent.objects.filter(entity_id=entity_id).values_list("batch_id", flat=True).distinct()

    return list(Batch.objects.filter(id__in=batch_ids).order_by("-started_at"))
