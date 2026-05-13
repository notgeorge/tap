"""ECS Service — an Amazon ECS service running tasks."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class EcsService(BaseModel):
    """An Amazon ECS service."""

    ENTITY_TYPE: ClassVar[str] = "aws_ecs_service"
    ENTITY_NAME: ClassVar[str] = "ECS Service"
    ENTITY_DESCRIPTION: ClassVar[str] = "An Amazon ECS service managing task instances."
    ENTITY_ICON: ClassVar[str] = "aws-ecs"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "service_arn": {"type": "string"},
        "status": {"type": "string"},
        "desired_count": {"type": ["integer", "null"]},
        "running_count": {"type": ["integer", "null"]},
        "launch_type": {"type": "string"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "service_arn": {"validation": "jsonschema", "schema": {"type": "string"}},
        "status": {"validation": "jsonschema", "schema": {"type": "string"}},
        "desired_count": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "running_count": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "launch_type": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    service_arn = models.CharField(max_length=512, blank=True, default="")
    status = models.CharField(max_length=64, blank=True, default="")
    desired_count = models.IntegerField(blank=True, null=True)
    running_count = models.IntegerField(blank=True, null=True)
    launch_type = models.CharField(max_length=64, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_ecs_service"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
