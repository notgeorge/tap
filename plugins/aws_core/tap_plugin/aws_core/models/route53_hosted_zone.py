"""Route 53 Hosted Zone — an Amazon Route 53 DNS hosted zone."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class Route53HostedZone(BaseModel):
    """An Amazon Route 53 DNS hosted zone."""

    ENTITY_TYPE: ClassVar[str] = "aws_core__aws_route53_zone"
    ENTITY_NAME: ClassVar[str] = "Route 53 Hosted Zone"
    ENTITY_DESCRIPTION: ClassVar[str] = "An Amazon Route 53 DNS hosted zone."
    ENTITY_ICON: ClassVar[str] = "aws-route53"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "colors": {"fill": "#DAD1E6", "border": "#7B5EA7", "label": "#221A2E"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "hosted_zone_id": {"type": "string"},
        "record_count": {"type": ["integer", "null"]},
        "private_zone": {"type": "boolean"},
        "configuration": {"type": "object"},
        "tags": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "hosted_zone_id": {"validation": "jsonschema", "schema": {"type": "string"}},
        "record_count": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "private_zone": {"validation": "jsonschema", "schema": {"type": "boolean"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
        "tags": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    hosted_zone_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    record_count = models.IntegerField(blank=True, null=True)
    private_zone = models.BooleanField(default=False)
    configuration = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_core__aws_route53_zone"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
