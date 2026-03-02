"""Signal handlers for batch event recording.

These signals automatically:
1. Populate batch_id on models before save (pre_save)
2. Record BatchEvent after save (post_save)
3. Record BatchEvent on delete (post_delete)

Signals are no-ops when:
- The model is not a BaseModel subclass
- Batch tracking is disabled for the model (FLIP_CONFIG)
- No batch context is set (get_batch_id() returns None)
"""

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from tap_grid.models import BaseModel
from tap_flip.config import is_batch_enabled
from tap_flip.history.context import get_batch_id, get_history_user


@receiver(pre_save)
def populate_batch_id(sender: type, instance: object, **kwargs: object) -> None:
    """Populate batch_id on model before save.

    Only populates if:
    - Instance is a BaseModel subclass
    - Batch tracking is enabled for this model
    - A batch context is set
    - The instance doesn't already have a batch_id
    """
    if not isinstance(instance, BaseModel):
        return
    if not is_batch_enabled(sender):
        return

    batch_id = get_batch_id()
    if batch_id and not instance.batch_id:
        instance.batch_id = batch_id


@receiver(post_save)
def record_save_event(sender: type, instance: object, created: bool, **kwargs: object) -> None:
    """Record batch event after model save.

    Records a 'create' or 'update' event depending on whether
    the instance was newly created.
    """
    if not isinstance(instance, BaseModel):
        return
    if not is_batch_enabled(sender):
        return

    batch_id = get_batch_id()
    if not batch_id:
        return  # No batch context, no-op

    # Import here to avoid circular imports
    from tap_flip.batch.service import record_batch_event

    record_batch_event(
        entity=instance.entity,
        event_type="create" if created else "update",
        model_name=sender.__name__,
        actor=get_history_user(),
    )


@receiver(post_delete)
def record_delete_event(sender: type, instance: object, **kwargs: object) -> None:
    """Record batch event on model delete."""
    if not isinstance(instance, BaseModel):
        return
    if not is_batch_enabled(sender):
        return

    batch_id = get_batch_id()
    if not batch_id:
        return

    from tap_flip.batch.service import record_batch_event

    record_batch_event(
        entity=instance.entity,
        event_type="delete",
        model_name=sender.__name__,
        actor=get_history_user(),
    )
