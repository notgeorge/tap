"""AWS Account — an AWS account within an organization."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class AwsAccount(BaseModel):
    """An AWS account."""

    ENTITY_TYPE: ClassVar[str] = "aws_account"
    ENTITY_NAME: ClassVar[str] = "AWS Account"
    ENTITY_DESCRIPTION: ClassVar[str] = "An AWS account within an organization."
    ENTITY_ICON: ClassVar[str] = "aws-account"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "round-rectangle",
            "colors": {"fill": "#F2E5C4", "border": "#B89669", "label": "#6E5428"},
            "label": {"valign": "top", "halign": "center", "position": "outside"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "account_id": {"type": "string", "minLength": 1},
        "email": {"type": "string"},
        "status": {"type": "string"},
        "configuration": {"type": "object"},
        "tags": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "account_id": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "email": {"validation": "jsonschema", "schema": {"type": "string"}},
        "status": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
        "tags": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name", "account_id"]

    name = models.CharField(max_length=255, blank=True, default="")
    account_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    email = models.EmailField(blank=True, default="")
    status = models.CharField(max_length=64, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_account"

    def get_name(self) -> str:
        return self.name or self.account_id

    def __str__(self) -> str:
        return self.get_name()
