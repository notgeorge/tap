"""TAP Web URL configuration.

URL patterns (evaluated in order):
    /panel/<slug>--<uuid>/edit/                Panel editor
    /panel/<slug>--<uuid>/                     Panel HTMX fragment endpoint
    /object/<entity-type>/<slug>--<uuid>/edit/ Generic object editor
    /object/<entity-type>/<slug>--<uuid>/      Generic object viewer
    /                                          Landing page (or placeholder if none configured)
    /<path:page_slug>                          Catch-all dynamic page resolution

The catch-all must come last within this file.
In tap/urls.py, tap_web must be the final include (after admin, api, viz)
because path("") matches any prefix and would shadow other apps' routes.
"""

from django.urls import path

from tap_web import views

urlpatterns = [
    path("panel/<str:panel_url_id>/edit/", views.panel_edit_view, name="panel-edit"),
    path("panel/<str:panel_url_id>/", views.panel_view, name="panel"),
    path("object/<str:entity_type>/<str:object_url_id>/edit/", views.object_edit_view, name="object-edit"),
    path("object/<str:entity_type>/<str:object_url_id>/", views.object_view, name="object-view"),
    path("", views.landing_view, name="landing"),
    # Parameterized pages — path segments become search inputs.
    path(
        "genericom/instance/<uuid:entity_id>",
        views.parameterized_page_view,
        {"page_slug": "genericom/instance"},
        name="genericom-instance",
    ),
    path("<path:page_slug>", views.page_view, name="page"),
]
