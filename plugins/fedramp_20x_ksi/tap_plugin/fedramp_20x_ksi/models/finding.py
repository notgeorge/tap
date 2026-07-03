"""Finding — a single instance of non-compliance or risk observed against an asset."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class Finding(BaseModel):
    """A finding is the bridge between an asset in the graph and a compliance requirement.

    v1 shape is deliberately minimal: name, description, status. Lifecycle events
    (being granted an exception, being resolved) are modeled as separate entities
    connected by edges — not as fields on the finding. Exception coverage is a
    graph-relational fact expressed via `COVERS_FINDING` edges and queried via
    traversal; it does not project onto `status`.

    Spec: plugins/fedramp_20x_ksi/specs/spec-fedramp-20x-ksi-finding.md
    """

    ENTITY_TYPE: ClassVar[str] = "fedramp_20x_ksi__finding"
    ENTITY_NAME: ClassVar[str] = "Finding"
    ENTITY_DESCRIPTION: ClassVar[str] = (
        "A single instance of non-compliance or risk observed against an asset, "
        "related to one or more compliance requirements."
    )
    ENTITY_ICON: ClassVar[str] = "finding"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"compliance": "fedramp-20x"}

    _STATUS_VALUES = ["open", "resolved"]

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "summary": {"type": "string"},
        "description": {"type": "string"},
        "status": {"type": "string", "enum": _STATUS_VALUES},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {
            "validation": "jsonschema",
            "schema": {"type": "string", "minLength": 1},
        },
        "summary": {"validation": "jsonschema", "schema": {"type": "string"}},
        "description": {"validation": "jsonschema", "schema": {"type": "string"}},
        "status": {
            "validation": "jsonschema",
            "schema": {"type": "string", "enum": _STATUS_VALUES},
        },
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    summary = models.CharField(max_length=500, blank=True, default="")
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=16, blank=True, default="open", db_index=True)

    class Meta(BaseModel.Meta):
        db_table = "fedramp_20x_ksi__finding"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.get_name()
