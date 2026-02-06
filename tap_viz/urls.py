"""tap_viz URL configuration."""

from django.urls import path

from tap_viz import views

app_name = "tap_viz"

urlpatterns = [
    path("graph/<str:layout_id>/", views.graph_view, name="graph"),
    path("layout-maker/", views.layout_maker, name="layout_maker"),
]
