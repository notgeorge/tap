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
        "mac_address": {
            "type": ["string", "null"],
            # Declared absence semantics (tap_grid req-grid-node-observation-6). Phase 1
            # carries null_default/description; not_applicable is Phase-2-reserved (Codd's
            # N/A, resolved via extended FLIP) — declared so external readers see the shape.
            "x-tap-absence": {
                "null_default": "unobserved",
                "empty_is_meaningful": False,
                "convention": "req-computing-core-interface-1",
                "description": "Null = no source has captured a hardware address for this interface.",
                "not_applicable": {
                    "permitted": True,
                    "means": "Interface has no hardware address by nature (e.g. loopback/virtual).",
                },
            },
        },
        "state": {"type": "string"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "interface_name": {"validation": "jsonschema", "schema": {"type": "string"}},
        # value-or-null: empty_is_meaningful is False, so "" is rejected (minLength on a
        # null is not applied by jsonschema). A MAC is captured or unobserved, never "".
        "mac_address": {"validation": "jsonschema", "schema": {"type": ["string", "null"], "minLength": 1}},
        "state": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["interface_name"]

    name = models.CharField(max_length=255, blank=True, default="")
    interface_name = models.CharField(max_length=64, blank=True, default="", db_index=True)
    # null = hardware address unobserved, distinct from "". The authoritative absence
    # semantics are DECLARED in FIELD_CRUD_SCHEMA["mac_address"]["x-tap-absence"] above
    # (grid req-grid-node-observation, applied here by req-computing-core-interface-1);
    # this noqa is only the DJ001 lint-silencer, with the RID as its standing justification.
    mac_address = models.CharField(  # noqa: DJ001  (req-computing-core-interface-1)
        max_length=17, blank=True, null=True
    )
    state = models.CharField(max_length=32, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "computing_network_interface"

    def get_name(self) -> str:
        return self.name or self.interface_name

    def __str__(self) -> str:
        return self.get_name()
