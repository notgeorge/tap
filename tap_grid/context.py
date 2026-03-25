"""Grid-level context variables for request/operation scoping.

These contextvars are owned by tap_grid because they represent core operational
context (which batch is active) that the grid layer needs to read during writes.
tap_flip sets the batch_id when opening a batch; tap_grid reads it in BaseModel.save().
"""

import contextvars

_batch_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "batch_id",
    default=None,
)


def set_batch_id(batch_id: str | None) -> None:
    """Set the active batch ID for the current context."""
    _batch_id.set(batch_id)


def get_batch_id() -> str | None:
    """Return the active batch ID, or None if no batch context is set."""
    return _batch_id.get()
