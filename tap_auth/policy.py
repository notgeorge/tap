"""Central authorization policy (req-tap-auth-policy).

`authorize()` is the single gate: one capability per call, returns None on allow,
raises a typed `tap_auth.errors` exception on denial. `can()` is its
non-raising twin for non-enforcement checks (hiding a UI control), and never
records a decision so it cannot stand in for the enforcing gate at a boundary.

Two deliberate design points:

1. **`is_superuser` is NOT a TAP-service bypass** (req-tap-auth-policy-5). The
   capability check evaluates explicit group→permission membership and never
   calls Django's `user.has_perm()` (which returns True for any superuser).
   Django admin keeps its superuser floor; the TAP service boundary does not.

2. **Decision ledger.** A successful `authorize()` records the capability into a
   contextvar ledger. The on-by-default enforcement backstops (write pipeline /
   read dispatch) consult this ledger to prove an operation was authorized; an
   operation that reaches commit/return with no recorded decision fails closed.
   The ledger primitives live here; the backstops that consume them are wired in
   with the enforcement flip.
"""

from __future__ import annotations

import contextvars
import logging
from typing import TYPE_CHECKING, Any

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

from tap_auth import capabilities as caps
from tap_auth.errors import (
    AuthzError,
    CapabilityDenied,
    InactiveActor,
    MissingActor,
    UnknownCapability,
)
from tap_auth.models import Capability

if TYPE_CHECKING:
    from tap_grid.caller_context import CallerContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Decision ledger — capabilities authorized in the current execution context.
# ---------------------------------------------------------------------------

_authorized: contextvars.ContextVar[set[str] | None] = contextvars.ContextVar(
    "tap_auth_authorized",
    default=None,
)


def record_authorization(capability: str) -> None:
    """Record that `capability` was authorized in the current context."""
    current = _authorized.get()
    if current is None:
        current = set()
        _authorized.set(current)
    current.add(capability)


def authorized_capabilities() -> frozenset[str]:
    """Return the set of capabilities authorized in the current context."""
    current = _authorized.get()
    return frozenset(current) if current else frozenset()


def reset_authorization_ledger() -> None:
    """Clear the ledger — call at request/task/operation boundaries so decisions
    never leak across logical operations."""
    _authorized.set(None)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def _has_capability(user: Any, capability: str) -> bool:
    """True iff `user` holds `capability` via group membership — ignoring superuser.

    Evaluated as an explicit Permission ⋈ Group ⋈ User query, so `is_superuser`
    grants nothing here (req-tap-auth-policy-5). v1 is group-only; direct
    per-user grants are intentionally not part of the TAP path.
    """
    content_type = ContentType.objects.get_for_model(Capability)
    return Permission.objects.filter(
        content_type=content_type,
        codename=caps.codename_for(capability),
        group__user=user,
    ).exists()


def _evaluate(caller_context: CallerContext | None, capability: str) -> None:
    """Raise a typed AuthzError if the capability is not granted; else return None.

    Does not log and does not record a decision — shared by the raising
    `authorize()` and the silent `can()`.
    """
    if caps.get_capability(capability) is None:
        raise UnknownCapability(f"unknown capability: {capability!r}")

    user = caller_context.user if caller_context is not None else None
    if user is None:
        raise MissingActor(f"no named actor for capability {capability!r}")

    if not getattr(user, "is_active", False) or getattr(user, "deactivated_at", None) is not None:
        raise InactiveActor(f"actor {getattr(user, 'username', '?')!r} is inactive")

    if not _has_capability(user, capability):
        raise CapabilityDenied(f"actor lacks capability {capability!r}")


def authorize(
    caller_context: CallerContext | None,
    capability: str,
    *,
    operation: str = "",
    resource_type: str = "",
    resource: Any = None,
) -> None:
    """Authorize one capability for the caller. Returns None on allow; raises a
    typed `tap_auth.errors` exception on denial/error.

    On allow, records the decision in the ledger so the enforcement backstops can
    prove the operation was authorized. On denial, emits a structured security log.
    """
    try:
        _evaluate(caller_context, capability)
    except AuthzError as exc:
        _log_denial(caller_context, capability, operation, resource_type, resource, exc.reason)
        raise
    record_authorization(capability)


def can(
    caller_context: CallerContext | None,
    capability: str,
) -> bool:
    """Non-raising, non-recording predicate twin of `authorize()`.

    For non-enforcement uses (hiding a UI control, branching). Never a substitute
    for `authorize()` at a mutation/read boundary — it records no decision, so it
    cannot satisfy the enforcement backstop.
    """
    try:
        _evaluate(caller_context, capability)
    except AuthzError:
        return False
    return True


def _log_denial(
    caller_context: CallerContext | None,
    capability: str,
    operation: str,
    resource_type: str,
    resource: Any,
    reason: str,
) -> None:
    """Emit a structured security log for an authorization denial (req-tap-auth-policy-4)."""
    user = caller_context.user if caller_context is not None else None
    message_data = {
        "actor": getattr(user, "username", None),
        "actor_kind": getattr(user, "user_kind", None),
        "capability": capability,
        "operation": operation,
        "resource_type": resource_type,
        "resource": str(resource) if resource is not None else None,
        "reason": reason,
    }
    logger.warning(
        "[e5d9] authz denied: reason=%s capability=%s actor=%s operation=%s",
        reason,
        capability,
        message_data["actor"],
        operation,
        extra={"message_data": message_data},
    )
