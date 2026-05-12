"""tap_cares models.

req-tap-cares-collector-model (spec-tap-cares-collector.md).

The Collector model is the on-grid representation of a tap_cares collector
capability. It stores a fully-qualified scope:key that resolves to a Python
class in collector_registry at execution time; it never stores filesystem
paths, import strings, or executable code.

CollectionJob and the HAS_JOB edge land in Phase 4.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.core.exceptions import ValidationError
from django.db import models

from tap_cares.exceptions import InvalidCollectorRegistryKeyError
from tap_cares.registry import _validate_collector_token
from tap_grid.models import BaseModel


class Collector(BaseModel):
    """An on-grid tap_cares collector capability.

    The collector_registry field stores a `scope:key` referencing a registered
    CollectorBase subclass. Persisting a Collector with a short key (no `:`),
    a malformed scope/key, or a duplicate collector_registry value all fail
    validation. The Python class itself is never resolved or imported at
    persist time — that happens at execution time via
    `tap_cares.registry.get_collector`.

    Spec: tap_cares/specs/spec-tap-cares-collector.md
    """

    ENTITY_TYPE: ClassVar[str] = "collector"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap_cares": "collector"}

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, dict[str, Any]]] = {
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "collector_registry": {"type": "string", "minLength": 1},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name", "collector_registry"]

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, dict[str, Any]]] = {
        "name": {
            "validation": "jsonschema",
            "schema": {"type": "string", "minLength": 1},
        },
        "description": {
            "validation": "jsonschema",
            "schema": {"type": "string"},
        },
        "collector_registry": {
            "validation": "jsonschema",
            # Loose JSON-schema check; the strict scope:key format check lives in
            # validate() so the error speaks in terms of scope/key rather than regex.
            "schema": {"type": "string", "minLength": 3},
        },
    }

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    collector_registry = models.CharField(max_length=512, unique=True)

    class Meta(BaseModel.Meta):
        db_table = "tap_cares_collector"

    def get_name(self) -> str:
        return self.name or ""

    def __str__(self) -> str:
        return self.name

    def validate(self) -> None:
        """Enforce the scope:key format on collector_registry.

        Short keys (no `:`) are rejected per req-tap-cares-collector-model-4.
        Both halves of the scope:key are validated with
        `_validate_collector_token`, the same helper the registry calls — so
        model-side and registry-side enforcement cannot drift
        (req-tap-cares-collector-registry-10).
        """
        value = self.collector_registry or ""
        if ":" not in value:
            raise ValidationError(
                {
                    "collector_registry": [
                        "Must use scope:key format; short keys are not allowed.",
                    ]
                }
            )
        scope_part, key_part = value.rsplit(":", 1)
        try:
            _validate_collector_token(scope_part)
            _validate_collector_token(key_part)
        except InvalidCollectorRegistryKeyError as exc:
            raise ValidationError({"collector_registry": [str(exc)]}) from exc
