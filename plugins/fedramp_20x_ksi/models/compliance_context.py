"""ComplianceContext — per-regime compliance posture metadata on a Grid."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class ComplianceContext(BaseModel):
    """A Grid's compliance posture under a single regime.

    Each ComplianceContext captures the Grid's posture under one compliance
    regime (FedRAMP 20x, SOC2, CMMC, ISO 27001, ...). A Grid that operates
    under multiple regimes carries one ComplianceContext per regime.

    The `regime` field is the primary discriminator — a slug identifying
    which compliance framework the context belongs to (e.g. "fedramp_20x").
    Framework-specific posture fields live additively on the same model
    (`fedramp_class` for FedRAMP 20x today; future `soc2_type`,
    `cmmc_level`, etc. land as additional fields when those frameworks
    are scoped). Fields not relevant to a given instance's regime hold
    their default empty value.

    Each instance carries the dimension of its regime (e.g.
    `{"compliance": "fedramp-20x"}` for a FedRAMP 20x context). The
    DEFAULT_DIMENSIONS fallback (`{"compliance": "context"}`) is a generic
    meta-marker for instances created without explicit dimensions; seed
    bundles set the per-regime dimension explicitly.

    Cardinality: one ComplianceContext per regime per Grid in v0, enforced
    by seeding convention rather than schema. Consumer queries filter by
    `regime` (or by the matching `compliance` dimension) to select the
    relevant context for a given framework's panels.

    Spec: plugins/fedramp_20x_ksi/specs/spec-fedramp-20x-ksi-compliance-context.md
    """

    ENTITY_TYPE: ClassVar[str] = "compliance_context"
    ENTITY_NAME: ClassVar[str] = "Compliance Context"
    ENTITY_DESCRIPTION: ClassVar[str] = (
        "Per-regime compliance posture metadata on a Grid. Each instance "
        "represents the Grid's posture under one compliance regime "
        "(FedRAMP 20x, SOC2, CMMC, ...). One ComplianceContext per regime "
        "per Grid in v0."
    )
    ENTITY_ICON: ClassVar[str] = "compliance-context"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"compliance": "context"}

    # Empty string explicitly allowed — expresses "FedRAMP 20x is not in scope
    # for this context" (e.g. a SOC2-regime context). Default `b` matches the
    # demo deployment's working baseline (Class B / Low).
    _FEDRAMP_CLASS_VALUES = ["", "a", "b", "c", "d"]

    # Regime slug pattern: lowercase, snake_case-friendly. Pattern-validated
    # rather than hard-enumerated so future compliance plugins can register
    # their regime slug without a model migration here.
    _REGIME_PATTERN = r"^[a-z][a-z0-9_]+$"

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "regime": {"type": "string", "minLength": 1},
        "fedramp_class": {"type": "string", "enum": _FEDRAMP_CLASS_VALUES},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {
            "validation": "jsonschema",
            "schema": {"type": "string", "minLength": 1},
        },
        "description": {"validation": "jsonschema", "schema": {"type": "string"}},
        "regime": {
            "validation": "jsonschema",
            "schema": {
                "type": "string",
                "minLength": 1,
                "pattern": _REGIME_PATTERN,
            },
        },
        "fedramp_class": {
            "validation": "jsonschema",
            "schema": {"type": "string", "enum": _FEDRAMP_CLASS_VALUES},
        },
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name", "regime"]

    name = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    regime = models.CharField(max_length=64, blank=True, default="", db_index=True)
    fedramp_class = models.CharField(
        max_length=8, blank=True, default="b", db_index=True
    )

    class Meta(BaseModel.Meta):
        db_table = "compliance_context"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.get_name()
