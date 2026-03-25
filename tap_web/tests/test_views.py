"""Tests for tap_web views."""

import pytest
from django.test import Client

from tap_grid.models import Entity


@pytest.mark.django_db
class TestLandingView:
    """Root / uses setup placeholder when no LandingPage is configured."""

    def test_root_returns_200(self):
        client = Client()
        response = client.get("/")
        assert response.status_code == 200

    def test_root_shows_setup_placeholder_without_landing_page(self):
        client = Client()
        response = client.get("/")
        assert "tap_web/setup_placeholder.html" in [t.name for t in response.templates]

    def test_root_placeholder_contains_admin_link(self):
        client = Client()
        response = client.get("/")
        assert b"/admin/" in response.content


@pytest.mark.django_db
class TestObjectEditorView:
    """Generic /object/<type>/<slug>--<uuid>/edit/ editor shell for registered entity types."""

    def _make_character(self, name: str = "Gandalf") -> tuple[object, str]:
        from plugins.lotr.models import Character
        from tap_flip.batch.service import batch_context

        entity = Entity.objects.create(entity_type="character", name=name)
        with batch_context(source="test:setup"):
            char = Character.objects.create(entity=entity, title="The Grey", bio="A wizard.")
        url_id = f"{name.lower().replace(' ', '-')}--{entity.pk}"
        return char, url_id

    def test_get_returns_200(self):
        _, url_id = self._make_character()
        response = Client().get(f"/object/character/{url_id}/edit/")
        assert response.status_code == 200

    def test_get_uses_editor_template(self):
        _, url_id = self._make_character()
        response = Client().get(f"/object/character/{url_id}/edit/")
        assert "tap_web/editor.html" in [t.name for t in response.templates]

    def test_get_includes_typed_editor_template(self):
        _, url_id = self._make_character()
        response = Client().get(f"/object/character/{url_id}/edit/")
        template_names = [t.name for t in response.templates]
        assert "lotr/character_editor.html" in template_names

    def test_get_renders_character_name(self):
        _, url_id = self._make_character(name="Frodo Baggins")
        response = Client().get(f"/object/character/{url_id}/edit/")
        assert b"Frodo Baggins" in response.content

    def test_post_saves_name(self):
        char, url_id = self._make_character(name="Old Name")
        Client().post(f"/object/character/{url_id}/edit/", {"name": "New Name", "title": "", "bio": ""})
        char.entity.refresh_from_db()
        assert char.entity.name == "New Name"

    def test_post_saves_bio(self):
        char, url_id = self._make_character()
        Client().post(f"/object/character/{url_id}/edit/", {"name": "Gandalf", "title": "", "bio": "Updated bio."})
        char.refresh_from_db()
        assert char.bio == "Updated bio."

    def test_post_redirects_on_success(self):
        _, url_id = self._make_character()
        response = Client().post(f"/object/character/{url_id}/edit/", {"name": "Gandalf", "title": "", "bio": ""})
        assert response.status_code == 302

    def test_post_empty_name_rerenders_with_errors(self):
        _, url_id = self._make_character()
        response = Client().post(f"/object/character/{url_id}/edit/", {"name": "", "title": "", "bio": ""})
        assert response.status_code == 200
        assert b"tap_web/editor.html" in bytes(str([t.name for t in response.templates]), "utf-8")

    def test_unknown_entity_type_returns_404(self):
        response = Client().get("/object/unknown-type/some-slug--00000000-0000-0000-0000-000000000000/edit/")
        assert response.status_code == 404

    def test_nonexistent_entity_returns_404(self):
        response = Client().get("/object/character/x--00000000-0000-0000-0000-000000000000/edit/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestObjectViewerView:
    """Generic /object/<type>/<slug>--<uuid>/ viewer shell."""

    def _make_character(self, name: str = "Aragorn") -> tuple[object, str]:
        from plugins.lotr.models import Character
        from tap_flip.batch.service import batch_context

        entity = Entity.objects.create(entity_type="character", name=name)
        with batch_context(source="test:setup"):
            char = Character.objects.create(entity=entity, title="King", bio="Heir of Isildur.")
        url_id = f"{name.lower().replace(' ', '-')}--{entity.pk}"
        return char, url_id

    def test_get_returns_200(self):
        _, url_id = self._make_character()
        response = Client().get(f"/object/character/{url_id}/")
        assert response.status_code == 200

    def test_get_uses_viewer_template(self):
        _, url_id = self._make_character()
        response = Client().get(f"/object/character/{url_id}/")
        assert "tap_web/viewer.html" in [t.name for t in response.templates]

    def test_get_renders_character_name(self):
        _, url_id = self._make_character(name="Legolas")
        response = Client().get(f"/object/character/{url_id}/")
        assert b"Legolas" in response.content

    def test_get_shows_edit_link(self):
        _, url_id = self._make_character()
        response = Client().get(f"/object/character/{url_id}/")
        assert b"/edit/" in response.content

    def test_unknown_entity_type_returns_404(self):
        response = Client().get("/object/unknown-type/some-slug--00000000-0000-0000-0000-000000000000/")
        assert response.status_code == 404
