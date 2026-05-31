"""VdrReport — one emission of a FedRAMP 20x Vulnerability Detection and Response report."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class VdrReport(BaseModel):
    """One emission of the VDR report.

    The report aggregates vulnerability findings across SAST/SCA tools and
    applies the FedRAMP 20x VDR evaluation framework. The findings are
    separate `vdr_finding` nodes linked by `REPORTS_FINDING`; the report it
    cites is a `REFERENCES_SIGNAL` edge to the `ksi_signal`.

    Spec: spec-fedramp-20x-ksi-compliance-artifacts-v0.md.
    """

    ENTITY_TYPE: ClassVar[str] = "vdr_report"
    ENTITY_NAME: ClassVar[str] = "VDR Report"
    ENTITY_DESCRIPTION: ClassVar[str] = (
        "One emission of a FedRAMP 20x Vulnerability Detection and Response "
        "report — the aggregated vulnerability posture of a system."
    )
    ENTITY_ICON: ClassVar[str] = "vdr-report"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"compliance": "vdr"}

    # Signed file artifact — render as a file card in graph views: pale-olive
    # rectangle (light fill, saturated border) matching the AWS leaf-node pattern
    # so the document glyph stays a clean glyph and the title isn't lost against a
    # dark fill. Name sits bottom-center, outside the box, on the canvas.
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "colors": {"fill": "#EAE4C0", "border": "#8C7A1E", "label": "#463B08"},
            "label": {"valign": "bottom", "halign": "center", "position": "outside"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "report_version": {"type": "string"},
        "report_id": {"type": "string", "minLength": 1},
        "emitted_at": {"type": "string"},
        "system_id": {"type": "string"},
        "vdr_class": {"type": "string"},
        "ksi_signal_ref": {"type": "string"},
        "poam_ref": {"type": "string"},
        "summary": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "report_id": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "summary": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name", "report_id"]

    name = models.CharField(max_length=255, blank=True, default="")
    report_version = models.CharField(max_length=32, blank=True, default="")
    report_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    emitted_at = models.CharField(max_length=64, blank=True, default="")
    system_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    vdr_class = models.CharField(max_length=16, blank=True, default="")
    ksi_signal_ref = models.CharField(max_length=512, blank=True, default="")
    poam_ref = models.CharField(max_length=255, blank=True, default="")
    # Derived rollup counts (by_pain, blocking, kev, totals) — a denormalized
    # summary; the queryable substance is the vdr_finding nodes.
    summary = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "vdr_report"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.get_name()
