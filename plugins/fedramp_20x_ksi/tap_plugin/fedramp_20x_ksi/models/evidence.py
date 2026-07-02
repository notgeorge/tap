"""Evidence — an artifact that demonstrates the state of a compliance check."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class Evidence(BaseModel):
    """Evidence is a supporting artifact attached to a finding via a HAS_EVIDENCE edge.

    The model is intentionally minimal in v1: name, description, kind. The verdict
    the evidence supports — passing, violation, informational — lives on the
    HAS_EVIDENCE edge as `support_kind`, not on the evidence record itself. That
    keeps a single evidence artifact reusable across multiple findings with
    different relationships.

    Spec: plugins/fedramp_20x_ksi/specs/spec-fedramp-20x-ksi-evidence.md
    """

    ENTITY_TYPE: ClassVar[str] = "evidence"
    ENTITY_NAME: ClassVar[str] = "Evidence"
    ENTITY_DESCRIPTION: ClassVar[str] = (
        "A supporting artifact for a compliance finding — screenshot, scanner output, "
        "policy document, attestation, log excerpt, or other material."
    )
    ENTITY_ICON: ClassVar[str] = "evidence"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"compliance": "fedramp-20x"}

    _KIND_VALUES = [
        "screenshot",
        "scanner_output",
        "policy_doc",
        "attestation",
        "log_excerpt",
        "other",
    ]

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "kind": {"type": "string", "enum": _KIND_VALUES},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {
            "validation": "jsonschema",
            "schema": {"type": "string", "minLength": 1},
        },
        "description": {"validation": "jsonschema", "schema": {"type": "string"}},
        "kind": {
            "validation": "jsonschema",
            "schema": {"type": "string", "enum": _KIND_VALUES},
        },
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name", "kind"]

    name = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    kind = models.CharField(max_length=32, blank=True, default="other", db_index=True)

    class Meta(BaseModel.Meta):
        db_table = "evidence"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.get_name()
