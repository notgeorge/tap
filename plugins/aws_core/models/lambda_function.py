"""Lambda Function — an AWS Lambda serverless function."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class LambdaFunction(BaseModel):
    """An AWS Lambda serverless function."""

    ENTITY_TYPE: ClassVar[str] = "aws_lambda"
    ENTITY_NAME: ClassVar[str] = "Lambda Function"
    ENTITY_DESCRIPTION: ClassVar[str] = "An AWS Lambda serverless function."
    ENTITY_ICON: ClassVar[str] = "aws-lambda"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "function_arn": {"type": "string"},
        "runtime": {"type": "string"},
        "handler": {"type": "string"},
        "memory_size": {"type": ["integer", "null"]},
        "timeout": {"type": ["integer", "null"]},
        "configuration": {"type": "object"},
        "tags": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "function_arn": {"validation": "jsonschema", "schema": {"type": "string"}},
        "runtime": {"validation": "jsonschema", "schema": {"type": "string"}},
        "handler": {"validation": "jsonschema", "schema": {"type": "string"}},
        "memory_size": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "timeout": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
        "tags": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    function_arn = models.CharField(max_length=512, blank=True, default="")
    runtime = models.CharField(max_length=64, blank=True, default="")
    handler = models.CharField(max_length=255, blank=True, default="")
    memory_size = models.IntegerField(blank=True, null=True)
    timeout = models.IntegerField(blank=True, null=True)
    configuration = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_lambda_function"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
