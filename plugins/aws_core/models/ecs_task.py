"""ECS Task — an Amazon ECS task (running container group)."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class EcsTask(BaseModel):
    """An Amazon ECS task instance."""

    ENTITY_TYPE: ClassVar[str] = "aws_ecs_task"
    ENTITY_NAME: ClassVar[str] = "ECS Task"
    ENTITY_DESCRIPTION: ClassVar[str] = "A running ECS task (container group)."
    ENTITY_ICON: ClassVar[str] = "aws-ecs"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string"},
        "task_arn": {"type": "string"},
        "task_definition_arn": {"type": "string"},
        "status": {"type": "string"},
        "launch_type": {"type": "string"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "task_arn": {"validation": "jsonschema", "schema": {"type": "string"}},
        "task_definition_arn": {"validation": "jsonschema", "schema": {"type": "string"}},
        "status": {"validation": "jsonschema", "schema": {"type": "string"}},
        "launch_type": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["task_arn"]

    name = models.CharField(max_length=255, blank=True, default="")
    task_arn = models.CharField(max_length=512, blank=True, default="")
    task_definition_arn = models.CharField(max_length=512, blank=True, default="")
    status = models.CharField(max_length=64, blank=True, default="")
    launch_type = models.CharField(max_length=64, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_ecs_task"

    def get_name(self) -> str:
        return self.name or self.task_arn.rsplit("/", 1)[-1] if self.task_arn else ""

    def __str__(self) -> str:
        return self.get_name()
