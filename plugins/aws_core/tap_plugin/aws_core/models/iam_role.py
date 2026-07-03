"""IAM Role — an AWS Identity and Access Management role."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class IamRole(BaseModel):
    """An AWS IAM role."""

    ENTITY_TYPE: ClassVar[str] = "aws_core__aws_iam_role"
    ENTITY_NAME: ClassVar[str] = "IAM Role"
    ENTITY_DESCRIPTION: ClassVar[str] = "An AWS IAM role for service or cross-account access."
    ENTITY_ICON: ClassVar[str] = "aws-iam"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "colors": {"fill": "#F5C6CC", "border": "#DD344C", "label": "#3D0E15"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "role_arn": {"type": "string"},
        "path": {"type": "string"},
        "max_session_duration": {"type": ["integer", "null"]},
        "configuration": {"type": "object"},
        "tags": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "role_arn": {"validation": "jsonschema", "schema": {"type": "string"}},
        "path": {"validation": "jsonschema", "schema": {"type": "string"}},
        "max_session_duration": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
        "tags": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    role_arn = models.CharField(max_length=512, blank=True, default="")
    path = models.CharField(max_length=512, blank=True, default="/")
    max_session_duration = models.IntegerField(blank=True, null=True)
    configuration = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_core__aws_iam_role"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
