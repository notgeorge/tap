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

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from django.http import HttpRequest, HttpResponse, HttpResponseForbidden

from tap_auth.errors import AuthzError
from tap_grid.caller_context import CallerContext, get_caller_context, set_caller_context

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

logger = logging.getLogger(__name__)


class CallerContextMiddleware:
    """Bind a CallerContext from request.user for the request lifecycle, and
    translate an authorization denial that escapes a web view into a 403."""

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

    def process_exception(self, request: HttpRequest, exception: Exception) -> HttpResponse | None:
        """Translate a tap_auth authorization denial escaping a web view into a
        403 (req-tap-auth-policy: web layers translate denials to a 403 / no-access
        response). A branded no-access page is allauth-phase work; v1 returns a
        plain 403. `unguarded_operation` is NOT an AuthzError and stays a 500 — it
        is an internal defect, not a denial."""
        if isinstance(exception, AuthzError):
            logger.warning("[a6b7] web authz denied: reason=%s path=%s", exception.reason, request.path)
            return HttpResponseForbidden(f"Forbidden ({exception.reason}). You do not have access to this resource.")
        return None
