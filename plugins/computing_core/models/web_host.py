"""Web Host — a named internet host that serves content over HTTP(S)."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class WebHost(BaseModel):
    """A named internet host that serves content over HTTP(S), identified by hostname.

    For external / unmanaged hosts (e.g. ``cisa.gov``) this models the origin
    that serves documents, not its internal compute. Carries the ``tap.web``
    dimension marker so a future ``web_core`` split can lift every web-native
    type in one shot.

    Spec: plugins/computing_core/specs/spec-computing-core-v0.md
    """

    ENTITY_TYPE: ClassVar[str] = "web_host"
    ENTITY_NAME: ClassVar[str] = "Web Host"
    ENTITY_DESCRIPTION: ClassVar[str] = "A named internet host that serves content over HTTP(S)."
    ENTITY_ICON: ClassVar[str] = "web-host"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.computing": "network", "tap.web": "native"}
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "round-rectangle",
            "colors": {"fill": "#5E8EB2", "border": "#2B5C83", "label": "#FFFFFF"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string"},
        "hostname": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "hostname": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "description": {"validation": "jsonschema", "schema": {"type": "string"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["hostname"]

    name = models.CharField(max_length=255, blank=True, default="")
    hostname = models.CharField(max_length=255, blank=True, default="", db_index=True)
    description = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "computing_web_host"

    def get_name(self) -> str:
        return self.name or self.hostname

    def __str__(self) -> str:
        return self.get_name()
