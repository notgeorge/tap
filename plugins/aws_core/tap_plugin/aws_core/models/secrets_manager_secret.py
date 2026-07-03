"""Secrets Manager Secret — an AWS Secrets Manager secret."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class SecretsManagerSecret(BaseModel):
    """An AWS Secrets Manager secret."""

    ENTITY_TYPE: ClassVar[str] = "aws_core__aws_secrets_manager_secret"
    ENTITY_NAME: ClassVar[str] = "Secrets Manager Secret"
    ENTITY_DESCRIPTION: ClassVar[str] = "An AWS Secrets Manager secret."
    ENTITY_ICON: ClassVar[str] = "aws-secrets-manager"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "colors": {"fill": "#F5C6CC", "border": "#DD344C", "label": "#3D0E15"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "secret_arn": {"type": "string"},
        "rotation_enabled": {"type": "boolean"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "secret_arn": {"validation": "jsonschema", "schema": {"type": "string"}},
        "rotation_enabled": {"validation": "jsonschema", "schema": {"type": "boolean"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    secret_arn = models.CharField(max_length=512, blank=True, default="")
    rotation_enabled = models.BooleanField(default=False)
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_core__aws_secrets_manager_secret"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
