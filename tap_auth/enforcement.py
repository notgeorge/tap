"""On-by-default enforcement: the @requires_capability decorator + structural
backstops (req-tap-auth-policy On By Default).

Two layers make authorization the *default* state rather than something a
developer must remember:

1. `@requires_capability(cap)` decorates a public service function. It opens an
   isolated authorization scope, resolves the `CallerContext` (explicit arg →
   contextvar), and calls `authorize()` before the function body runs. The
   default state of a newly-written guarded function is therefore "gated."

2. The structural backstops — `assert_write_authorized()` (called at the
   write-pipeline commit chokepoint) and `assert_read_authorized()` (called at
   the Search read-dispatch chokepoint) — verify a decision was actually
   recorded for the active scope. An operation that reaches commit/return with
   no recorded decision raises `UnguardedOperation` and **fails closed in every
   mode**. This is the Oso-style "authorize-can-be-forgotten" net: the gate is
   enforced by structure, not reviewer vigilance.

`TAP_TEST_MODE` does not gate enforcement — it only raises the volume (the
unguarded callsite is surfaced for CI). Security behavior never depends on test
mode.
"""

from __future__ import annotations

import functools
import logging
import traceback
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

from tap_auth import capabilities as caps
from tap_auth import policy
from tap_auth.errors import UnguardedOperation

if TYPE_CHECKING:
    from tap_grid.caller_context import CallerContext

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def _resolve_caller_context(kwargs: dict[str, Any]) -> CallerContext | None:
    """Resolve the active CallerContext: explicit `caller_context` kwarg first,
    then the contextvar (set by a request/task/boot boundary)."""
    ctx = kwargs.get("caller_context")
    if ctx is not None:
        return ctx  # type: ignore[no-any-return]
    from tap_grid.caller_context import get_caller_context

    return get_caller_context()


def requires_capability(capability: str, *, operation: str = "") -> Callable[[F], F]:
    """Gate a public service function on one capability.

    Opens a fresh authorization scope, authorizes `capability` for the resolved
    CallerContext, then runs the function. The scope isolates this operation's
    authorization so a directly-called write/read that bypassed the decorator
    fails the structural backstop.
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx = _resolve_caller_context(kwargs)
            token = policy.push_authorization_scope()
            try:
                policy.authorize(ctx, capability, operation=operation or fn.__name__)
                return fn(*args, **kwargs)
            finally:
                policy.pop_authorization_scope(token)

        return wrapper  # type: ignore[return-value]

    return decorator


def _callsite(skip: int = 2) -> str:
    """Best-effort callsite of the code that reached the unguarded chokepoint."""
    stack = traceback.extract_stack()
    # Walk outward past this module's frames to the first non-tap_auth frame.
    for frame in reversed(stack[:-skip]):
        if "/tap_auth/" not in frame.filename:
            return f"{frame.filename}:{frame.lineno} in {frame.name}"
    return "<unknown>"


def _raise_unguarded(kind: str, caller_context: CallerContext | None, detail: str) -> None:
    """Log loudly and raise UnguardedOperation (fail closed in every mode)."""
    callsite = _callsite()
    user = caller_context.user if caller_context is not None else None
    logger.error(
        "[eeef] UNGUARDED %s operation — no authorize() decision recorded; failing closed. "
        "callsite=%s actor=%s detail=%s",
        kind,
        callsite,
        getattr(user, "username", None),
        detail,
        extra={
            "message_data": {
                "flaw_class": "code",
                "flaw_tags": ["security"],
                "kind": kind,
                "callsite": callsite,
                "actor": getattr(user, "username", None),
            }
        },
    )
    raise UnguardedOperation(f"unguarded {kind}: no authorization decision recorded before {detail}", callsite=callsite)


def assert_write_authorized(caller_context: CallerContext | None) -> None:
    """Backstop at the write-pipeline commit chokepoint.

    Passes iff the active scope recorded at least one write-class capability
    (`WRITE_CAPABILITIES`). Otherwise the mutation reached commit without an
    `authorize()` call — fail closed.
    """
    if caps.WRITE_CAPABILITIES & policy.authorized_capabilities():
        return
    _raise_unguarded("write", caller_context, "write_batch commit")


def assert_read_authorized(caller_context: CallerContext | None) -> None:
    """Backstop at the Search read-dispatch chokepoint.

    Passes iff the active scope recorded `grid.read`. Otherwise the read reached
    mode dispatch without an `authorize()` call — fail closed (returns no data).
    """
    if caps.READ_CAPABILITY in policy.authorized_capabilities():
        return
    _raise_unguarded("read", caller_context, "search dispatch")
