"""Security Group — an Amazon VPC security group."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class SecurityGroup(BaseModel):
    """An Amazon VPC security group."""

    ENTITY_TYPE: ClassVar[str] = "aws_security_group"
    ENTITY_NAME: ClassVar[str] = "Security Group"
    ENTITY_DESCRIPTION: ClassVar[str] = "An Amazon VPC security group (stateful firewall)."
    ENTITY_ICON: ClassVar[str] = "aws-security-group"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string"},
        "group_id": {"type": "string"},
        "description": {"type": "string"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "group_id": {"validation": "jsonschema", "schema": {"type": "string"}},
        "description": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["group_id"]

    name = models.CharField(max_length=255, blank=True, default="")
    group_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    description = models.TextField(blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_security_group"

    def get_name(self) -> str:
        return self.name or self.group_id

    def __str__(self) -> str:
        return self.get_name()
