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

import requests
from django.conf import settings
from django.contrib.auth.middleware import LoginRequiredMiddleware
from django.http import HttpRequest, HttpResponse, HttpResponseBase, HttpResponseForbidden
from django.shortcuts import render

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
        """Translate an auth-edge exception escaping a web view into a branded,
        actionable response rather than a raw 500/traceback:

        - a tap_auth authorization denial (`AuthzError`) → 403 no-access
          (req-tap-auth-policy: web layers translate denials to a 403);
        - a transient identity-provider reachability failure DURING the OAuth
          login/callback flow (`requests.RequestException` on an `/auth/` path) →
          a retryable 503 page (req-tap-auth-google-oidc callback hardening).
          allauth's callback fetches the provider discovery doc, exchanges the
          code, and fetches userinfo with `requests`; a network blip there is
          otherwise an uncaught 500 on a load-bearing path.

        Scope is deliberate. `unguarded_operation` is NOT an AuthzError and stays
        a 500 — an internal defect, not a denial. A `RequestException` from any
        non-auth view likewise stays a 500 (a real defect): only the login flow,
        the one place TAP makes outbound IdP calls inside a request, is rescued.

        KNOWN GAP (unrescued, by design until FIPS ships). Under `TAP_FIPS=1`, an
        OIDC login against an IdP signing with a non-approved algorithm (JWS
        `ES256K`, or RSA < 2048) fails inside allauth's `jwtkit.fetch_key ->
        algorithm.from_jwk()` with `cryptography.exceptions.InternalError:
        Unknown OpenSSL error` or `ValueError: Unable to sign/verify with this
        key`. Neither is a `PyJWTError` nor an allauth error type, so it escapes
        both allauth's handler and this one, surfacing as an uncaught 500 with no
        hint that FIPS is the cause. The rescue belongs here, alongside the
        RequestException branch. Design + exact error signatures:
        docs/misc/doc-fips-assessment-record.md sec 5.3."""
        if isinstance(exception, AuthzError):
            logger.warning("[a6b7] web authz denied: reason=%s path=%s", exception.reason, request.path)
            return HttpResponseForbidden(f"Forbidden ({exception.reason}). You do not have access to this resource.")
        if isinstance(exception, requests.RequestException) and request.path.startswith("/auth/"):
            logger.warning(
                "[55c6] identity provider unreachable during login: path=%s error=%s",
                request.path,
                type(exception).__name__,
            )
            response = render(request, "tap_web/auth/provider_unreachable.html", status=503)
            response["Retry-After"] = "10"
            return response
        return None


class TapLoginRequiredMiddleware(LoginRequiredMiddleware):
    """Default-deny login wall (req-tap-auth-service-boundary).

    Subclasses Django's `LoginRequiredMiddleware` so every view requires an
    authenticated session by default, EXCEPT requests whose path starts with a
    prefix in `settings.TAP_LOGIN_EXEMPT_PREFIXES`. Those prefixes each carry
    their own enforcement (the login routes, the API's session_auth → 401, the
    Django admin login, static assets), so applying an HTML login redirect on
    top would either loop or corrupt non-HTML clients.

    A non-exempt anonymous request is redirected to `LOGIN_URL` with `?next=` —
    fail-closed. This is a coarse, request-level gate that complements (never
    replaces) the service-boundary capability checks: passing the wall proves a
    named session exists, not that the actor may read/write the grid.
    """

    def process_view(
        self,
        request: HttpRequest,
        view_func: Callable[..., HttpResponseBase],
        view_args: tuple[object, ...],
        view_kwargs: dict[str, object],
    ) -> HttpResponseBase | None:
        path = request.path_info
        for prefix in getattr(settings, "TAP_LOGIN_EXEMPT_PREFIXES", ()):
            if path.startswith(prefix):
                return None
        return super().process_view(request, view_func, view_args, view_kwargs)
