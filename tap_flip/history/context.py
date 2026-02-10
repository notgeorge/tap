"""Context management for history tracking.

Provides contextvars for implicit user and batch_id tracking.
Explicit parameters in service calls take precedence over context.
"""

import contextvars
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tap_core.models import User

# ContextVar for the current user making changes.
# Set by middleware/views before service calls.
_history_user: contextvars.ContextVar[User | None] = contextvars.ContextVar(
    "history_user",
    default=None,
)

# ContextVar for the current batch_id (Phase 2).
# Will be set when processing a batch; None if no batch context.
_batch_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "batch_id",
    default=None,
)


def set_history_user(user: User | None) -> None:
    """Set the current user for history context.

    Call this in middleware or before service methods.
    """
    _history_user.set(user)


def get_history_user(instance: object = None, **kwargs: object) -> User | None:
    """Get the current user from context, or None if unset.

    Args:
        instance: The model instance being saved (passed by django-simple-history).
        **kwargs: Additional kwargs from django-simple-history (ignored).

    Returns:
        The user from context, or None if unset.
    """
    return _history_user.get()


def set_batch_id(batch_id: str | None) -> None:
    """Set the current batch_id (Phase 2)."""
    _batch_id.set(batch_id)


def get_batch_id() -> str | None:
    """Get the current batch_id from context, or None if unset."""
    return _batch_id.get()
