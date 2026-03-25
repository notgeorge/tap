"""Tests for req-grid-service-schemas: SERVICE_SCHEMAS startup invariants.

Covers:
  - req-grid-service-schemas-1: All concrete BaseModel subclasses must publish SERVICE_SCHEMAS
  - req-grid-service-schemas-2: Missing schemas are ImproperlyConfigured at class-definition time
  - req-grid-service-schemas-3: Schema content spot-checks for Edge and Search
"""

from typing import ClassVar

import jsonschema
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import models

from tap_grid.models import BaseModel, Edge, Search
from plugins.lotr.models import Character


# ---------------------------------------------------------------------------
# Minimal abstract base for test-only concrete models (no table, no CASCADE).
# ---------------------------------------------------------------------------


class _TestBaseModel(BaseModel):
    entity = models.OneToOneField(
        "tap_grid.Entity",
        on_delete=models.DO_NOTHING,
        related_name="+",
    )

    class Meta(BaseModel.Meta):
        abstract = True


# ---------------------------------------------------------------------------
# Startup invariant tests
# ---------------------------------------------------------------------------


class TestServiceSchemasInvariant:
    """req-grid-service-schemas-1/2: startup checks fire at class definition."""

    def test_missing_service_schemas_raises(self):
        """Concrete subclass missing SERVICE_SCHEMAS raises ImproperlyConfigured."""
        with pytest.raises(ImproperlyConfigured, match="SERVICE_SCHEMAS"):

            class _NoSchemas(_TestBaseModel):
                ENTITY_TYPE: ClassVar[str] = "test_no_schemas_xyz"

                class Meta(_TestBaseModel.Meta):
                    managed = False

    def test_missing_required_key_raises(self):
        """SERVICE_SCHEMAS missing 'patch' raises ImproperlyConfigured."""
        with pytest.raises(ImproperlyConfigured, match="'patch'"):

            class _MissingPatch(_TestBaseModel):
                ENTITY_TYPE: ClassVar[str] = "test_missing_patch_xyz"
                SERVICE_SCHEMAS: ClassVar[dict] = {
                    "create": {"type": "object", "additionalProperties": False, "properties": {}},
                    "replace": {"type": "object", "additionalProperties": False, "properties": {}},
                }

                class Meta(_TestBaseModel.Meta):
                    managed = False

    def test_unknown_key_raises(self):
        """SERVICE_SCHEMAS with an unrecognised key raises ImproperlyConfigured."""
        with pytest.raises(ImproperlyConfigured, match="unknown key"):

            class _UnknownKey(_TestBaseModel):
                ENTITY_TYPE: ClassVar[str] = "test_unknown_key_xyz"
                SERVICE_SCHEMAS: ClassVar[dict] = {
                    "create": {"type": "object", "additionalProperties": False, "properties": {}},
                    "patch": {"type": "object", "additionalProperties": False, "properties": {}},
                    "replace": {"type": "object", "additionalProperties": False, "properties": {}},
                    "destroy": {"type": "object"},
                }

                class Meta(_TestBaseModel.Meta):
                    managed = False

    def test_non_dict_value_raises(self):
        """SERVICE_SCHEMAS with a non-dict value raises ImproperlyConfigured."""
        with pytest.raises(ImproperlyConfigured, match="must be a dict"):

            class _BadValue(_TestBaseModel):
                ENTITY_TYPE: ClassVar[str] = "test_bad_value_xyz"
                SERVICE_SCHEMAS: ClassVar[dict] = {
                    "create": "not a dict",  # type: ignore[dict-item]
                    "patch": {"type": "object", "additionalProperties": False, "properties": {}},
                    "replace": {"type": "object", "additionalProperties": False, "properties": {}},
                }

                class Meta(_TestBaseModel.Meta):
                    managed = False

    def test_abstract_intermediate_without_entity_type_exempt(self):
        """Abstract class without ENTITY_TYPE in its own __dict__ is skipped."""

        class _AbstractMiddle(_TestBaseModel):
            class Meta(_TestBaseModel.Meta):
                abstract = True

        # If we get here without ImproperlyConfigured, the invariant was correctly skipped.
        assert not hasattr(_AbstractMiddle, "SERVICE_SCHEMAS") or True  # always passes

    def test_valid_service_schemas_accepted(self):
        """A concrete class with all required keys and dict values is accepted."""

        class _Valid(_TestBaseModel):
            ENTITY_TYPE: ClassVar[str] = "test_valid_xyz"
            SERVICE_SCHEMAS: ClassVar[dict] = {
                "create": {"type": "object", "additionalProperties": False, "properties": {}},
                "patch": {"type": "object", "additionalProperties": False, "properties": {}},
                "replace": {"type": "object", "additionalProperties": False, "properties": {}},
            }

            class Meta(_TestBaseModel.Meta):
                managed = False

        assert "create" in _Valid.SERVICE_SCHEMAS

    def test_read_key_allowed(self):
        """'read' key is allowed (deferred but valid) if provided alongside required keys."""

        class _WithRead(_TestBaseModel):
            ENTITY_TYPE: ClassVar[str] = "test_with_read_xyz"
            SERVICE_SCHEMAS: ClassVar[dict] = {
                "create": {"type": "object", "additionalProperties": False, "properties": {}},
                "patch": {"type": "object", "additionalProperties": False, "properties": {}},
                "replace": {"type": "object", "additionalProperties": False, "properties": {}},
                "read": {"type": "object"},
            }

            class Meta(_TestBaseModel.Meta):
                managed = False

        assert "read" in _WithRead.SERVICE_SCHEMAS


