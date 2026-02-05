"""
TAP URL Configuration
=============================================================================
Top-level URL routing for the TAP platform.

URL structure:
    /admin/         - Django admin interface
    /media/icons/   - Secure icon serving (authentication required)
    /api/v1/...     - API endpoints (added when tap_api is scaffolded)
    /               - Web interface (added when tap_web is scaffolded)
"""

from django.contrib import admin
from django.urls import path

from tap_core.views import serve_icon

urlpatterns = [
    # Django's built-in admin interface
    # Provides CRUD for models registered with admin.site.register()
    path("admin/", admin.site.urls),
    # Secure icon serving for uploaded icons
    # Requires authentication and performs security checks
    path("media/icons/<path:path>", serve_icon, name="serve_icon"),
]
