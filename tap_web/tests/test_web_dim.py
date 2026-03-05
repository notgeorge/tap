"""Tests for req-web-page-dim: Web Dimension.

Covers:
  req-web-page-dim — All tap_web nodes and web-origin edges carry {"tap.graph": "web"}
"""

import pytest

from tap_grid.models import Edge
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


# ---------------------------------------------------------------------------
# req-web-page-dim-5: Web edges carry web dimension via registered default_dimensions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWebEdgeDimensions:
    """USES_PANEL and USES_LANDING_PAGE edges get {"tap.graph": "web"} on create."""

    def test_uses_panel_edge_gets_web_dimension(self):
        """USES_PANEL edge backing Entity has tap.graph=web (dim-5)."""
        page = Page.objects.create()
        panel = Panel.objects.create()
        edge = Edge.objects.create(
            from_entity=page.entity,
            to_entity=panel.entity,
            edge_type="USES_PANEL",
        )
        assert edge.entity.dimensions == {"tap.graph": "web"}

    def test_uses_landing_page_edge_gets_web_dimension(self):
        """USES_LANDING_PAGE edge backing Entity has tap.graph=web (dim-5)."""
        lp = LandingPage.objects.create()
        page = Page.objects.create()
        edge = Edge.objects.create(
            from_entity=lp.entity,
            to_entity=page.entity,
            edge_type="USES_LANDING_PAGE",
        )
        assert edge.entity.dimensions == {"tap.graph": "web"}
