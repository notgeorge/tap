"""CloudFront Distribution — an Amazon CloudFront content delivery distribution."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class CloudfrontDistribution(BaseModel):
    """An Amazon CloudFront distribution.

    Spec: plugins/aws_core/specs/spec-aws-core-v0.md (req-aws-core-models),
    plugins/aws_core/specs/spec-aws-core-collector-v0.md
    (req-aws-collector-model-deps).

    `domain_name` is indexed because the Route 53 alias → CloudFront edge
    resolves by matching an alias record's target against this value.
    """

    ENTITY_TYPE: ClassVar[str] = "aws_core__aws_cloudfront_distribution"
    ENTITY_NAME: ClassVar[str] = "CloudFront Distribution"
    ENTITY_DESCRIPTION: ClassVar[str] = "An Amazon CloudFront content delivery distribution."
    ENTITY_ICON: ClassVar[str] = "aws-cloudfront"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "colors": {"fill": "#DECDFF", "border": "#8C4FFF", "label": "#271647"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "distribution_arn": {"type": "string"},
        "domain_name": {"type": "string"},
        "status": {"type": "string"},
        "enabled": {"type": "boolean"},
        "configuration": {"type": "object"},
        "tags": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "distribution_arn": {"validation": "jsonschema", "schema": {"type": "string"}},
        "domain_name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "status": {"validation": "jsonschema", "schema": {"type": "string"}},
        "enabled": {"validation": "jsonschema", "schema": {"type": "boolean"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
        "tags": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    distribution_arn = models.CharField(max_length=512, blank=True, default="")
    domain_name = models.CharField(max_length=255, blank=True, default="", db_index=True)
    status = models.CharField(max_length=64, blank=True, default="")
    enabled = models.BooleanField(default=False)
    configuration = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_core__aws_cloudfront_distribution"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
