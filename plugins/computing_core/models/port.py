"""Port — a transport endpoint identified by port number and transport family."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class Port(BaseModel):
    """A transport endpoint identified by port number and protocol."""

    ENTITY_TYPE: ClassVar[str] = "port"
    ENTITY_NAME: ClassVar[str] = "Port"
    ENTITY_DESCRIPTION: ClassVar[str] = "A transport endpoint identified by port number and transport family."
    ENTITY_ICON: ClassVar[str] = "port"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.computing": "network"}
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "colors": {"fill": "#8E7EB2", "border": "#5C4E82", "label": "#3E2A5F"},
            "label": {"valign": "center", "halign": "center", "position": "inside"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string"},
        "port_number": {"type": ["integer", "null"]},
        "transport": {"type": "string"},
        "state": {"type": "string"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "port_number": {
            "validation": "jsonschema",
            "schema": {"type": ["integer", "null"], "minimum": 0, "maximum": 65535},
        },
        "transport": {
            "validation": "jsonschema",
            "schema": {"type": "string", "enum": ["tcp", "udp", "sctp"]},
        },
        "state": {
            "validation": "jsonschema",
            "schema": {"type": "string", "enum": ["listening", "bound", "connected", "closed", ""]},
        },
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["transport"]

    name = models.CharField(max_length=255, blank=True, default="")
    port_number = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    transport = models.CharField(max_length=8, default="tcp")
    state = models.CharField(max_length=32, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "computing_port"

    def get_name(self) -> str:
        if self.name:
            return self.name
        num = self.port_number if self.port_number is not None else "*"
        return f":{num}/{self.transport}"

    def __str__(self) -> str:
        return self.get_name()