# ---------------------------------------------------------------------------
# req-grid-service-schemas-1: all registered concrete models publish schemas
# ---------------------------------------------------------------------------


class TestAllConcreteModelsPublishSchemas:
    """Every registered concrete model must have SERVICE_SCHEMAS with required keys."""

    def test_character_has_all_required_keys(self):
        assert {"create", "patch", "replace"} <= set(Character.SERVICE_SCHEMAS.keys())

    def test_edge_has_all_required_keys(self):
        assert {"create", "patch", "replace"} <= set(Edge.SERVICE_SCHEMAS.keys())

    def test_edge_replace_excludes_edge_type(self):
        """Edge.SERVICE_SCHEMAS['replace'] must not include edge_type (immutable)."""
        replace_props = Edge.SERVICE_SCHEMAS["replace"].get("properties", {})
        assert "edge_type" not in replace_props

    def test_edge_create_excludes_from_to_entity(self):
        """Edge create payload uses dedicated params; from/to entity not in properties."""
        create_props = Edge.SERVICE_SCHEMAS["create"].get("properties", {})
        assert "from_entity" not in create_props
        assert "to_entity" not in create_props

    def test_search_create_validates_good_payload(self):
        """Search.SERVICE_SCHEMAS['create'] accepts a valid payload."""
        payload = {"name": "My Search", "search_type": "orm", "root": "node"}
        jsonschema.validate(instance=payload, schema=Search.SERVICE_SCHEMAS["create"])

    def test_search_create_rejects_unknown_field(self):
        """Search.SERVICE_SCHEMAS['create'] rejects unknown fields (additionalProperties=False)."""
        payload = {
            "name": "My Search",
            "search_type": "orm",
            "root": "node",
            "bad_field": "oops",
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=payload, schema=Search.SERVICE_SCHEMAS["create"])

    def test_search_create_rejects_missing_required(self):
        """Search.SERVICE_SCHEMAS['create'] rejects payload missing 'name'."""
        payload = {"search_type": "orm", "root": "node"}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=payload, schema=Search.SERVICE_SCHEMAS["create"])

    def test_search_patch_has_no_required_fields(self):
        """Search.SERVICE_SCHEMAS['patch'] requires no fields."""
        assert "required" not in Search.SERVICE_SCHEMAS["patch"]

    def test_search_patch_validates_empty_payload(self):
        """Search.SERVICE_SCHEMAS['patch'] accepts an empty payload (all fields optional)."""
        jsonschema.validate(instance={}, schema=Search.SERVICE_SCHEMAS["patch"])
