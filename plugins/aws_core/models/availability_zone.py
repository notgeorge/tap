"""AWS Availability Zone — an isolated location within a region."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class AvailabilityZone(BaseModel):
    """An AWS availability zone (us-east-1a, us-east-1b, etc.)."""

    ENTITY_TYPE: ClassVar[str] = "aws_az"
    ENTITY_NAME: ClassVar[str] = "Availability Zone"
    ENTITY_DESCRIPTION: ClassVar[str] = "An isolated location within an AWS region."
    ENTITY_ICON: ClassVar[str] = "aws-az"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "zone_id": {"type": "string"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "zone_id": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    zone_id = models.CharField(max_length=64, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_availability_zone"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
