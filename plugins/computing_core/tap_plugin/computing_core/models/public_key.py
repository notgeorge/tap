"""Public Key — a public cryptographic key."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class PublicKey(BaseModel):
    """A public cryptographic key represented as a data blob."""

    ENTITY_TYPE: ClassVar[str] = "public_key"
    ENTITY_NAME: ClassVar[str] = "Public Key"
    ENTITY_DESCRIPTION: ClassVar[str] = "A public cryptographic key."
    ENTITY_ICON: ClassVar[str] = "public-key"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.computing": "storage"}
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "colors": {"fill": "#5E8E5E", "border": "#2B5C2B", "label": "#FFFFFF"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string"},
        "algorithm": {"type": "string"},
        "key_size": {"type": ["integer", "null"]},
        "fingerprint": {"type": "string"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "algorithm": {"validation": "jsonschema", "schema": {"type": "string"}},
        "key_size": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "fingerprint": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = []

    name = models.CharField(max_length=255, blank=True, default="")
    algorithm = models.CharField(max_length=32, blank=True, default="")
    key_size = models.PositiveIntegerField(blank=True, null=True)
    fingerprint = models.CharField(max_length=255, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "computing_public_key"

    def get_name(self) -> str:
        return self.name or self.fingerprint or "public key"

    def __str__(self) -> str:
        return self.get_name()
