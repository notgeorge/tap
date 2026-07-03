"""SageMaker Endpoint — an Amazon SageMaker inference endpoint."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class SagemakerEndpoint(BaseModel):
    """An Amazon SageMaker inference endpoint."""

    ENTITY_TYPE: ClassVar[str] = "aws_core__aws_sagemaker_endpoint"
    ENTITY_NAME: ClassVar[str] = "SageMaker Endpoint"
    ENTITY_DESCRIPTION: ClassVar[str] = "An Amazon SageMaker inference endpoint."
    ENTITY_ICON: ClassVar[str] = "aws-sagemaker"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "colors": {"fill": "#DECDFF", "border": "#8C4FFF", "label": "#271647"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "endpoint_arn": {"type": "string"},
        "status": {"type": "string"},
        "endpoint_instance_type": {"type": "string"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "endpoint_arn": {"validation": "jsonschema", "schema": {"type": "string"}},
        "status": {"validation": "jsonschema", "schema": {"type": "string"}},
        "endpoint_instance_type": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    endpoint_arn = models.CharField(max_length=512, blank=True, default="")
    status = models.CharField(max_length=64, blank=True, default="")
    endpoint_instance_type = models.CharField(max_length=64, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_core__aws_sagemaker_endpoint"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
