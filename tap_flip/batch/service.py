"""Batch service layer — batch lifecycle and event recording.

This module provides the API for:
1. Creating and managing batches
2. Recording batch events
3. Querying batch history

Usage:
    # Context manager for automatic batch lifecycle
    with batch_context(source="scanner:aws", actor=user) as batch_id:
        create_entity("server", display_name="prod-web-01")
        # batch_id automatically populated on models via signals

    # Or explicit API for more control
    batch = create_batch(source="import:csv", actor=user)
    set_batch_id(str(batch.entity.id))
    try:
        # ... operations ...
        close_batch(batch)
    except Exception as e:
        fail_batch(batch, str(e))
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from typing import TYPE_CHECKING, Any

from django.utils import timezone

from tap_grid.services import create_entity
from tap_flip.history.context import get_batch_id, get_history_user, set_batch_id

if TYPE_CHECKING:
    from tap_grid.models import Entity, User
    from tap_flip.models import Batch, BatchEvent


def create_batch(
    source: str = "",
    actor: User | None = None,
    display_name: str = "",
    metadata: dict[str, Any] | None = None,
) -> Batch:
    """Create a new batch.

    Args:
        source: Source identifier (e.g., 'scanner:aws').
        actor: User initiating the batch (falls back to context user).
        display_name: Optional human-readable name.
        metadata: Additional context for the batch.

    Returns:
        The created Batch instance.
    """
    from tap_flip.models import Batch

    actor = actor or get_history_user()

    # Create backing Entity for the Batch
    entity = create_entity(
        entity_type="batch",
        display_name=display_name or f"Batch {datetime.now().isoformat()}",
    )

    return Batch.objects.create(
        entity=entity,
        source=source,
        actor=actor,
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
    from tap_flip.models import BatchStatus

    if batch.status != BatchStatus.OPEN:
        raise ValueError(f"Cannot close batch in status '{batch.status}'")

    batch.status = BatchStatus.CLOSED
    batch.closed_at = timezone.now()
    batch.save(update_fields=["status", "closed_at", "updated_at"])
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
    from tap_flip.models import BatchStatus

    if batch.status != BatchStatus.OPEN:
        raise ValueError(f"Cannot fail batch in status '{batch.status}'")

    batch.status = BatchStatus.FAILED
    batch.closed_at = timezone.now()
    batch.error_message = error_message
    batch.save(update_fields=["status", "closed_at", "error_message", "updated_at"])
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

    This is called by signal handlers. External code typically
    does not need to call this directly.

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
    from tap_flip.models import Batch, BatchEvent

    # Resolve batch_id: explicit param > context > None
    resolved_batch_id = batch_id or get_batch_id()
    if not resolved_batch_id:
        return None

    try:
        batch = Batch.objects.get(entity_id=resolved_batch_id)
    except Batch.DoesNotExist:
        # Log warning but don't fail the operation
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


@contextmanager
def batch_context(
    source: str = "",
    actor: User | None = None,
    display_name: str = "",
    metadata: dict[str, Any] | None = None,
) -> Generator[str]:
    """Context manager for batch operations.

    Creates a batch, sets it in context, and handles lifecycle.

    Usage:
        with batch_context(source="import:csv") as batch_id:
            create_entity(...)  # automatically tagged with batch_id
        # batch is automatically closed on success, failed on exception

    Yields:
        The batch ID (string UUID).
    """
    batch = create_batch(
        source=source,
        actor=actor,
        display_name=display_name,
        metadata=metadata,
    )
    batch_id_str = str(batch.entity.id)

    # Save previous context and set new
    previous_batch_id = get_batch_id()
    set_batch_id(batch_id_str)

    try:
        yield batch_id_str
        close_batch(batch)
    except Exception:
        fail_batch(batch, error_message="Exception during batch execution")
        raise
    finally:
        # Restore previous context
        set_batch_id(previous_batch_id)


def get_batch(batch_id: str) -> Batch | None:
    """Retrieve a batch by its entity ID.

    Args:
        batch_id: The entity ID of the batch (string UUID).

    Returns:
        The Batch instance, or None if not found.
    """
    from tap_flip.models import Batch

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
    from tap_flip.models import Batch

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
    from tap_flip.models import Batch, BatchEvent

    batch_ids = BatchEvent.objects.filter(entity_id=entity_id).values_list("batch_id", flat=True).distinct()

    return list(Batch.objects.filter(id__in=batch_ids).order_by("-started_at"))
