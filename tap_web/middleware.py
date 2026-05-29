"""Dev-only response middleware."""

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse

_NO_STORE = "no-store, no-cache, must-revalidate, max-age=0"


class DevNoStoreMiddleware:
    """In DEBUG, mark page responses non-cacheable so a reload always re-fetches.

    Complements the ``runserver_nocache`` dev command: that command handles
    ``/static/`` (the StaticFilesHandler serves static BEFORE the middleware stack,
    so middleware can't reach it), while this covers everything that *does* go
    through middleware — the HTML pages and the JSON the panels embed/fetch.
    Together they make a dev reload pick up edits without hard-refreshes or cache
    dances. Pure dev ergonomics; inert whenever ``DEBUG`` is off (i.e. production).
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if settings.DEBUG:
            response["Cache-Control"] = _NO_STORE
        return response
