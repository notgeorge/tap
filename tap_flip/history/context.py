"""Context management for history tracking.

Provides the history_user contextvar for django-simple-history integration.
The batch_id contextvar lives in tap_grid.context (grid-level operational context)
and is re-exported here for backward compatibility.
"""

import contextvars
from typing import TYPE_CHECKING

from tap_grid.context import get_batch_id, set_batch_id

if TYPE_CHECKING:
    from tap_grid.models import User

# Re-export so existing imports from tap_flip.history.context continue to work.
__all__ = ["get_batch_id", "set_batch_id", "get_history_user", "set_history_user"]

_history_user: contextvars.ContextVar["User | None"] = contextvars.ContextVar(
    "history_user",
    default=None,
)


def set_history_user(user: "User | None") -> None:
    """Set the current user for history context."""
    _history_user.set(user)


def get_history_user(instance: object = None, **kwargs: object) -> "User | None":
    """Return the current user from context, or None if unset.

    Args:
        instance: The model instance being saved (passed by django-simple-history).
        **kwargs: Additional kwargs from django-simple-history (ignored).
    """
    return _history_user.get()
