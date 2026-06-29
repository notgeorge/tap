"""Network Interface — an OS-level network interface such as eth0."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class NetworkInterface(BaseModel):
    """An operating-system-level network interface."""

    ENTITY_TYPE: ClassVar[str] = "network_interface"
    ENTITY_NAME: ClassVar[str] = "Network Interface"
    ENTITY_DESCRIPTION: ClassVar[str] = "An OS-level network interface such as eth0 or a virtual equivalent."
    ENTITY_ICON: ClassVar[str] = "network-interface"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.computing": "network"}
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "colors": {"fill": "#6B8E8E", "border": "#3D5C5C", "label": "#FFFFFF"},
            "label": {"valign": "top", "halign": "center", "position": "inside"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string"},
        "interface_name": {"type": "string"},
        "mac_address": {"type": ["string", "null"]},
        "state": {"type": "string"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "interface_name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "mac_address": {"validation": "jsonschema", "schema": {"type": ["string", "null"]}},
        "state": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["interface_name"]

    name = models.CharField(max_length=255, blank=True, default="")
    interface_name = models.CharField(max_length=64, blank=True, default="", db_index=True)
    # null distinguishes "MAC unknown/not-applicable" from "" (intentional; a
    # nullability change would require a data migration). noqa the string-null rule.
    mac_address = models.CharField(max_length=17, blank=True, null=True)  # noqa: DJ001
    state = models.CharField(max_length=32, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "computing_network_interface"

    def get_name(self) -> str:
        return self.name or self.interface_name

    def __str__(self) -> str:
        return self.get_name()
