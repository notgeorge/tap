"""DynamoDB Table — an Amazon DynamoDB table."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class DynamoDbTable(BaseModel):
    """An Amazon DynamoDB table."""

    ENTITY_TYPE: ClassVar[str] = "aws_core__aws_dynamodb_table"
    ENTITY_NAME: ClassVar[str] = "DynamoDB Table"
    ENTITY_DESCRIPTION: ClassVar[str] = "An Amazon DynamoDB NoSQL table."
    ENTITY_ICON: ClassVar[str] = "aws-dynamodb"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "colors": {"fill": "#EFC1F2", "border": "#C925D1", "label": "#380A3A"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "table_arn": {"type": "string"},
        "status": {"type": "string"},
        "billing_mode": {"type": "string"},
        "tags": {"type": "object"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "table_arn": {"validation": "jsonschema", "schema": {"type": "string"}},
        "status": {"validation": "jsonschema", "schema": {"type": "string"}},
        "billing_mode": {"validation": "jsonschema", "schema": {"type": "string"}},
        "tags": {"validation": "jsonschema", "schema": {"type": "object"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    table_arn = models.CharField(max_length=512, blank=True, default="")
    status = models.CharField(max_length=64, blank=True, default="")
    billing_mode = models.CharField(max_length=32, blank=True, default="")
    tags = models.JSONField(default=dict, blank=True)
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_core__aws_dynamodb_table"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
