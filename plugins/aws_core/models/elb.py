"""ELB — an Amazon Classic Load Balancer."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class Elb(BaseModel):
    """An Amazon Classic Load Balancer."""

    ENTITY_TYPE: ClassVar[str] = "aws_elb"
    ENTITY_NAME: ClassVar[str] = "Classic Load Balancer"
    ENTITY_DESCRIPTION: ClassVar[str] = "An Amazon Classic Load Balancer (ELB)."
    ENTITY_ICON: ClassVar[str] = "aws-elb"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "dns_name": {"type": "string"},
        "scheme": {"type": "string"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "dns_name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "scheme": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    dns_name = models.CharField(max_length=512, blank=True, default="")
    scheme = models.CharField(max_length=32, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_elb"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
