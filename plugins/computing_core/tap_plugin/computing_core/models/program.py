"""Program — execution of an application that may spawn multiple processes."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class Program(BaseModel):
    """An application-level program that may spawn processes and use resources."""

    ENTITY_TYPE: ClassVar[str] = "computing_core__program"
    ENTITY_NAME: ClassVar[str] = "Program"
    ENTITY_DESCRIPTION: ClassVar[str] = "Execution of an application that may spawn multiple processes."
    ENTITY_ICON: ClassVar[str] = "computing_core__program"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.computing": "runtime"}
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "colors": {"fill": "#5EB289", "border": "#2B8359", "label": "#FFFFFF"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string"},
        "program_name": {"type": "string"},
        "version": {"type": "string"},
        "path": {"type": "string"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "program_name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "version": {"validation": "jsonschema", "schema": {"type": "string"}},
        "path": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["program_name"]

    name = models.CharField(max_length=255, blank=True, default="")
    program_name = models.CharField(max_length=255, blank=True, default="", db_index=True)
    version = models.CharField(max_length=64, blank=True, default="")
    path = models.CharField(max_length=1024, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "computing_core__program"

    def get_name(self) -> str:
        return self.name or self.program_name

    def __str__(self) -> str:
        return self.get_name()
