"""
TAP URL Configuration
=============================================================================
Top-level URL routing for the TAP platform.

URL structure:
    /admin/         - Django admin interface
    /api/v1/...     - API endpoints (added when tap_api is scaffolded)
    /               - Web interface (added when tap_web is scaffolded)
"""

from django.contrib import admin
from django.urls import path

urlpatterns = [
    # Django's built-in admin interface
    # Provides CRUD for models registered with admin.site.register()
    path("admin/", admin.site.urls),
]
