"""TAP Web views."""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def home(request: HttpRequest) -> HttpResponse:
    """TAP home page."""
    return render(request, "tap_web/home.html")
