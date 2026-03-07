"""TAP API URL configuration.

Mounts versioned API instances and redirects unversioned /api/... requests
to the current latest version. Adding a future version is a one-line change here.
"""

from django.urls import path
from django.views.generic import RedirectView

from tap_api.api import api

urlpatterns = [
    path("v1/", api.urls),
    path("<path:resource>", RedirectView.as_view(url="/api/v1/%(resource)s")),
    path("", RedirectView.as_view(url="/api/v1/")),
]
