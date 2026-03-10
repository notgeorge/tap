"""TAP Web URL configuration.

URL patterns (evaluated in order):
    /panel/<slug>--<uuid>/   Panel HTMX fragment endpoint
    /                        Landing page (or home fallback if none configured)
    /<path:page_slug>        Catch-all dynamic page resolution

The catch-all must come last within this file.
In tap/urls.py, tap_web must be the final include (after admin, api, viz)
because path("") matches any prefix and would shadow other apps' routes.
"""

from django.urls import path

from tap_web import views

urlpatterns = [
    path("panel/<str:panel_url_id>/edit/", views.panel_edit_view, name="panel-edit"),
    path("panel/<str:panel_url_id>/", views.panel_view, name="panel"),
    path("", views.landing_view, name="landing"),
    path("<path:page_slug>", views.page_view, name="page"),
]
