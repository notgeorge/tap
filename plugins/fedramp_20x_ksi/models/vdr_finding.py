"""VdrFinding — one vulnerability finding carried by a VDR report."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class VdrFinding(BaseModel):
    """One vulnerability finding — and the home of Sam's VDR evaluation framework.

    The VDR framework — PAIN (N1-N5 severity), IRV (internet-reachable), LEV
    (likely-exploitable), KEV (CISA Known-Exploited), and the Class-C
    remediation SLA — is the evaluation schema of a finding, so it lives here
    as typed, queryable fields: "every pain >= N4 finding that is
    internet_reachable and past remediation_due_at" is a Gryphon WHERE.

    A report's `findings[]` (disposition `open`) and `risk_accepted[]`
    (disposition `risk-accepted`) are both `vdr_finding` nodes, discriminated
    by `current_disposition`.

    Spec: spec-fedramp-20x-ksi-compliance-artifacts-v0.md.
    """

    ENTITY_TYPE: ClassVar[str] = "vdr_finding"
    ENTITY_NAME: ClassVar[str] = "VDR Finding"
    ENTITY_DESCRIPTION: ClassVar[str] = (
        "One vulnerability finding from a VDR report — carrying its FedRAMP "
        "20x evaluation (PAIN / IRV / LEV / KEV) and Class-C remediation SLA."
    )
    ENTITY_ICON: ClassVar[str] = "vdr-finding"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"compliance": "vdr"}

    _SOURCE_VALUES = ["opa", "checkov", "tfsec", "dependabot", "checkov-suppression", ""]
    _PAIN_VALUES = ["N1", "N2", "N3", "N4", "N5", ""]
    _DISPOSITION_VALUES = ["open", "risk-accepted", ""]

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "tracking_id": {"type": "string", "minLength": 1},
        "source": {"type": "string"},
        "tool_id": {"type": "string"},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "resource": {"type": "string"},
        "cve": {"type": "string"},
        "first_detected": {"type": "string"},
        "days_since_first_detected": {"type": ["integer", "null"]},
        "pain": {"type": "string"},
        "internet_reachable": {"type": "boolean"},
        "likely_exploitable": {"type": "boolean"},
        "is_kev": {"type": "boolean"},
        "current_disposition": {"type": "string"},
        "remediation_sla_days": {"type": ["integer", "null"]},
        "remediation_due_at": {"type": "string"},
        "is_blocking": {"type": "boolean"},
        "block_reason": {"type": "string"},
        "explanation": {"type": "string"},
        "poam_ref": {"type": "string"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "tracking_id": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "source": {"validation": "jsonschema", "schema": {"type": "string", "enum": _SOURCE_VALUES}},
        "pain": {"validation": "jsonschema", "schema": {"type": "string", "enum": _PAIN_VALUES}},
        "current_disposition": {"validation": "jsonschema", "schema": {"type": "string", "enum": _DISPOSITION_VALUES}},
        "days_since_first_detected": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "remediation_sla_days": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name", "tracking_id"]

    name = models.CharField(max_length=255, blank=True, default="")
    tracking_id = models.CharField(max_length=512, blank=True, default="", db_index=True)
    source = models.CharField(max_length=32, blank=True, default="", db_index=True)
    tool_id = models.CharField(max_length=255, blank=True, default="")
    title = models.CharField(max_length=512, blank=True, default="")
    description = models.TextField(blank=True, default="")
    resource = models.CharField(max_length=512, blank=True, default="")
    cve = models.CharField(max_length=64, blank=True, default="", db_index=True)
    first_detected = models.CharField(max_length=64, blank=True, default="")
    days_since_first_detected = models.IntegerField(blank=True, null=True)
    # Sam's VDR evaluation framework, as typed fields.
    pain = models.CharField(max_length=8, blank=True, default="", db_index=True)
    internet_reachable = models.BooleanField(default=False)
    likely_exploitable = models.BooleanField(default=False)
    is_kev = models.BooleanField(default=False, db_index=True)
    current_disposition = models.CharField(max_length=32, blank=True, default="", db_index=True)
    remediation_sla_days = models.IntegerField(blank=True, null=True)
    remediation_due_at = models.CharField(max_length=64, blank=True, default="")
    is_blocking = models.BooleanField(default=False, db_index=True)
    block_reason = models.TextField(blank=True, default="")
    # Risk-accepted findings carry these (the VDR-RPT-AVI fields).
    explanation = models.TextField(blank=True, default="")
    poam_ref = models.CharField(max_length=255, blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "vdr_finding"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.get_name()
