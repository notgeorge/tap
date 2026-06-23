"""Tests for tap_web views."""

from collections.abc import Generator
from contextlib import contextmanager

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client

from tap_grid.batch import create_batch
from tap_grid.caller_context import CallerContext, get_caller_context, set_caller_context
from tap_grid.models import Entity


def _admin_client() -> Client:
    """Test client logged in as a tap_admin member, so graph-backed object views
    are authorized under the on-by-default service-boundary enforcement
    (req-tap-auth-service-boundary). tap_admin is created by the session auth seed.
    """
    user = get_user_model().objects.create_user(username="views-admin", password="x")
    user.groups.add(Group.objects.get(name="tap_admin"))
    client = Client()
    client.force_login(user)
    return client


@contextmanager
def _batch_ctx(source: str = "test") -> Generator[str]:
    """Create a Batch entity and set CallerContext for the duration (test helper)."""
    batch = create_batch(source=source)
    batch_id = str(batch.entity.id)
    prev = get_caller_context()
    set_caller_context(CallerContext(user=get_caller_context().user, batch_id=batch_id))
    try:
        yield batch_id
    finally:
        set_caller_context(prev)


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


@pytest.mark.django_db(transaction=True, databases=["default", "search_readonly"])
class TestObjectEditorView:
    """Generic /object/<type>/<slug>--<uuid>/edit/ editor shell for registered entity types."""

    def _make_character(self, name: str = "Gandalf") -> tuple[object, str]:
        from plugins.lotr.models import Character

        entity = Entity.objects.create(entity_type="character", name=name)
        with _batch_ctx(source="test:setup"):
            char = Character.objects.create(entity=entity, name=name, bio="A wizard.")
        url_id = f"{name.lower().replace(' ', '-')}--{entity.pk}"
        return char, url_id

    def test_get_returns_200(self):
        _, url_id = self._make_character()
        response = _admin_client().get(f"/object/character/{url_id}/edit/")
        assert response.status_code == 200

    def test_get_uses_synthetic_page(self):
        _, url_id = self._make_character()
        response = _admin_client().get(f"/object/character/{url_id}/edit/")
        assert "tap_web/synthetic_page.html" in [t.name for t in response.templates]

    def test_get_includes_editor_panel(self):
        _, url_id = self._make_character()
        response = _admin_client().get(f"/object/character/{url_id}/edit/")
        template_names = [t.name for t in response.templates]
        assert "tap_web/panels/editor_panel.html" in template_names

    def test_get_includes_typed_editor_template(self):
        _, url_id = self._make_character()
        response = _admin_client().get(f"/object/character/{url_id}/edit/")
        template_names = [t.name for t in response.templates]
        assert "lotr/character_editor.html" in template_names

    def test_get_renders_character_name(self):
        _, url_id = self._make_character(name="Frodo Baggins")
        response = _admin_client().get(f"/object/character/{url_id}/edit/")
        assert b"Frodo Baggins" in response.content

    def test_post_saves_name(self):
        char, url_id = self._make_character(name="Old Name")
        _admin_client().post(f"/object/character/{url_id}/edit/", {"name": "New Name", "title": "", "bio": ""})
        char.entity.refresh_from_db()
        assert char.entity.name == "New Name"

    def test_post_saves_bio(self):
        char, url_id = self._make_character()
        _admin_client().post(
            f"/object/character/{url_id}/edit/", {"name": "Gandalf", "title": "", "bio": "Updated bio."}
        )
        char.refresh_from_db()
        assert char.bio == "Updated bio."

    def test_post_redirects_on_success(self):
        _, url_id = self._make_character()
        response = _admin_client().post(
            f"/object/character/{url_id}/edit/", {"name": "Gandalf", "title": "", "bio": ""}
        )
        assert response.status_code == 302

    def test_post_empty_name_rerenders_with_errors(self):
        _, url_id = self._make_character()
        response = _admin_client().post(f"/object/character/{url_id}/edit/", {"name": "", "title": "", "bio": ""})
        assert response.status_code == 200
        assert "tap_web/synthetic_page.html" in [t.name for t in response.templates]

    def test_unknown_entity_type_returns_404(self):
        response = _admin_client().get("/object/unknown-type/some-slug--00000000-0000-0000-0000-000000000000/edit/")
        assert response.status_code == 404

    def test_nonexistent_entity_returns_404(self):
        response = _admin_client().get("/object/character/x--00000000-0000-0000-0000-000000000000/edit/")
        assert response.status_code == 404


