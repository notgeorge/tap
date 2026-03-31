"""FLIP configuration and field-path map update logic.

FLIP_CONFIG controls which FLIP features are enabled per model. History and
perspective have their own independent configuration mechanisms (not FLIP_CONFIG).

Models without FLIP_CONFIG use defaults (all disabled, opt-in).

This module owns the in-memory mutation of flip_map on BaseModel instances.
update_flip_map() is called from BaseModel.save() before the DB write so the
flip_map update is included in the same transaction as the field changes.

The batch_id is read from tap_grid.context (set by the service layer when a
CallerContext is active).
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tap_grid.models import BaseModel


# ---------------------------------------------------------------------------
# FLIP config
# ---------------------------------------------------------------------------

# Default FLIP_CONFIG — all features disabled by default (opt-in)
DEFAULT_FLIP_CONFIG: dict[str, Any] = {
    "batch": {
        "enabled": False,
    },
    "flip": {
        "enabled": False,
        "fields": [],  # explicit allow-list of top-level Django model field names
    },
}

# Central registry: maps model class name → merged FLIP_CONFIG
_FLIP_REGISTRY: dict[str, dict[str, Any]] = {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge override into base, returning a new dict."""
    result = {}
    for key in base:
        if key in override:
            if isinstance(base[key], dict) and isinstance(override[key], dict):
                result[key] = _deep_merge(base[key], override[key])
            else:
                result[key] = override[key]
        else:
            if isinstance(base[key], dict):
                result[key] = base[key].copy()
            else:
                result[key] = base[key]
    return result


def get_model_flip_config(model_class: type) -> dict[str, Any]:
    """Return merged FLIP_CONFIG for a model.

    Merges model's FLIP_CONFIG attribute (if present) with defaults.
    Results are cached in _FLIP_REGISTRY.

    Args:
        model_class: The model class to query.

    Returns:
        Merged config dict with all required keys.
    """
    class_name = model_class.__name__
    if class_name not in _FLIP_REGISTRY:
        model_config = getattr(model_class, "FLIP_CONFIG", {})
        merged = _deep_merge(DEFAULT_FLIP_CONFIG, model_config)
        _FLIP_REGISTRY[class_name] = merged
    return _FLIP_REGISTRY[class_name]


def is_batch_enabled(model_class: type) -> bool:
    """Check if batch tracking is enabled for a model."""
    config = get_model_flip_config(model_class)
    return bool(config["batch"]["enabled"])


def is_flip_enabled(model_class: type) -> bool:
    """Check if FLIP field-path tracking is enabled for a model."""
    config = get_model_flip_config(model_class)
    return bool(config["flip"]["enabled"])


def get_flip_fields(model_class: type) -> list[str]:
    """Return the list of field names tracked by FLIP for a model."""
    config = get_model_flip_config(model_class)
    return list(config["flip"]["fields"])


def clear_registry() -> None:
    """Clear the FLIP registry. Used in tests."""
    _FLIP_REGISTRY.clear()


# ---------------------------------------------------------------------------
# flip_map update
# ---------------------------------------------------------------------------


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
