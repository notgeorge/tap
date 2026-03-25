"""FLIP field-path map update logic.

This module owns the in-memory mutation of flip_map on BaseModel instances.
It is called from BaseModel.save() before the DB write so the flip_map update
is included in the same transaction as the field changes.

The batch_id is read from tap_grid.context (set by tap_flip when a batch opens).
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tap_grid.models import BaseModel


def update_flip_map(instance: "BaseModel", changed_fields: list[str] | None, batch_id: str | None) -> bool:
    """Mutate instance.flip_map in memory for FLIP-tracked fields.

    Should be called before save() so the mutation is included in the same
    DB write. Does NOT issue a separate save call.

    Args:
        instance: The domain model instance being saved.
        changed_fields: Field names being updated, or None for a full save
            (all FLIP-tracked fields are updated).
        batch_id: The active batch ID from tap_grid.context.

    Returns:
        True if flip_map was modified (so the caller can include "flip_map"
        in update_fields when doing a partial save).

    Raises:
        NoBatchContextError: If FLIP is enabled for this model but no batch
            context is active.
    """
    from tap_flip.config import get_model_flip_config

    config = get_model_flip_config(instance.__class__)
    flip_cfg = config.get("flip", {})

    if not flip_cfg.get("enabled", False):
        return False

    if not batch_id:
        from tap_grid.exceptions import NoBatchContextError

        raise NoBatchContextError(
            f"{instance.__class__.__name__} has FLIP enabled but was saved without an "
            "active CallerContext. All FLIP-enabled writes must flow through the service layer "
            "with a CallerContext carrying a batch_id."
        )

    tracked: set[str] = set(flip_cfg.get("fields", []))
    if not tracked:
        return False

    if changed_fields is None:
        # Full save — stamp all tracked fields.
        target = tracked
    else:
        target = tracked & set(changed_fields)

    if not target:
        return False

    for field in target:
        instance.flip_map[field] = batch_id

    return True
