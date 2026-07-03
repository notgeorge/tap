"""Subnet — an Amazon VPC subnet."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class Subnet(BaseModel):
    """An Amazon VPC subnet."""

    ENTITY_TYPE: ClassVar[str] = "aws_core__aws_subnet"
    ENTITY_NAME: ClassVar[str] = "Subnet"
    ENTITY_DESCRIPTION: ClassVar[str] = "A subnet within an Amazon VPC."
    ENTITY_ICON: ClassVar[str] = "aws-subnet"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "round-rectangle",
            "colors": {"fill": "#DAE5D3", "border": "#7BA362", "label": "#222D1B"},
            "label": {"valign": "top", "halign": "center", "position": "outside"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string"},
        "subnet_id": {"type": "string"},
        "cidr_block": {"type": "string"},
        "availability_zone": {"type": "string"},
        "public": {"type": "boolean"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "subnet_id": {"validation": "jsonschema", "schema": {"type": "string"}},
        "cidr_block": {"validation": "jsonschema", "schema": {"type": "string"}},
        "availability_zone": {"validation": "jsonschema", "schema": {"type": "string"}},
        "public": {"validation": "jsonschema", "schema": {"type": "boolean"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["subnet_id"]

    name = models.CharField(max_length=255, blank=True, default="")
    subnet_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    cidr_block = models.CharField(max_length=64, blank=True, default="")
    availability_zone = models.CharField(max_length=64, blank=True, default="")
    public = models.BooleanField(default=False)
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_core__aws_subnet"

    def get_name(self) -> str:
        return self.name or self.subnet_id

    def __str__(self) -> str:
        return self.get_name()
