"""
TAP URL Configuration

URL structure:
    /admin/         Django admin interface
    /api/v1/...     Versioned API (Django Ninja)
    /api/...        Redirects to /api/v1/... (latest version alias)
    /               Web interface
"""

from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import include, path

from tap_api.api import api

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", api.urls),
    path("api/<path:resource>", lambda request, resource: HttpResponseRedirect(f"/api/v1/{resource}")),
    path("api/", lambda request: HttpResponseRedirect("/api/v1/")),
    path("", include("tap_web.urls")),
    path("viz/", include("tap_viz.urls")),
]