@pytest.mark.django_db(transaction=True, databases=["default", "search_readonly"])
class TestObjectViewerView:
    """Generic /object/<type>/<slug>--<uuid>/ viewer shell."""

    def _make_character(self, name: str = "Aragorn") -> tuple[object, str]:
        from plugins.lotr.models import Character

        entity = Entity.objects.create(entity_type="character", name=name)
        with _batch_ctx(source="test:setup"):
            char = Character.objects.create(entity=entity, name=name, bio="Heir of Isildur.")
        url_id = f"{name.lower().replace(' ', '-')}--{entity.pk}"
        return char, url_id

    def test_get_returns_200(self):
        _, url_id = self._make_character()
        response = _admin_client().get(f"/object/character/{url_id}/")
        assert response.status_code == 200

    def test_get_uses_synthetic_page(self):
        _, url_id = self._make_character()
        response = _admin_client().get(f"/object/character/{url_id}/")
        assert "tap_web/synthetic_page.html" in [t.name for t in response.templates]

    def test_get_includes_viewer_panel(self):
        _, url_id = self._make_character()
        response = _admin_client().get(f"/object/character/{url_id}/")
        template_names = [t.name for t in response.templates]
        assert "tap_web/panels/viewer_panel.html" in template_names

    def test_get_renders_character_name(self):
        _, url_id = self._make_character(name="Legolas")
        response = _admin_client().get(f"/object/character/{url_id}/")
        assert b"Legolas" in response.content

    def test_get_shows_edit_link(self):
        _, url_id = self._make_character()
        response = _admin_client().get(f"/object/character/{url_id}/")
        assert b"/edit/" in response.content

    def test_viewer_includes_graph_panel(self):
        _, url_id = self._make_character()
        response = _admin_client().get(f"/object/character/{url_id}/")
        template_names = [t.name for t in response.templates]
        assert "tap_viz/panels/graph_panel.html" in template_names

    def test_viewer_includes_flip_panel(self):
        _, url_id = self._make_character()
        response = _admin_client().get(f"/object/character/{url_id}/")
        template_names = [t.name for t in response.templates]
        assert "tap_web/panels/flip_panel.html" in template_names

    def test_unknown_entity_type_returns_404(self):
        response = _admin_client().get("/object/unknown-type/some-slug--00000000-0000-0000-0000-000000000000/")
        assert response.status_code == 404


def _no_cap_client() -> Client:
    """Authenticated client whose user holds no capability bundle."""
    user = get_user_model().objects.create_user(username="views-nocap", password="x")
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db(transaction=True, databases=["default", "search_readonly"])
class TestObjectViewReadGate:
    """Graph-backed object views deny unauthorized callers (req-tap-auth-service-boundary).

    The web edge translates an authorization denial to a 403 via
    CallerContextMiddleware.process_exception. Both an anonymous request (no
    actor → MissingActor) and an authenticated-but-no-capability request
    (CapabilityDenied) are denied — passing authentication is not permission. The
    gate runs before the entity is loaded, so a denied caller cannot tell an
    existing object from a missing one.
    """

    def _make_character(self, name: str = "Boromir") -> str:
        from plugins.lotr.models import Character

        entity = Entity.objects.create(entity_type="character", name=name)
        with _batch_ctx(source="test:setup"):
            Character.objects.create(entity=entity, name=name, bio="Of Gondor.")
        return f"{name.lower()}--{entity.pk}"

    def test_anonymous_object_view_denied_403(self):
        url_id = self._make_character()
        response = Client().get(f"/object/character/{url_id}/")
        assert response.status_code == 403

    def test_anonymous_object_edit_denied_403(self):
        url_id = self._make_character()
        response = Client().get(f"/object/character/{url_id}/edit/")
        assert response.status_code == 403

    def test_no_cap_object_view_denied_403(self):
        url_id = self._make_character()
        response = _no_cap_client().get(f"/object/character/{url_id}/")
        assert response.status_code == 403

    def test_no_cap_object_edit_denied_403(self):
        url_id = self._make_character()
        response = _no_cap_client().get(f"/object/character/{url_id}/edit/")
        assert response.status_code == 403

    def test_denied_before_existence_check_no_leak(self):
        """A no-cap caller gets 403 for a NON-existent object too — same as for an
        existing one — so existence is not leaked through the status code."""
        missing = "ghost--00000000-0000-0000-0000-000000000000"
        response = _no_cap_client().get(f"/object/character/{missing}/")
        assert response.status_code == 403
