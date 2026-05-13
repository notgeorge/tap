"""KSI Theme — a top-level grouping of related FedRAMP 20x Key Security Indicators."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class KsiTheme(BaseModel):
    """A top-level KSI theme such as KSI-IAM or KSI-CNA."""

    ENTITY_TYPE: ClassVar[str] = "ksi_theme"
    ENTITY_NAME: ClassVar[str] = "KSI Theme"
    ENTITY_DESCRIPTION: ClassVar[str] = (
        "A top-level grouping of related FedRAMP 20x Key Security Indicators."
    )
    ENTITY_ICON: ClassVar[str] = "ksi-theme"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"compliance": "fedramp-20x"}

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "code": {"type": "string", "pattern": "^KSI-[A-Z]{3}$"},
        "name": {"type": "string", "minLength": 1},
        "short_name": {"type": "string", "pattern": "^[A-Z]{3}$"},
        "web_name": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "sort_order": {"type": "integer", "minimum": 0},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "code": {
            "validation": "jsonschema",
            "schema": {"type": "string", "pattern": "^KSI-[A-Z]{3}$"},
        },
        "name": {
            "validation": "jsonschema",
            "schema": {"type": "string", "minLength": 1},
        },
        "short_name": {
            "validation": "jsonschema",
            "schema": {"type": "string", "pattern": "^[A-Z]{3}$"},
        },
        "web_name": {
            "validation": "jsonschema",
            "schema": {"type": "string", "minLength": 1},
        },
        "description": {"validation": "jsonschema", "schema": {"type": "string"}},
        "sort_order": {
            "validation": "jsonschema",
            "schema": {"type": "integer", "minimum": 0},
        },
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["code", "name", "short_name", "web_name"]

    code = models.CharField(max_length=8, blank=True, default="", db_index=True)
    name = models.CharField(max_length=255, blank=True, default="")
    short_name = models.CharField(max_length=3, blank=True, default="")
    web_name = models.CharField(max_length=64, blank=True, default="")
    description = models.TextField(blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta(BaseModel.Meta):
        db_table = "ksi_theme"
        ordering = ["sort_order", "code"]

    def get_name(self) -> str:
        return self.name or self.code

    def __str__(self) -> str:
        return self.get_name()
