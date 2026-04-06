"""FLIP field-path map update logic.

FLIP (Field-Level Information Provenance) is default-on for all service-writeable
model types. It stamps every service-writeable field with the batch_id responsible
for the current canonical value, derived from the model's SERVICE_SCHEMAS rather
than a per-model allow-list.

Rules:
- Internal-only model types (INTERNAL_ONLY = True) are excluded from FLIP.
- Service-writeable fields are the union of properties declared in
  SERVICE_SCHEMAS["create"], ["patch"], and ["replace"].
- If no CallerContext batch_id is active, FLIP stamping is silently skipped.
  Direct ORM saves outside the service layer simply do not record provenance.
- The batch_id is read from tap_grid.context (set by the service layer when a
  CallerContext is active).
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tap_grid.models import BaseModel


def _get_service_writeable_fields(model_class: type) -> set[str]:
    """Return the union of field names declared across all SERVICE_SCHEMAS payloads."""
    schemas = getattr(model_class, "SERVICE_SCHEMAS", {})
    fields: set[str] = set()
    for key in ("create", "patch", "replace"):
        props = schemas.get(key, {}).get("properties", {})
        fields.update(props.keys())
    return fields


def is_flip_enabled(model_class: type) -> bool:
    """Return True if FLIP is active for this model type.

    FLIP is enabled when the model has at least one service-writeable field
    and is not marked internal-only.
    """
    if getattr(model_class, "INTERNAL_ONLY", False):
        return False
    return bool(_get_service_writeable_fields(model_class))


def clear_registry() -> None:
    """No-op. Retained for test compatibility during the config-deprecation pass."""


def update_flip_map(instance: BaseModel, changed_fields: list[str] | None, batch_id: str | None) -> bool:
    """Mutate instance.flip_map in memory for all service-writeable fields.

    Default-on: derives tracked fields from SERVICE_SCHEMAS rather than an
    explicit allow-list. Internal-only model types are excluded.

    Should be called before save() so the mutation is included in the same
    DB write. Does NOT issue a separate save call.

    Args:
        instance: The domain model instance being saved.
        changed_fields: Field names being updated, or None for a full save
            (all service-writeable fields are stamped).
        batch_id: The active batch ID from CallerContext. If None, returns
            False without raising — direct ORM saves outside the service layer
            simply do not record provenance.

    Returns:
        True if flip_map was modified (so the caller can include "flip_map"
        in update_fields when doing a partial save).
    """
    if not batch_id:
        return False

    if getattr(instance.__class__, "INTERNAL_ONLY", False):
        return False

    service_fields = _get_service_writeable_fields(instance.__class__)
    if not service_fields:
        return False

    if changed_fields is None:
        target = service_fields
    else:
        target = service_fields & set(changed_fields)

    if not target:
        return False

    for field in target:
        instance.flip_map[field] = batch_id

    return True
