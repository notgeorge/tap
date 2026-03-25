"""CallerContext — the typed carrier for actor identity and batch scope.

Every public service-layer function accepts a CallerContext. It carries:
  - user: the acting User (None for system/internal callers)
  - batch_id: an existing batch scope to join (None means the service layer generates one)

A module-level ContextVar holds the active CallerContext so that BaseModel.save()
can read batch_id without requiring a signature change to Django's save() machinery.

See: req-grid-service-pipeline-context
"""

import contextvars
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tap_grid.models import User

_caller_context: contextvars.ContextVar["CallerContext | None"] = contextvars.ContextVar(
    "caller_context",
    default=None,
)


@dataclass(frozen=True)
class CallerContext:
    """Typed carrier for actor identity and batch scope.

    Frozen to prevent accidental mutation inside the write pipeline.

    Attributes:
        user: The acting user. None indicates a system or internal caller.
        batch_id: An existing batch scope to join. None means the service
            layer will generate a new batch_id for this operation.
    """

    user: "User | None" = None
    batch_id: str | None = None


def get_caller_context() -> CallerContext | None:
    """Return the active CallerContext for the current execution context, or None."""
    return _caller_context.get()


def set_caller_context(ctx: CallerContext | None) -> None:
    """Set the active CallerContext for the current execution context."""
    _caller_context.set(ctx)
