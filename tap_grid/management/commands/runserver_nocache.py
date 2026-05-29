"""Dev runserver that tells browsers NOT to cache static assets.

Django's staticfiles dev handler serves ``/static/`` with only ``Last-Modified``
and no ``Cache-Control``, so browsers heuristically cache JS/CSS. While iterating
on projection layout modules — and, worse, their transitive ES ``import``s, which
load by a fixed URL — the browser keeps running stale code, and the only reliable
escape is closing the tab or CDP cache-clears. Under ``runserver`` the
``StaticFilesHandler`` serves static BEFORE the middleware stack, so a
response-header middleware can't reach it; we wrap the handler instead.

This is a SEPARATE command (not a ``runserver`` override) so it doesn't depend on
INSTALLED_APPS command-resolution order: the dev entrypoint invokes it explicitly.
Pure dev ergonomics — production never runs this; it serves static through a real
web server with proper caching. The no-store header only takes effect when the
static handler is active (DEBUG), so it's inert otherwise.
"""

from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.contrib.staticfiles.management.commands.runserver import (
    Command as StaticfilesRunserverCommand,
)


class NoCacheStaticFilesHandler(StaticFilesHandler):
    """StaticFilesHandler that marks every static response non-cacheable."""

    def serve(self, request):
        response = super().serve(request)
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return response


class Command(StaticfilesRunserverCommand):
    help = "runserver with no-store on static assets (dev: always-fresh JS/CSS)."

    def get_handler(self, *args, **options):
        handler = super().get_handler(*args, **options)
        # The staticfiles runserver returns a StaticFilesHandler wrapping the WSGI
        # app when the static handler is active (DEBUG / --insecure). Re-wrap the
        # same inner application with our no-cache variant; otherwise pass through.
        if isinstance(handler, StaticFilesHandler):
            return NoCacheStaticFilesHandler(handler.application)
        return handler
