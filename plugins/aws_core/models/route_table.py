"""Route Table — an Amazon VPC route table."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class RouteTable(BaseModel):
    """An Amazon VPC route table."""

    ENTITY_TYPE: ClassVar[str] = "aws_route_table"
    ENTITY_NAME: ClassVar[str] = "Route Table"
    ENTITY_DESCRIPTION: ClassVar[str] = "An Amazon VPC route table."
    ENTITY_ICON: ClassVar[str] = "aws-route-table"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string"},
        "route_table_id": {"type": "string"},
        "is_main": {"type": "boolean"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "route_table_id": {"validation": "jsonschema", "schema": {"type": "string"}},
        "is_main": {"validation": "jsonschema", "schema": {"type": "boolean"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["route_table_id"]

    name = models.CharField(max_length=255, blank=True, default="")
    route_table_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    is_main = models.BooleanField(default=False)
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_route_table"

    def get_name(self) -> str:
        return self.name or self.route_table_id

    def __str__(self) -> str:
        return self.get_name()
