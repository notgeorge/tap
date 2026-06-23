"""Edge AuthN → actor-context binding middleware (req-tap-auth-service-boundary).

An authenticated HTTP request resolves to a named TAP actor at the edge; the
service boundary then authorizes (req-tap-auth-policy). This middleware binds a
`CallerContext` from `request.user` for the duration of the request and restores
the prior context afterward, so the actor never leaks across requests
(req-tap-auth-logging boundary-clearing).

An unauthenticated request binds a `None`-actor context: the on-by-default
read/write enforcement then denies graph access (the user reaches a no-access
page / 403), per "passing request authentication never implies permission".

The prior context is saved and restored (rather than cleared to None) so that:
  - in production, where each request begins with no context, the prior is None
    and the request still ends clean — no cross-request leak;
  - under test, where an autouse fixture binds the test actor, service calls made
    after a test client request still see that actor.

The authorization ledger is managed by per-operation scopes (the decorators /
`authorized()`), not here.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from django.http import HttpRequest, HttpResponse

from tap_grid.caller_context import CallerContext, get_caller_context, set_caller_context

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


class CallerContextMiddleware:
    """Bind a CallerContext from request.user for the request lifecycle."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        authed = getattr(request.user, "is_authenticated", False)
        user = cast("AbstractUser | None", request.user if authed else None)
        prior = get_caller_context()
        set_caller_context(CallerContext(user=user))
        try:
            return self.get_response(request)
        finally:
            set_caller_context(prior)
