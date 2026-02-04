"""
ASGI config for TAP project.

Exposes the ASGI callable as a module-level variable named 'application'.
ASGI (Asynchronous Server Gateway Interface) supports async views and WebSockets.
Django Ninja can use this for async API endpoints.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tap.settings")

application = get_asgi_application()
