"""Elastic IP — an Amazon VPC elastic IP address."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class ElasticIp(BaseModel):
    """An Amazon VPC elastic IP address."""

    ENTITY_TYPE: ClassVar[str] = "aws_core__aws_elastic_ip"
    ENTITY_NAME: ClassVar[str] = "Elastic IP"
    ENTITY_DESCRIPTION: ClassVar[str] = "An Amazon VPC elastic IP address."
    ENTITY_ICON: ClassVar[str] = "aws-elastic-ip"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "colors": {"fill": "#F9D7B7", "border": "#ED7100", "label": "#421F00"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string"},
        "allocation_id": {"type": "string"},
        "public_ip": {"type": ["string", "null"]},
        "association_id": {"type": "string"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "allocation_id": {"validation": "jsonschema", "schema": {"type": "string"}},
        "public_ip": {"validation": "jsonschema", "schema": {"type": ["string", "null"]}},
        "association_id": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["allocation_id"]

    name = models.CharField(max_length=255, blank=True, default="")
    allocation_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    public_ip = models.GenericIPAddressField(blank=True, null=True)
    association_id = models.CharField(max_length=64, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_core__aws_elastic_ip"

    def get_name(self) -> str:
        return self.name or str(self.public_ip or self.allocation_id)

    def __str__(self) -> str:
        return self.get_name()
