"""Internet Gateway — an Amazon VPC internet gateway."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class InternetGateway(BaseModel):
    """An Amazon VPC internet gateway."""

    ENTITY_TYPE: ClassVar[str] = "aws_internet_gateway"
    ENTITY_NAME: ClassVar[str] = "Internet Gateway"
    ENTITY_DESCRIPTION: ClassVar[str] = "An Amazon VPC internet gateway."
    ENTITY_ICON: ClassVar[str] = "aws-internet-gateway"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string"},
        "igw_id": {"type": "string"},
        "state": {"type": "string"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "igw_id": {"validation": "jsonschema", "schema": {"type": "string"}},
        "state": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["igw_id"]

    name = models.CharField(max_length=255, blank=True, default="")
    igw_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    state = models.CharField(max_length=32, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_internet_gateway"

    def get_name(self) -> str:
        return self.name or self.igw_id

    def __str__(self) -> str:
        return self.get_name()
