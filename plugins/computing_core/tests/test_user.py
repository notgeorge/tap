"""Domain-specific tests for the Computing Core User model.

The User node is the generic human-actor primitive (req-computing-core-models-5).
These tests cover service-layer creation, required-field validation, the
display-name projection onto Entity.name, and default dimensions.
"""

import pytest

import tap_plugin.computing_core.models as computing  # noqa: F401 — trigger model registration
from tap_grid.models import Entity
from tap_grid.registry import get_model_class
from tap_grid.services import create_node


def _create(type_slug: str, payload: dict):
    """Create a node via the service layer and return the typed domain object."""
    result = create_node(type_slug, payload)
    assert result.success, f"create_node failed: {result.errors}"
    entity = Entity.objects.get(pk=result.entity_id)
    model_cls = get_model_class(type_slug)
    return model_cls.objects.get(entity=entity)


@pytest.mark.django_db
class TestUserCreation:
    def test_create_via_service_layer(self):
        node = _create("computing_core__user", {"name": "Ada Lovelace", "description": "First programmer."})
        assert node.name == "Ada Lovelace"
        assert node.description == "First programmer."

    def test_description_defaults_to_empty(self):
        node = _create("computing_core__user", {"name": "Grace Hopper"})
        assert node.description == ""

    def test_name_required_on_create(self):
        result = create_node("computing_core__user", {"description": "no name given"})
        assert not result.success
        assert result.errors


@pytest.mark.django_db
class TestUserDisplayProjection:
    def test_entity_name_synced_from_get_name(self):
        node = _create("computing_core__user", {"name": "Alan Turing"})
        node.entity.refresh_from_db()
        assert node.entity.name == "Alan Turing"

    def test_entity_name_resynced_on_save(self):
        node = _create("computing_core__user", {"name": "Alan Turing"})
        node.name = "Alan M. Turing"
        node.save()
        node.entity.refresh_from_db()
        assert node.entity.name == "Alan M. Turing"


@pytest.mark.django_db
class TestUserDimensions:
    def test_default_dimensions_applied(self):
        node = _create("computing_core__user", {"name": "Margaret Hamilton"})
        assert node.entity.dimensions.get("tap.computing") == "identity"
