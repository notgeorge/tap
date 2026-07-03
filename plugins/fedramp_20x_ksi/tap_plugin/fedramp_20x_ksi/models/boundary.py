"""Boundary — a FedRAMP authorization (ATO) boundary."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class Boundary(BaseModel):
    """A FedRAMP authorization boundary — the perimeter of an ATO.

    A Boundary names an authorization boundary: the set of system
    components in scope for a single FedRAMP authorization. Components
    are linked to their Boundary by the ``SCOPED_TO_BOUNDARY`` edge
    (component → boundary). "Identify everything inside the boundary"
    is then a fan-in query over that edge.

    The initial pass carries only name and description; structured
    FedRAMP metadata (impact level, ATO dates, authorizing official)
    becomes typed fields when a consumer needs them rather than a
    speculative JSON blob now.

    Spec: plugins/fedramp_20x_ksi/specs/spec-fedramp-20x-ksi-boundary.md
    """

    ENTITY_TYPE: ClassVar[str] = "fedramp_20x_ksi__boundary"
    ENTITY_NAME: ClassVar[str] = "Authorization Boundary"
    ENTITY_DESCRIPTION: ClassVar[str] = (
        "A FedRAMP authorization boundary — the perimeter of system "
        "components in scope for a single ATO. Components link to it "
        "via the SCOPED_TO_BOUNDARY edge."
    )
    # No type icon: the red box from DEFAULT_DISPLAY is sufficient to read the
    # boundary on the graph, and the icon badge added visual noise.
    ENTITY_ICON: ClassVar[str] = ""
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"compliance": "fedramp_20x_ksi__boundary"}
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
        db_table = "fedramp_20x_ksi__boundary"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.get_name()
