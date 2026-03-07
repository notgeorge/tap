"""Tests for req-web-page-dim: Web Dimension.

Covers:
  req-web-page-dim — All tap_web nodes and web-origin edges carry {"tap.graph": "web"}
"""

import pytest

from tap_web.models import LandingPage, Page, Panel


# ---------------------------------------------------------------------------
# req-web-page-dim-2 / dim-3: Node types carry web dimension on create
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWebNodeDimensions:
    """tap_web nodes get {"tap.graph": "web"} on the backing Entity at create time."""

    def test_page_gets_web_dimension(self):
        """Page backing Entity has tap.graph=web (dim-2)."""
        page = Page.objects.create()
        assert page.entity.dimensions == {"tap.graph": "web"}

    def test_panel_gets_web_dimension(self):
        """Panel backing Entity has tap.graph=web (dim-2)."""
        panel = Panel.objects.create()
        assert panel.entity.dimensions == {"tap.graph": "web"}

    def test_landing_page_gets_web_dimension(self):
        """LandingPage backing Entity has tap.graph=web (dim-2)."""
        lp = LandingPage.objects.create()
        assert lp.entity.dimensions == {"tap.graph": "web"}

    def test_merge_preserves_web_default(self):
        """Caller-supplied extra keys are merged; tap.graph=web remains (dim-3)."""
        page = Page()
        page._initial_dimensions = {"env": "staging"}
        page.save()
        assert page.entity.dimensions == {"tap.graph": "web", "env": "staging"}
