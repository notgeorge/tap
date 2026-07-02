"""Sentinel model — wildcard edge test case."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel

_NAME_SCHEMA: dict[str, Any] = {"type": "string", "minLength": 1}


class Sentinel(BaseModel):
    """A watcher that can reference anything (wildcard test case)."""

    ENTITY_TYPE: ClassVar[str] = "sentinel"
    ENTITY_NAME: ClassVar[str] = "Sentinel"
    ENTITY_DESCRIPTION: ClassVar[str] = "A watcher (wildcard test)."

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": _NAME_SCHEMA,
        "watch_domain": {"type": "string"},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]
    REPLACE_REQUIRED: ClassVar[list[str]] = ["name", "watch_domain"]
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {"tap_viz": {"shape": "rectangle"}}

    # No "nodes" key = wildcard: REFERENCES can point to ANY node type
    OUTBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {"edges": [{"type": "REFERENCES"}]},
    ]

    INBOUND_EDGES: ClassVar[list[dict[str, Any]]] = [
        {"nodes": [{"type": "sentinel"}], "edges": [{"type": "REFERENCES"}]},
    ]

    name = models.CharField(max_length=255, blank=True, default="")
    watch_domain = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "lotr_sentinel"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
