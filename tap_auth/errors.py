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
