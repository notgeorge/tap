"""Port — a transport endpoint identified by port number and transport family."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class Port(BaseModel):
    """A transport endpoint identified by port number and protocol."""

    ENTITY_TYPE: ClassVar[str] = "computing_core__port"
    ENTITY_NAME: ClassVar[str] = "Port"
    ENTITY_DESCRIPTION: ClassVar[str] = "A transport endpoint identified by port number and transport family."
    ENTITY_ICON: ClassVar[str] = "computing_core__port"
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
        "port_number": {
            "type": ["integer", "null"],
            # Declared absence semantics (tap_grid req-grid-node-observation-6). An integer
            # field, so two-state (null | value): null = port number unobserved. The ephemeral
            # client-port signal ("number unknown but known to be ephemeral") is a separate
            # observation, deferred to a future is_ephemeral/role field — NOT a meaning of null
            # and NOT a sentinel (no -1). not_applicable stays unpermitted: null already covers
            # the absence, so N/A adds no useful flavor. See req-computing-core-ports-2.
            "x-tap-absence": {
                "null_default": "unobserved",
                "empty_is_meaningful": False,
                "convention": "req-computing-core-ports-2",
                "description": "Null = port number unobserved (not captured by the observing source).",
                "not_applicable": {"permitted": False},
            },
        },
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
        db_table = "computing_core__port"

    def get_name(self) -> str:
        if self.name:
            return self.name
        num = self.port_number if self.port_number is not None else "*"
        return f":{num}/{self.transport}"

    def __str__(self) -> str:
        return self.get_name()
