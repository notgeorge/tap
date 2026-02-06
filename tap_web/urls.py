"""TAP Web URL configuration."""

from django.urls import path

from tap_web import views

urlpatterns = [
    path("", views.home, name="home"),
]
