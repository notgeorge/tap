"""Exception — a formal acceptance of one or more findings."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class ComplianceException(BaseModel):
    """An exception covers one or more findings, formally accepting the risk they represent.

    The Python class is `ComplianceException` rather than `Exception` to avoid
    shadowing the Python built-in in any module that imports this model. The
    entity-type slug remains `"exception"` — that's what GRIFT, the service
    layer, and the rest of TAP see externally.

    v1 shape is minimal: name, description, status. By convention the `description`
    carries the business justification. Additional workflow fields (expiration_date,
    approver, review cadence) are deferred as explicit Future work in the spec.

    Spec: plugins/fedramp_20x_ksi/specs/spec-fedramp-20x-ksi-finding.md
    """

    ENTITY_TYPE: ClassVar[str] = "exception"
    ENTITY_NAME: ClassVar[str] = "Exception"
    ENTITY_DESCRIPTION: ClassVar[str] = (
        "A formal acceptance of one or more findings, typically recording "
        "the rationale for not remediating."
    )
    ENTITY_ICON: ClassVar[str] = "exception"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"compliance": "fedramp-20x"}

    _STATUS_VALUES = ["active", "expired", "revoked"]

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "status": {"type": "string", "enum": _STATUS_VALUES},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {
            "validation": "jsonschema",
            "schema": {"type": "string", "minLength": 1},
        },
        "description": {"validation": "jsonschema", "schema": {"type": "string"}},
        "status": {
            "validation": "jsonschema",
            "schema": {"type": "string", "enum": _STATUS_VALUES},
        },
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=16, blank=True, default="active", db_index=True)

    class Meta(BaseModel.Meta):
        db_table = "compliance_exception"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.get_name()
