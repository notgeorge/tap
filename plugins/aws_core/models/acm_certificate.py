"""ACM Certificate — an AWS Certificate Manager certificate."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class AcmCertificate(BaseModel):
    """An AWS Certificate Manager TLS/SSL certificate."""

    ENTITY_TYPE: ClassVar[str] = "aws_acm_certificate"
    ENTITY_NAME: ClassVar[str] = "ACM Certificate"
    ENTITY_DESCRIPTION: ClassVar[str] = "An AWS Certificate Manager TLS/SSL certificate."
    ENTITY_ICON: ClassVar[str] = "aws-acm"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "colors": {"fill": "#F5C6CC", "border": "#DD344C", "label": "#3D0E15"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "certificate_arn": {"type": "string"},
        "domain_name": {"type": "string"},
        "status": {"type": "string"},
        "type": {"type": "string"},
        "configuration": {"type": "object"},
        "tags": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "certificate_arn": {"validation": "jsonschema", "schema": {"type": "string"}},
        "domain_name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "status": {"validation": "jsonschema", "schema": {"type": "string"}},
        "type": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
        "tags": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    certificate_arn = models.CharField(max_length=512, blank=True, default="")
    domain_name = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=64, blank=True, default="")
    type = models.CharField(max_length=64, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_acm_certificate"

    def get_name(self) -> str:
        return self.name or self.domain_name

    def __str__(self) -> str:
        return self.get_name()
