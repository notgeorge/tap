"""VPC — an Amazon Virtual Private Cloud."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class Vpc(BaseModel):
    """An Amazon VPC."""

    ENTITY_TYPE: ClassVar[str] = "aws_core__aws_vpc"
    ENTITY_NAME: ClassVar[str] = "VPC"
    ENTITY_DESCRIPTION: ClassVar[str] = "An Amazon Virtual Private Cloud."
    ENTITY_ICON: ClassVar[str] = "aws-vpc"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "round-rectangle",
            "colors": {"fill": "#D0DECD", "border": "#5A8A4D", "label": "#192615"},
            "label": {"valign": "top", "halign": "center", "position": "outside"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string"},
        "vpc_id": {"type": "string"},
        "cidr_block": {"type": "string"},
        "state": {"type": "string"},
        "is_default": {"type": "boolean"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "vpc_id": {"validation": "jsonschema", "schema": {"type": "string"}},
        "cidr_block": {"validation": "jsonschema", "schema": {"type": "string"}},
        "state": {"validation": "jsonschema", "schema": {"type": "string"}},
        "is_default": {"validation": "jsonschema", "schema": {"type": "boolean"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["vpc_id"]

    name = models.CharField(max_length=255, blank=True, default="")
    vpc_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    cidr_block = models.CharField(max_length=64, blank=True, default="")
    state = models.CharField(max_length=32, blank=True, default="")
    is_default = models.BooleanField(default=False)
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_core__aws_vpc"

    def get_name(self) -> str:
        return self.name or self.vpc_id

    def __str__(self) -> str:
        return self.get_name()
