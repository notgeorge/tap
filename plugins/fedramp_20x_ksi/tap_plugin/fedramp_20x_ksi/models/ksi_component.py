"""KsiComponent — one component named by a KSI signal."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class KsiComponent(BaseModel):
    """One entry of a KSI signal's `components[]` array.

    One model for every component type; `component_type` discriminates across
    the signal schema's normalized component-type enum. `component_id` is the
    join key validations reference via `EVALUATES_COMPONENT`. `attributes` is
    a schema-declared free-form blob; `information_flow` is retained as
    structured data in v0 (flow-edge decomposition is a future seam).

    Spec: spec-fedramp-20x-ksi-compliance-artifacts-v0.md.
    """

    ENTITY_TYPE: ClassVar[str] = "ksi_component"
    ENTITY_NAME: ClassVar[str] = "KSI Component"
    ENTITY_DESCRIPTION: ClassVar[str] = (
        "One component a KSI signal names — a normalized cross-CSP component "
        "(object store, function, CDN distribution, package, …) with global "
        "identifiers and a FIPS 199 security categorization."
    )
    ENTITY_ICON: ClassVar[str] = "ksi-component"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"compliance": "ksi-signal"}

    _CATEGORY_VALUES = ["low", "moderate", "high", "inherited", "not-applicable", ""]

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "component_id": {"type": "string", "minLength": 1},
        "component_type": {"type": "string"},
        "native_id": {"type": "string"},
        "global_purl": {"type": "string"},
        "global_sha256": {"type": "string"},
        "global_image_digest": {"type": "string"},
        "security_confidentiality": {"type": "string"},
        "security_integrity": {"type": "string"},
        "security_availability": {"type": "string"},
        "attributes": {"type": "object"},
        "information_flow": {"type": "array"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "component_id": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "security_confidentiality": {"validation": "jsonschema", "schema": {"type": "string", "enum": _CATEGORY_VALUES}},
        "security_integrity": {"validation": "jsonschema", "schema": {"type": "string", "enum": _CATEGORY_VALUES}},
        "security_availability": {"validation": "jsonschema", "schema": {"type": "string", "enum": _CATEGORY_VALUES}},
        "attributes": {"validation": "jsonschema", "schema": {"type": "object"}},
        "information_flow": {"validation": "jsonschema", "schema": {"type": "array"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name", "component_id"]

    name = models.CharField(max_length=255, blank=True, default="")
    component_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    component_type = models.CharField(max_length=64, blank=True, default="", db_index=True)
    native_id = models.CharField(max_length=512, blank=True, default="")
    # global_id sub-keys, flattened so prefix queries (purl ecosystem, hash) reach.
    global_purl = models.CharField(max_length=512, blank=True, default="")
    global_sha256 = models.CharField(max_length=64, blank=True, default="")
    global_image_digest = models.CharField(max_length=128, blank=True, default="")
    # FIPS 199 security categorization (per MAS-CSO-FLO), flattened.
    security_confidentiality = models.CharField(max_length=16, blank=True, default="")
    security_integrity = models.CharField(max_length=16, blank=True, default="")
    security_availability = models.CharField(max_length=16, blank=True, default="")
    # attributes — schema-declared free-form, opaque-by-design.
    attributes = models.JSONField(default=dict, blank=True)
    # information_flow — retained structured in v0; flow-edge decomposition deferred.
    information_flow = models.JSONField(default=list, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "ksi_component"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.get_name()
