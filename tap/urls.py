"""
TAP URL Configuration

URL structure:
    /admin/         Django admin interface
    /api/...        Versioned API — see tap_api/urls.py
    /auth/...       Authentication (login/logout/OIDC) — see tap_auth/urls.py
    /viz/...        Visualization views
    /               Web interface (catch-all — must come last)
"""

from django.contrib import admin
from django.contrib.staticfiles.storage import staticfiles_storage
from django.urls import include, path
from django.views.generic.base import RedirectView

from tap.health import health_view

urlpatterns = [
    path("favicon.ico", RedirectView.as_view(url=staticfiles_storage.url("tap_web/favicon.ico"), permanent=True)),
    # Core health probe — real-backend db/cache/queue round-trip, JSON, 200/503.
    # Mounted here (not in an app) because it is instance-level infrastructure;
    # must precede the tap_web catch-all. See tap/health.py.
    path("healthz", health_view, name="healthz"),
    path("admin/", admin.site.urls),
    path("api/", include("tap_api.urls")),
    # Auth routes (login/logout/OIDC) owned by tap_auth, mounted under /auth/
    # rather than allauth's default /accounts/ (req-tap-auth-app-3). Must precede
    # the tap_web catch-all (path("") matches everything).
    path("auth/", include("tap_auth.urls")),
    # viz must come before the tap_web catch-all (path("") matches everything)
    path("viz/", include("tap_viz.urls")),
    path("", include("tap_web.urls")),
]
