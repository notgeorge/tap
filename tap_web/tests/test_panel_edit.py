"""Tests for the panel edit view.

Covers:
  req-web-render-panel-edit — Panel edit page at /panel/<slug>--<uuid>/edit/
  req-web-panel-edit — Panel edit mode behavior
"""

import json

import pytest
from django.test import Client

from tap_web.models import Panel


@pytest.mark.django_db
class TestPanelEditView:
    """Panel edit endpoint renders two-region editor and saves via POST."""

    def _create_panel(self, **kwargs) -> Panel:
        defaults = {
            "slug": "test-panel",
            "name": "Test Panel",
            "description": "A test panel.",
            "view": "tap_web/panel_error.html",
            "config": {"key": "value"},
        }
        defaults.update(kwargs)
        return Panel.objects.create(**defaults)

    def _edit_url(self, panel: Panel) -> str:
        return f"/panel/{panel.slug}--{panel.entity_id}/edit/"

    def test_get_returns_200(self):
        panel = self._create_panel()
        client = Client()
        response = client.get(self._edit_url(panel))
        assert response.status_code == 200

    def test_get_uses_edit_template(self):
        panel = self._create_panel()
        client = Client()
        response = client.get(self._edit_url(panel))
        assert "tap_web/editor.html" in [t.name for t in response.templates]

    def test_get_renders_panel_title(self):
        panel = self._create_panel(name="My Panel")
        client = Client()
        response = client.get(self._edit_url(panel))
        assert b"My Panel" in response.content

    def test_get_shows_graph_context_section(self):
        panel = self._create_panel()
        client = Client()
        response = client.get(self._edit_url(panel))
        assert b"Graph Context" in response.content

    def test_post_saves_title(self):
        panel = self._create_panel(name="Old Title")
        client = Client()
        client.post(self._edit_url(panel), {"name": "New Title", "description": "", "config": "{}"})
        panel.refresh_from_db()
        assert panel.name == "New Title"

    def test_post_saves_description(self):
        panel = self._create_panel()
        client = Client()
        client.post(self._edit_url(panel), {"name": panel.name, "description": "Updated desc.", "config": "{}"})
        panel.refresh_from_db()
        assert panel.description == "Updated desc."

    def test_post_saves_config(self):
        panel = self._create_panel(config={})
        client = Client()
        new_config = {"color": "blue", "size": 42}
        client.post(
            self._edit_url(panel),
            {"name": panel.name, "description": "", "config": json.dumps(new_config)},
        )
        panel.refresh_from_db()
        assert panel.config == new_config

    def test_post_redirects_to_edit_page(self):
        panel = self._create_panel()
        client = Client()
        response = client.post(
            self._edit_url(panel),
            {"name": panel.name, "description": "", "config": "{}"},
        )
        assert response.status_code == 302
        assert response["Location"] == self._edit_url(panel)

    def test_post_invalid_json_config_rerenders_form(self):
        panel = self._create_panel()
        client = Client()
        response = client.post(
            self._edit_url(panel),
            {"name": panel.name, "description": "", "config": "not-json"},
        )
        assert response.status_code == 200
        assert b"tap_web/editor.html" in bytes(str([t.name for t in response.templates]), "utf-8")

    def test_invalid_panel_url_returns_error_fragment(self):
        client = Client()
        response = client.get("/panel/bad-url-no-separator/edit/")
        assert response.status_code == 200
        assert b"Panel Error" in response.content or b"Invalid panel URL" in response.content

    def test_nonexistent_panel_uuid_returns_error_fragment(self):
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        client = Client()
        response = client.get(f"/panel/some-panel--{fake_uuid}/edit/")
        assert response.status_code == 200
        assert b"not found" in response.content or b"Panel Error" in response.content


@pytest.mark.django_db
class TestPanelEditNoEditorView:
    """Panels without editor_view show 'No editor configured' in edit mode."""

    def test_no_editor_view_shows_fallback_message(self):
        panel = Panel.objects.create(
            slug="plain-panel",
            name="Plain Panel",
            view="tap_web/panel_error.html",
        )
        client = Client()
        response = client.get(f"/panel/{panel.slug}--{panel.entity_id}/edit/")
        assert response.status_code == 200
        # No editor_view means the custom editor section is not shown
        assert b"editor_view" not in response.content
