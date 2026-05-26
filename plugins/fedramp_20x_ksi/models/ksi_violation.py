"""KsiViolation — one policy violation reported by a failed KSI validation."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class KsiViolation(BaseModel):
    """One specific finding from a failed KSI validation.

    The signal schema notes violations are "the same shape as the OPA
    compliance_report violations the existing pipeline produces."

    Open question, recorded deliberately (see
    spec-fedramp-20x-ksi-compliance-artifacts-v0.md § KSI Violation Model):
    `ksi_violation` is a cousin of `finding` — both represent "something wrong
    with the system," and the VDR collector ingests OPA output, so a
    `ksi_violation` and a `vdr_finding`-from-OPA can be the same underlying
    issue in two artifacts. v0 keeps them distinct (a raw policy violation is
    not catalog-tied the way `finding` is). `ksi_violation` lives alongside
    `finding` in this plugin so a future unify/shared-base decision has both
    models in one place.
    """

    ENTITY_TYPE: ClassVar[str] = "ksi_violation"
    ENTITY_NAME: ClassVar[str] = "KSI Violation"
    ENTITY_DESCRIPTION: ClassVar[str] = (
        "One policy violation a failed KSI validation reports — type, "
        "message, severity, and the resource it was found on."
    )
    ENTITY_ICON: ClassVar[str] = "ksi-violation"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"compliance": "ksi-signal"}

    _SEVERITY_VALUES = ["LOW", "MEDIUM", "HIGH", "CRITICAL", ""]

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "violation_type": {"type": "string"},
        "message": {"type": "string"},
        "severity": {"type": "string"},
        "resource": {"type": "string"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "severity": {"validation": "jsonschema", "schema": {"type": "string", "enum": _SEVERITY_VALUES}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    violation_type = models.CharField(max_length=128, blank=True, default="", db_index=True)
    message = models.TextField(blank=True, default="")
    severity = models.CharField(max_length=16, blank=True, default="", db_index=True)
    resource = models.CharField(max_length=512, blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "ksi_violation"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.get_name()
