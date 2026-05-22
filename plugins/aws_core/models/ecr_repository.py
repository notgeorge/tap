"""ECR Repository — an Amazon Elastic Container Registry repository."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class EcrRepository(BaseModel):
    """An Amazon ECR container image repository."""

    ENTITY_TYPE: ClassVar[str] = "aws_ecr_repository"
    ENTITY_NAME: ClassVar[str] = "ECR Repository"
    ENTITY_DESCRIPTION: ClassVar[str] = "An Amazon ECR container image repository."
    ENTITY_ICON: ClassVar[str] = "aws-ecr"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "repository_arn": {"type": "string"},
        "repository_uri": {"type": "string"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "repository_arn": {"validation": "jsonschema", "schema": {"type": "string"}},
        "repository_uri": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    repository_arn = models.CharField(max_length=512, blank=True, default="")
    repository_uri = models.CharField(max_length=512, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_ecr_repository"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
