"""Target Group — an Amazon ALB/NLB target group."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class TargetGroup(BaseModel):
    """An Amazon load balancer target group."""

    ENTITY_TYPE: ClassVar[str] = "aws_target_group"
    ENTITY_NAME: ClassVar[str] = "Target Group"
    ENTITY_DESCRIPTION: ClassVar[str] = "An Amazon load balancer target group."
    ENTITY_ICON: ClassVar[str] = "aws-target-group"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "target_group_arn": {"type": "string"},
        "protocol": {"type": "string"},
        "port": {"type": ["integer", "null"]},
        "target_type": {"type": "string"},
        "health_check_path": {"type": "string"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "target_group_arn": {"validation": "jsonschema", "schema": {"type": "string"}},
        "protocol": {"validation": "jsonschema", "schema": {"type": "string"}},
        "port": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "target_type": {"validation": "jsonschema", "schema": {"type": "string"}},
        "health_check_path": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    target_group_arn = models.CharField(max_length=512, blank=True, default="")
    protocol = models.CharField(max_length=16, blank=True, default="")
    port = models.IntegerField(blank=True, null=True)
    target_type = models.CharField(max_length=32, blank=True, default="")
    health_check_path = models.CharField(max_length=255, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_target_group"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
