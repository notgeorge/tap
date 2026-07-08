"""Compliance boundary — an authorization boundary (regime-agnostic)."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class ComplianceBoundary(BaseModel):
    """An authorization boundary — the perimeter of a single authorization.

    A boundary names the set of system components in scope for a single
    compliance authorization (a FedRAMP ATO, a SOC2 audit scope, an ISO
    certification scope, …). Components are linked to their boundary by the
    ``SCOPED_TO_COMPLIANCE_BOUNDARY`` edge (component → boundary). "Identify
    everything inside the boundary" is then a fan-in query over that edge.

    Regime-agnostic substrate: the scoping concept is shared across regimes;
    the regime is layered per-instance, not baked into the model.

    The initial pass carries only name and description; structured metadata
    (impact level, authorization dates, authorizing official) becomes typed
    fields when a consumer needs them rather than a speculative JSON blob now.

    Spec: plugins/compliance_core/specs/spec-compliance-core-v0.md
    """

    ENTITY_TYPE: ClassVar[str] = "compliance_core__compliance_boundary"
    ENTITY_NAME: ClassVar[str] = "Authorization Boundary"
    ENTITY_DESCRIPTION: ClassVar[str] = (
        "An authorization boundary — the perimeter of system components in "
        "scope for a single compliance authorization. Components link to it "
        "via the SCOPED_TO_COMPLIANCE_BOUNDARY edge."
    )
    # No type icon: the red box from DEFAULT_DISPLAY is sufficient to read the
    # boundary on the graph, and the icon badge added visual noise.
    ENTITY_ICON: ClassVar[str] = ""
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"compliance": "boundary"}
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "round-rectangle",
            "colors": {"fill": "#FBE4E4", "border": "#D93535", "label": "#A11B1B"},
            "label": {"valign": "top", "halign": "center", "position": "outside"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "description": {"validation": "jsonschema", "schema": {"type": "string"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "compliance_core__compliance_boundary"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.get_name()
