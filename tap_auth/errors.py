"""Typed authorization errors (req-tap-auth-policy-3).

`tap_auth.policy.authorize()` raises these on denial/error. Edge layers (API,
web) translate them to 403 or appropriate user-facing pages. They form one
taxonomy shared by service-boundary denials and (later) AuthN-edge login
denials, so attribution is consistent everywhere.

Note: the defect-class `unguarded_operation` error (the on-by-default backstop
for an operation that committed without an authorize() decision) is a *separate*
category — a code-level flaw, not an authorization denial — and lands with the
enforcement backstop. It is the first concrete `code` Flaw under
spec-tap-flaw-v0; see req-tap-auth-policy On By Default.
"""

from __future__ import annotations


class AuthzError(Exception):
    """Base class for all tap_auth authorization errors.

    Carries a stable machine-readable ``reason`` code so callers and logs can
    branch on the denial kind without string-matching the message.
    """

    reason: str = "authz_error"

    def __init__(self, message: str = "", *, reason: str | None = None) -> None:
        if reason is not None:
            self.reason = reason
        super().__init__(message or self.reason)


class MissingActor(AuthzError):
    """No named actor on the CallerContext at a point that requires one.

    The no-`User=None` contract (req-tap-auth-actor-model): a public service
    operation must be attributable to a named actor.
    """

    reason = "missing_actor"


class InactiveActor(AuthzError):
    """The actor exists but is inactive/deactivated — treated as a denial."""

    reason = "inactive_actor"


class UnknownCapability(AuthzError):
    """A capability name not present in the canonical registry was requested.

    Fails closed at runtime (req-tap-auth-capabilities-6): an unknown capability
    is a programming error, never an implicit allow.
    """

    reason = "unknown_capability"


class CapabilityDenied(AuthzError):
    """The actor is named and active but lacks the required capability."""

    reason = "capability_denied"


class ActorKindNotAllowed(AuthzError):
    """The actor's kind is not permitted for this operation."""

    reason = "actor_kind_not_allowed"


class UnguardedOperation(Exception):
    """A mutation or read reached its commit/return point with NO authorize()
    decision recorded — a code-level defect, NOT an authorization denial.

    This is the on-by-default backstop (req-tap-auth-policy On By Default): the
    system is structurally enforced so a developer who forgets to gate an
    operation gets a loud, distinct failure rather than a silent open door. It is
    deliberately separate from the AuthzError taxonomy because it is an internal
    wiring flaw (a 500-class defect), not a 403 denial — conflating them would
    hide a real bug behind a routine denial log.

    It is the first concrete `code` Flaw under spec-tap-flaw-v0 (flaw_class=code,
    flaw_tags=[security]); full Flaw-mechanism emission is layered in later, but
    the distinct error type + loud logging is the foundation.

    Behavior is the same in every mode — the operation fails closed (does not
    commit / does not return data). `TAP_TEST_MODE` only raises the volume by
    surfacing the unguarded callsite for CI; production fails closed and logs.
    """

    def __init__(self, message: str, *, callsite: str = "") -> None:
        self.callsite = callsite
        super().__init__(message)
