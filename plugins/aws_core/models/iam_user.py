"""IAM User — an AWS Identity and Access Management user."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class IamUser(BaseModel):
    """An AWS IAM user."""

    ENTITY_TYPE: ClassVar[str] = "aws_iam_user"
    ENTITY_NAME: ClassVar[str] = "IAM User"
    ENTITY_DESCRIPTION: ClassVar[str] = "An AWS IAM user identity."
    ENTITY_ICON: ClassVar[str] = "aws-iam"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "user_arn": {"type": "string"},
        "path": {"type": "string"},
        "mfa_enabled": {"type": "boolean"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "user_arn": {"validation": "jsonschema", "schema": {"type": "string"}},
        "path": {"validation": "jsonschema", "schema": {"type": "string"}},
        "mfa_enabled": {"validation": "jsonschema", "schema": {"type": "boolean"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    user_arn = models.CharField(max_length=512, blank=True, default="")
    path = models.CharField(max_length=512, blank=True, default="/")
    mfa_enabled = models.BooleanField(default=False)
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_iam_user"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
