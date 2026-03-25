"""FLIP configuration defaults and per-model management.

FLIP_CONFIG controls which FLIP features are enabled per model. History and
perspective have their own independent configuration mechanisms (not FLIP_CONFIG).

Models without FLIP_CONFIG use defaults (all disabled, opt-in).
"""

from typing import Any

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


def is_history_enabled(model_class: type) -> bool:
    """Check if history tracking is enabled for a model.

    A model has history enabled when it carries a HistoricalRecords manager
    (i.e., `history = HistoricalRecords(...)`). History is configured directly
    on the model, not through FLIP_CONFIG.
    """
    return hasattr(model_class, "history")


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
