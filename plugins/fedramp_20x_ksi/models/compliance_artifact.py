"""ComplianceArtifact — a fetched compliance document kept whole."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class ComplianceArtifact(BaseModel):
    """A fetched compliance rendering kept whole — OSCAL SSP, OSCAL POA&M, IIW.

    These are downstream renderings of the same canonical inventory the KSI
    signal carries (`build-iiw.py` / `build-oscal-ssp.py` read the signal as
    their source). Decomposing them would re-model that inventory, so they are
    kept whole: typed metadata + the document as a blob. One model; `kind`
    discriminates.

    Spec: spec-fedramp-20x-ksi-compliance-artifacts-v0.md.
    """

    ENTITY_TYPE: ClassVar[str] = "compliance_artifact"
    ENTITY_NAME: ClassVar[str] = "Compliance Artifact"
    ENTITY_DESCRIPTION: ClassVar[str] = (
        "A fetched compliance rendering kept whole — an OSCAL SSP, OSCAL "
        "POA&M, or IIW inventory — with fetch and signature-verification "
        "metadata and the document body retained."
    )
    ENTITY_ICON: ClassVar[str] = "compliance-artifact"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"compliance": "compliance-artifact"}

    _KIND_VALUES = ["oscal_ssp", "oscal_poam", "iiw", ""]

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "kind": {"type": "string"},
        "source_url": {"type": "string"},
        "content_type": {"type": "string"},
        "fetched_at": {"type": "string"},
        "size_bytes": {"type": ["integer", "null"]},
        "content": {"type": ["object", "string", "array", "null"]},
        "signature_verified": {"type": ["boolean", "null"]},
        "signed_by": {"type": "string"},
        "rekor_log_index": {"type": "string"},
        "verified_at": {"type": "string"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "kind": {"validation": "jsonschema", "schema": {"type": "string", "enum": _KIND_VALUES}},
        "size_bytes": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "signature_verified": {"validation": "jsonschema", "schema": {"type": ["boolean", "null"]}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name", "kind"]

    name = models.CharField(max_length=255, blank=True, default="")
    kind = models.CharField(max_length=32, blank=True, default="", db_index=True)
    source_url = models.CharField(max_length=512, blank=True, default="")
    content_type = models.CharField(max_length=128, blank=True, default="")
    fetched_at = models.CharField(max_length=64, blank=True, default="")
    size_bytes = models.BigIntegerField(blank=True, null=True)
    # The document body — a parsed dict for OSCAL JSON, raw text for IIW CSV.
    content = models.JSONField(default=dict, blank=True)
    # Signature verification result — populated by the collector.
    signature_verified = models.BooleanField(blank=True, null=True)
    signed_by = models.CharField(max_length=512, blank=True, default="")
    rekor_log_index = models.CharField(max_length=64, blank=True, default="")
    verified_at = models.CharField(max_length=64, blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "compliance_artifact"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.get_name()
