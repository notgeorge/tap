"""KsiValidation — one validation result carried by a KSI signal."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class KsiValidation(BaseModel):
    """One entry of a KSI signal's `validations[]` array.

    A policy result (pass/fail) against a set of components. The components it
    evaluated are `EVALUATES_COMPONENT` edges (the signal schema's
    `component_refs` join); the violations it found are `ksi_violation` nodes
    linked by `REPORTS_VIOLATION`. Neither is a stored array — both are the
    graph.

    Spec: spec-fedramp-20x-ksi-compliance-artifacts-v0.md.
    """

    ENTITY_TYPE: ClassVar[str] = "fedramp_20x_ksi__ksi_validation"
    ENTITY_NAME: ClassVar[str] = "KSI Validation"
    ENTITY_DESCRIPTION: ClassVar[str] = (
        "One validation result a KSI signal carries — a policy pass/fail "
        "against the components it evaluated."
    )
    ENTITY_ICON: ClassVar[str] = "ksi-validation"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"compliance": "ksi-signal"}

    _RESULT_VALUES = ["pass", "fail", ""]

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "validation_id": {"type": "string", "minLength": 1},
        "policy_id": {"type": "string"},
        "policy_version": {"type": "string"},
        "result": {"type": "string"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "validation_id": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "result": {"validation": "jsonschema", "schema": {"type": "string", "enum": _RESULT_VALUES}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name", "validation_id"]

    name = models.CharField(max_length=255, blank=True, default="")
    validation_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    policy_id = models.CharField(max_length=255, blank=True, default="")
    policy_version = models.CharField(max_length=64, blank=True, default="")
    result = models.CharField(max_length=16, blank=True, default="", db_index=True)

    class Meta(BaseModel.Meta):
        db_table = "fedramp_20x_ksi__ksi_validation"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.get_name()
