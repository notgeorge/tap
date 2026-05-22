"""IAM Policy — an AWS Identity and Access Management policy."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class IamPolicy(BaseModel):
    """An AWS IAM policy document."""

    ENTITY_TYPE: ClassVar[str] = "aws_iam_policy"
    ENTITY_NAME: ClassVar[str] = "IAM Policy"
    ENTITY_DESCRIPTION: ClassVar[str] = "An AWS IAM permission policy."
    ENTITY_ICON: ClassVar[str] = "aws-iam"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "policy_arn": {"type": "string"},
        "path": {"type": "string"},
        "is_aws_managed": {"type": "boolean"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "policy_arn": {"validation": "jsonschema", "schema": {"type": "string"}},
        "path": {"validation": "jsonschema", "schema": {"type": "string"}},
        "is_aws_managed": {"validation": "jsonschema", "schema": {"type": "boolean"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    policy_arn = models.CharField(max_length=512, blank=True, default="")
    path = models.CharField(max_length=512, blank=True, default="/")
    is_aws_managed = models.BooleanField(default=False)
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_iam_policy"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
