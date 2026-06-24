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

2. **Stateless backstop — no decision ledger.** The on-by-default enforcement
   backstops (write-commit / read-dispatch) re-check the actor's capability
   directly via `can(actor, needed_cap)`. In capability-only v1, "did we
   authorize this operation?" and "does the actor hold the capability?" are the
   same question, so there is no contextvar ledger to leak across requests or
   threads (req-tap-auth-policy-8).
"""

from __future__ import annotations

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


def is_actor_active(user: Any) -> bool:
    """Single definition of an *active* actor: enabled AND not deactivated.

    `is_active=True AND deactivated_at IS NULL`. Centralized so the three places
    that ask "is this actor usable?" — `_evaluate` here, `get_builtin_actor`
    (runtime resolution), and `_ensure_program_actor` (sync repair, which clears
    `deactivated_at`) — cannot drift into a state where a lookup hands back an
    actor that policy then denies (the zombie built-in; doc-auth-per-app-standards
    "one definition of active").
    """
    return bool(getattr(user, "is_active", False)) and getattr(user, "deactivated_at", None) is None


def _evaluate(caller_context: CallerContext | None, capability: str) -> None:
    """Raise a typed AuthzError if the capability is not granted; else return None.

    Does not log — shared by the raising `authorize()` and the silent `can()`.
    """
    if caps.get_capability(capability) is None:
        raise UnknownCapability(f"unknown capability: {capability!r}")

    user = caller_context.user if caller_context is not None else None
    if user is None:
        raise MissingActor(f"no named actor for capability {capability!r}")

    if not is_actor_active(user):
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

    The backstop is stateless (req-tap-auth-policy-8): a successful authorize
    records nothing. On denial, emits a structured security log.
    """
    try:
        _evaluate(caller_context, capability)
    except AuthzError as exc:
        _log_denial(caller_context, capability, operation, resource_type, resource, exc.reason)
        raise


def can(
    caller_context: CallerContext | None,
    capability: str,
) -> bool:
    """Non-raising predicate twin of `authorize()` — same evaluation, returns a
    bool instead of raising.

    For non-enforcement uses (hiding a UI control, branching) and for the
    structural backstops, which re-check the actor's capability directly
    (req-tap-auth-policy-8). Not a substitute for `authorize()` at a primary
    mutation/read gate: `authorize()` raises a typed denial and emits the security
    log; `can()` is silent.
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
