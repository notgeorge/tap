"""ALB — an Amazon Application Load Balancer."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class Alb(BaseModel):
    """An Amazon Application Load Balancer."""

    ENTITY_TYPE: ClassVar[str] = "aws_alb"
    ENTITY_NAME: ClassVar[str] = "Application Load Balancer"
    ENTITY_DESCRIPTION: ClassVar[str] = "An Amazon Application Load Balancer (ALB)."
    ENTITY_ICON: ClassVar[str] = "aws-alb"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "colors": {"fill": "#D1BBE6", "border": "#8761AD", "label": "#3E2A5F"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "lb_arn": {"type": "string"},
        "dns_name": {"type": "string"},
        "scheme": {"type": "string"},
        "state": {"type": "string"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "lb_arn": {"validation": "jsonschema", "schema": {"type": "string"}},
        "dns_name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "scheme": {"validation": "jsonschema", "schema": {"type": "string"}},
        "state": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    lb_arn = models.CharField(max_length=512, blank=True, default="")
    dns_name = models.CharField(max_length=512, blank=True, default="")
    scheme = models.CharField(max_length=32, blank=True, default="")
    state = models.CharField(max_length=32, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_alb"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
