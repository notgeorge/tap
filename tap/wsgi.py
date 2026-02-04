"""
WSGI config for TAP project.

Exposes the WSGI callable as a module-level variable named 'application'.
WSGI (Web Server Gateway Interface) is the standard for serving Python web apps.
In production, a WSGI server like Gunicorn runs this.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tap.settings")

application = get_wsgi_application()
