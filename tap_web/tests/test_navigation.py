"""Tests for the breadcrumb helper + nav-index endpoint.

Covers req-web-nav-auto-parent (URL → breadcrumb decomposition; registered
vs. unregistered prefix handling) and req-web-nav-index-endpoint (the
machine-readable nav index's schema and population).
"""

from __future__ import annotations

import pytest
from django.test import Client

from tap_web.models import Page
from tap_web.navigation import BreadcrumbSegment, build_breadcrumb

# Pages require a valid layout to pass model-level validation. These tests
# don't care about layout content; the helpers only read `slug` and `name`.
_MINIMAL_LAYOUT = {
    "columns": {"col-1": {"width": "1fr", "rows": {"row-1": {"panel-id": "x"}}}}
}


def _create_page(name: str, slug: str, description: str = "") -> Page:
    return Page.objects.create(
        name=name, slug=slug, description=description, layout=_MINIMAL_LAYOUT
    )


@pytest.mark.django_db
class TestBuildBreadcrumb:
    """Decomposition of URL paths into BreadcrumbSegment chains."""

    def test_home_returns_single_segment(self):
        segments = build_breadcrumb("/")
        assert len(segments) == 1
        assert segments[0].is_home is True
        assert segments[0].is_current is True
        assert segments[0].url == "/"

    def test_single_segment_path_has_home_plus_one(self):
        _create_page("Samsite", "/samsite")
        segments = build_breadcrumb("/samsite")
        assert len(segments) == 2
        assert segments[0].is_home is True
        assert segments[0].is_current is False
        assert segments[1].label == "Samsite"
        assert segments[1].is_current is True
        assert segments[1].is_registered is True

    def test_two_segment_path_marks_last_current(self):
        _create_page("Samsite", "/samsite")
        _create_page("Samsite Compliance", "/samsite/compliance")
        segments = build_breadcrumb("/samsite/compliance")
        labels = [s.label for s in segments]
        assert labels == ["", "Samsite", "Samsite Compliance"]
        assert [s.is_current for s in segments] == [False, False, True]

    def test_unregistered_prefix_renders_unclickable(self):
        """A URL prefix with no registered Page renders as title-cased plain text."""
        # Only register the LEAF, not the intermediate.
        _create_page("Final Page", "/foo/bar/final-page")
        segments = build_breadcrumb("/foo/bar/final-page")
        # Segments: [home, foo, bar, final-page]
        assert len(segments) == 4
        assert segments[1].label == "Foo"  # title-cased slug
        assert segments[1].is_registered is False
        assert segments[2].label == "Bar"
        assert segments[2].is_registered is False
        assert segments[3].label == "Final Page"
        assert segments[3].is_registered is True
        assert segments[3].is_current is True

    def test_trailing_slash_normalized(self):
        _create_page("Samsite", "/samsite")
        with_slash = build_breadcrumb("/samsite/")
        without_slash = build_breadcrumb("/samsite")
        assert [s.url for s in with_slash] == [s.url for s in without_slash]
        assert [s.label for s in with_slash] == [s.label for s in without_slash]

    def test_dash_in_slug_title_cased_when_unregistered(self):
        segments = build_breadcrumb("/my-cool-page")
        # No Page registered → renders the slug title-cased.
        assert segments[1].label == "My Cool Page"
        assert segments[1].is_registered is False

    def test_underscore_in_slug_title_cased_when_unregistered(self):
        segments = build_breadcrumb("/my_cool_page")
        assert segments[1].label == "My Cool Page"

    def test_lookup_is_batched_in_one_query(self, django_assert_num_queries):
        """All Page lookups happen in a single batched query."""
        _create_page("A", "/a")
        _create_page("B", "/a/b")
        _create_page("C", "/a/b/c")
        with django_assert_num_queries(1):
            build_breadcrumb("/a/b/c")


@pytest.mark.django_db
class TestNavIndexEndpoint:
    """The `/__nav-index.json` endpoint exposes the platform's nav surface."""

    def test_returns_200(self):
        response = Client().get("/__nav-index.json")
        assert response.status_code == 200

    def test_response_is_json(self):
        response = Client().get("/__nav-index.json")
        assert response["Content-Type"].startswith("application/json")
        payload = response.json()
        assert "version" in payload
        assert "generated_at" in payload
        assert "pages" in payload
        assert isinstance(payload["pages"], list)

    def test_enumerates_registered_pages(self):
        _create_page("Alpha", "/alpha")
        _create_page("Beta", "/beta")
        response = Client().get("/__nav-index.json")
        urls = {p["url"] for p in response.json()["pages"]}
        assert "/alpha" in urls
        assert "/beta" in urls

    def test_each_page_carries_breadcrumb(self):
        _create_page("Samsite", "/samsite")
        _create_page("Samsite Compliance", "/samsite/compliance")
        response = Client().get("/__nav-index.json")
        entry = next(p for p in response.json()["pages"] if p["url"] == "/samsite/compliance")
        assert "breadcrumb" in entry
        bc = entry["breadcrumb"]
        # Each segment is {label, url}; the home segment has empty label
        # (consumers render the product mark for it).
        assert bc[0] == {"label": "", "url": "/"}
        assert bc[1] == {"label": "Samsite", "url": "/samsite"}
        assert bc[2] == {"label": "Samsite Compliance", "url": "/samsite/compliance"}

    def test_schema_keys_match_spec(self):
        _create_page("A", "/a", description="d")
        response = Client().get("/__nav-index.json")
        payload = response.json()
        # Top-level keys per spec-web-navigation §Machine-Readable Nav Index.
        assert payload["version"] == "0"
        # Each entry has url, name, description, breadcrumb.
        entry = next(p for p in payload["pages"] if p["url"] == "/a")
        assert set(entry.keys()) == {"url", "name", "description", "breadcrumb"}
        assert entry["description"] == "d"
