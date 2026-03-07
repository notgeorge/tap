"""
TAP URL Configuration

URL structure:
    /admin/         Django admin interface
    /api/...        Versioned API — see tap_api/urls.py
    /viz/...        Visualization views
    /               Web interface (catch-all — must come last)
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("tap_api.urls")),
    # viz must come before the tap_web catch-all (path("") matches everything)
    path("viz/", include("tap_viz.urls")),
    path("", include("tap_web.urls")),
]
