"""KsiSignal — one emission of a FedRAMP 20x KSI validation signal."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class KsiSignal(BaseModel):
    """One emission of the KSI signal document.

    The KSI signal is a graph serialized to JSON (see
    spec-fedramp-20x-ksi-compliance-artifacts-v0.md). This model is the
    emission's spine: top-level identity, flattened provenance / ownership /
    disclosure, and the collector-populated signature verification result.
    Components and validations are separate nodes (`ksi_component`,
    `ksi_validation`) linked by edges.

    Two emissions with the same `signal_id` are the same observation.
    """

    ENTITY_TYPE: ClassVar[str] = "ksi_signal"
    ENTITY_NAME: ClassVar[str] = "KSI Signal"
    ENTITY_DESCRIPTION: ClassVar[str] = (
        "One emission of a FedRAMP 20x KSI validation signal — identity, "
        "provenance, ownership, disclosure, and signature verification result."
    )
    ENTITY_ICON: ClassVar[str] = "ksi-signal"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"compliance": "ksi-signal"}

    _EMITTER_VALUES = ["deploy", "runtime"]

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "signal_version": {"type": "string"},
        "signal_id": {"type": "string", "minLength": 1},
        "emitted_at": {"type": "string"},
        "emitter": {"type": "string"},
        "csp": {"type": "string"},
        "system_id": {"type": "string"},
        "provenance_builder_id": {"type": "string"},
        "provenance_builder_run_id": {"type": "string"},
        "provenance_builder_version": {"type": "string"},
        "provenance_source_repository": {"type": "string"},
        "provenance_source_commit": {"type": "string"},
        "provenance_source_ref": {"type": "string"},
        "system_owner": {"type": "string"},
        "application_owner": {"type": "string"},
        "operator_contact": {"type": "string"},
        "authorization_status": {"type": "string"},
        "fedramp_certified": {"type": ["boolean", "null"]},
        "disclosure_remarks": {"type": "string"},
        "attestation": {"type": "object"},
        "signature_verified": {"type": ["boolean", "null"]},
        "signed_by": {"type": "string"},
        "rekor_log_index": {"type": "string"},
        "verified_at": {"type": "string"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "signal_id": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "emitter": {"validation": "jsonschema", "schema": {"type": "string", "enum": _EMITTER_VALUES + [""]}},
        "fedramp_certified": {"validation": "jsonschema", "schema": {"type": ["boolean", "null"]}},
        "attestation": {"validation": "jsonschema", "schema": {"type": "object"}},
        "signature_verified": {"validation": "jsonschema", "schema": {"type": ["boolean", "null"]}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name", "signal_id"]

    name = models.CharField(max_length=255, blank=True, default="")
    signal_version = models.CharField(max_length=32, blank=True, default="")
    signal_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    emitted_at = models.CharField(max_length=64, blank=True, default="")
    emitter = models.CharField(max_length=32, blank=True, default="")
    csp = models.CharField(max_length=64, blank=True, default="")
    system_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    # Provenance (flattened from the signal's provenance.builder / provenance.source).
    provenance_builder_id = models.CharField(max_length=512, blank=True, default="")
    provenance_builder_run_id = models.CharField(max_length=128, blank=True, default="")
    provenance_builder_version = models.CharField(max_length=64, blank=True, default="")
    provenance_source_repository = models.CharField(max_length=512, blank=True, default="")
    provenance_source_commit = models.CharField(max_length=64, blank=True, default="")
    provenance_source_ref = models.CharField(max_length=255, blank=True, default="")
    # Ownership (flattened).
    system_owner = models.CharField(max_length=255, blank=True, default="")
    application_owner = models.CharField(max_length=255, blank=True, default="")
    operator_contact = models.CharField(max_length=255, blank=True, default="")
    # Disclosure (flattened).
    authorization_status = models.CharField(max_length=64, blank=True, default="")
    fedramp_certified = models.BooleanField(blank=True, null=True)
    disclosure_remarks = models.TextField(blank=True, default="")
    # provenance.attestation — schema-declared free-form (the Sigstore bundle).
    attestation = models.JSONField(default=dict, blank=True)
    # Signature verification result — populated by the collector, not the document.
    signature_verified = models.BooleanField(blank=True, null=True)
    signed_by = models.CharField(max_length=512, blank=True, default="")
    rekor_log_index = models.CharField(max_length=64, blank=True, default="")
    verified_at = models.CharField(max_length=64, blank=True, default="")

    class Meta(BaseModel.Meta):
        db_table = "ksi_signal"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.get_name()
