"""IP Address — a generic IPv4 or IPv6 address."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class IpAddress(BaseModel):
    """A generic IPv4 or IPv6 address."""

    ENTITY_TYPE: ClassVar[str] = "computing_core__ip_address"
    ENTITY_NAME: ClassVar[str] = "IP Address"
    ENTITY_DESCRIPTION: ClassVar[str] = "A generic IPv4 or IPv6 address."
    ENTITY_ICON: ClassVar[str] = "ip-address"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.computing": "network"}
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "colors": {"fill": "#7A9EC2", "border": "#4A6E92", "label": "#FFFFFF"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string"},
        "address": {"type": "string"},
        "version": {"type": "integer"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "address": {"validation": "jsonschema", "schema": {"type": "string"}},
        "version": {"validation": "jsonschema", "schema": {"type": "integer", "enum": [4, 6]}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["address"]

    name = models.CharField(max_length=255, blank=True, default="")
    address = models.GenericIPAddressField(db_index=True)
    version = models.PositiveSmallIntegerField(default=4)
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "computing_core__ip_address"

    def get_name(self) -> str:
        return self.name or self.address

    def __str__(self) -> str:
        return self.get_name()
