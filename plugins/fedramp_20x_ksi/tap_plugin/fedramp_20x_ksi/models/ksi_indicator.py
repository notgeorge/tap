"""KSI Indicator — a single measurable FedRAMP 20x Key Security Indicator within a theme."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class KsiIndicator(BaseModel):
    """An individual KSI such as KSI-IAM-MFA."""

    ENTITY_TYPE: ClassVar[str] = "fedramp_20x_ksi__ksi_indicator"
    ENTITY_NAME: ClassVar[str] = "KSI Indicator"
    ENTITY_DESCRIPTION: ClassVar[str] = (
        "A single measurable FedRAMP 20x Key Security Indicator within a theme."
    )
    ENTITY_ICON: ClassVar[str] = "ksi-indicator"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"compliance": "fedramp-20x"}

    _STATUS_VALUES = ["draft", "published", "deprecated"]
    _CLASS_VALUES = ["a", "b", "c", "d"]

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "code": {"type": "string", "pattern": "^KSI-[A-Z]{3}-[A-Z0-9]{3}$"},
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "classes": {
            "type": "array",
            "items": {"type": "string", "enum": _CLASS_VALUES},
            "minItems": 1,
            "uniqueItems": True,
        },
        "class_variants": {"type": ["object", "null"]},
        "controls": {"type": "array", "items": {"type": "string"}},
        "updated_log": {"type": "array", "items": {"type": "object"}},
        "terms": {"type": "array", "items": {"type": "string"}},
        "reference": {"type": "string"},
        "reference_url": {"type": "string"},
        "status": {"type": "string", "enum": _STATUS_VALUES},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "code": {
            "validation": "jsonschema",
            "schema": {"type": "string", "pattern": "^KSI-[A-Z]{3}-[A-Z0-9]{3}$"},
        },
        "name": {
            "validation": "jsonschema",
            "schema": {"type": "string", "minLength": 1},
        },
        "description": {"validation": "jsonschema", "schema": {"type": "string"}},
        "classes": {
            "validation": "jsonschema",
            "schema": {
                "type": "array",
                "items": {"type": "string", "enum": _CLASS_VALUES},
                "minItems": 1,
                "uniqueItems": True,
            },
        },
        "class_variants": {
            "validation": "jsonschema",
            "schema": {"type": ["object", "null"]},
        },
        "controls": {
            "validation": "jsonschema",
            "schema": {"type": "array", "items": {"type": "string"}},
        },
        "updated_log": {
            "validation": "jsonschema",
            "schema": {"type": "array", "items": {"type": "object"}},
        },
        "terms": {
            "validation": "jsonschema",
            "schema": {"type": "array", "items": {"type": "string"}},
        },
        "reference": {"validation": "jsonschema", "schema": {"type": "string"}},
        "reference_url": {"validation": "jsonschema", "schema": {"type": "string"}},
        "status": {
            "validation": "jsonschema",
            "schema": {"type": "string", "enum": _STATUS_VALUES},
        },
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["code", "name", "classes", "status"]

    code = models.CharField(max_length=16, blank=True, default="", db_index=True)
    name = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    classes = models.JSONField(default=list, blank=True)
    class_variants = models.JSONField(null=True, blank=True)
    controls = models.JSONField(default=list, blank=True)
    updated_log = models.JSONField(default=list, blank=True)
    terms = models.JSONField(default=list, blank=True)
    reference = models.CharField(max_length=512, blank=True, default="")
    reference_url = models.URLField(max_length=1024, blank=True, default="")
    status = models.CharField(max_length=16, blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "fedramp_20x_ksi__ksi_indicator"

    def get_name(self) -> str:
        return self.name or self.code

    def __str__(self) -> str:
        return self.get_name()
