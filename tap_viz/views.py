"""tap_viz views — Graph viewer and layout maker."""

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render

from tap_viz.models import Layout


def graph_view(request: HttpRequest, layout_id: str) -> HttpResponse:
    """Display a read-only Cytoscape graph for a saved layout."""
    try:
        layout = Layout.objects.select_related("entity").get(entity_id=layout_id)
    except Layout.DoesNotExist as err:
        raise Http404("Layout not found") from err
    return render(request, "tap_viz/graph.html", {"layout": layout})


def layout_maker(request: HttpRequest) -> HttpResponse:
    """Layout editor page (stub for v0)."""
    return render(request, "tap_viz/layout_maker.html")
