"""EC2 Instance — an Amazon Elastic Compute Cloud virtual server."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class Ec2Instance(BaseModel):
    """An Amazon EC2 virtual server instance."""

    ENTITY_TYPE: ClassVar[str] = "aws_ec2_instance"
    ENTITY_NAME: ClassVar[str] = "EC2 Instance"
    ENTITY_DESCRIPTION: ClassVar[str] = "An Amazon EC2 virtual server instance."
    ENTITY_ICON: ClassVar[str] = "aws-ec2"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "colors": {"fill": "#F9D7B7", "border": "#ED7100", "label": "#421F00"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string"},
        "instance_id": {"type": "string"},
        "ec2_type": {"type": "string"},
        "state": {"type": "string"},
        "private_ip": {"type": ["string", "null"]},
        "public_ip": {"type": ["string", "null"]},
        "ami_id": {"type": "string"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "instance_id": {"validation": "jsonschema", "schema": {"type": "string"}},
        "ec2_type": {"validation": "jsonschema", "schema": {"type": "string"}},
        "state": {"validation": "jsonschema", "schema": {"type": "string"}},
        "private_ip": {"validation": "jsonschema", "schema": {"type": ["string", "null"]}},
        "public_ip": {"validation": "jsonschema", "schema": {"type": ["string", "null"]}},
        "ami_id": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["instance_id"]

    name = models.CharField(max_length=255, blank=True, default="")
    instance_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    ec2_type = models.CharField(max_length=64, blank=True, default="")
    state = models.CharField(max_length=32, blank=True, default="")
    private_ip = models.GenericIPAddressField(blank=True, null=True)
    public_ip = models.GenericIPAddressField(blank=True, null=True)
    ami_id = models.CharField(max_length=64, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_ec2_instance"

    def get_name(self) -> str:
        return self.name or self.instance_id

    def __str__(self) -> str:
        return self.get_name()
