"""History service layer — adapter between business code and django-simple-history.

This service layer allows future swaps of the history backend without
changing call sites. Currently uses django-simple-history.

History enablement is determined by whether the model has a HistoricalRecords
manager attached, not by FLIP_CONFIG (history is independent of FLIP).
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tap_grid.models import BaseModel


def get_historical_records(model_instance: "BaseModel") -> Any:
    """Retrieve all historical records for a model instance.

    Returns the HistoricalRecords related manager for this instance.
    If the model has no history manager, returns an empty list.

    Args:
        model_instance: The model instance to query history for.

    Returns:
        QuerySet of historical records, or empty list if history not enabled.
    """
    if not hasattr(model_instance.__class__, "history"):
        return []

    return model_instance.history.all()  # type: ignore[attr-defined]


def get_history_timeline(model_instance: "BaseModel") -> list[dict[str, Any]]:
    """Get a human-readable timeline of changes for a model.

    Returns a list of dicts with timestamp, change type, actor, and record ID.
    Useful for audit logs and change feeds.

    Args:
        model_instance: The model instance.

    Returns:
        List of change events with timestamp, change_type, actor, record_id.
    """
    records = get_historical_records(model_instance)
    timeline = []

    for record in records:
        change_type = record.get_history_type_display()
        actor = record.history_user
        actor_str = str(actor) if actor else "unknown"

        timeline.append(
            {
                "timestamp": record.history_date,
                "change_type": change_type,
                "actor": actor_str,
                "record_id": record.history_id,
            }
        )

    return timeline
