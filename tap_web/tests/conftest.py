"""Shared tap_web test fixtures.

tap_web's object-editor / viewer feature is exercised against a tap_web-OWNED
typed-editor fixture rather than any plugin's editor. The node vocabulary comes
from grid_fixtures (the neutral core-test node/edge vocabulary), but the typed
editor under test — descriptor, form, and custom template — belongs to tap_web,
because the typed-editor mechanism is a tap_web feature. This keeps tap_web's
web-feature tests self-owned and decoupled from lotr (or any plugin).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from django import forms

from tap_web.editor import EditorDescriptor

if TYPE_CHECKING:
    from django.forms import BaseForm
    from django.http import HttpRequest

# The neutral grid_fixtures node type the fixture editor is registered against.
FIXTURE_EDITOR_ENTITY_TYPE = "grid_fixtures__constrained_source"


class FixtureObjectEditForm(forms.Form):
    """Edit form for the tap_web object-editor fixture (entity name + description)."""

    name = forms.CharField(max_length=255, strip=True, help_text="Canonical name.")
    description = forms.CharField(
        required=False,
        strip=True,
        widget=forms.Textarea(attrs={"rows": 4}),
    )


class FixtureObjectEditorDescriptor(EditorDescriptor):
    """tap_web-owned typed editor for the grid_fixtures constrained-source node.

    Stands in for a plugin-supplied editor so the object-editor/viewer tests can
    assert typed-editor behavior (custom template inclusion, form validation,
    service-layer save) without reaching into a plugin.
    """

    entity_type = FIXTURE_EDITOR_ENTITY_TYPE
    form_class = FixtureObjectEditForm
    editor_template = "tap_web/tests/object_editor_fixture.html"

    def get_editor_initial(self, obj: Any) -> dict[str, Any]:
        return {"name": obj.entity.name, "description": obj.description or ""}

    def handle_save(self, form: BaseForm, obj: Any, request: HttpRequest) -> Any:
        """Persist through the service layer (patch_node carries grid.write/FLIP/provenance)."""
        from tap_grid.services import patch_node

        cleaned = form.cleaned_data
        patch_node(
            target=obj.entity.pk,
            payload={"name": cleaned["name"], "description": cleaned.get("description", "")},
        )
        obj.refresh_from_db()
        return obj


@pytest.fixture
def fixture_object_editor():
    """Register the tap_web-owned typed editor for the duration of a test.

    Registry-isolated: registers on entry, restores the prior state on exit so
    no global editor registration leaks between tests.
    """
    from tap_web.registry import _editor_registry, register_editor

    prior = _editor_registry.get(FIXTURE_EDITOR_ENTITY_TYPE)
    register_editor(FixtureObjectEditorDescriptor())
    try:
        yield
    finally:
        if prior is None:
            _editor_registry.pop(FIXTURE_EDITOR_ENTITY_TYPE, None)
        else:
            _editor_registry[FIXTURE_EDITOR_ENTITY_TYPE] = prior
