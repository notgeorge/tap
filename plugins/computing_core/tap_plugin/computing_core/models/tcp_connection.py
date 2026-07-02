"""TCP Connection — a TCP session represented as a node."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class TcpConnection(BaseModel):
    """A TCP session between two endpoints, modeled as a node."""

    ENTITY_TYPE: ClassVar[str] = "tcp_connection"
    ENTITY_NAME: ClassVar[str] = "TCP Connection"
    ENTITY_DESCRIPTION: ClassVar[str] = "A TCP session represented as a node for lifecycle and protocol attachment."
    ENTITY_ICON: ClassVar[str] = "tcp-connection"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.computing": "network"}
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "colors": {"fill": "#B28E5E", "border": "#835C2B", "label": "#FFFFFF"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string"},
        "state": {"type": "string"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "state": {
            "validation": "jsonschema",
            "schema": {
                "type": "string",
                "enum": [
                    "established",
                    "syn_sent",
                    "syn_received",
                    "fin_wait_1",
                    "fin_wait_2",
                    "time_wait",
                    "close_wait",
                    "last_ack",
                    "closing",
                    "closed",
                    "",
                ],
            },
        },
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = []

    name = models.CharField(max_length=255, blank=True, default="")
    state = models.CharField(max_length=32, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "computing_tcp_connection"

    def get_name(self) -> str:
        return self.name or f"tcp ({self.state})" if self.state else "tcp"

    def __str__(self) -> str:
        return self.get_name()
