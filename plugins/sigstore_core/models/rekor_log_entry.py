"""Rekor Log Entry — one signed-artifact entry in a Rekor transparency log.

Stores immutable transparency-log facts only. The verification verdict
(`signature_verified`), the policy that produced it, and any failure
code/detail live as attributes on the `ATTESTED_BY` edge from the signed
entity to this node, not as fields here.

Spec: plugins/sigstore_core/specs/spec-sigstore-core-v0.md
(req-sigstore-core-models, req-sigstore-core-models-3).
"""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class RekorLogEntry(BaseModel):
    """One entry in a Rekor transparency log.

    Natural key: ``(log_key_id, log_index)``. ``log_key_id`` is the log's
    signing-key identifier as carried in the bundle's inclusion proof — the
    strongest canonical identity for *which* log signed the proof. The
    display-origin URL is captured as a regular field but not used for
    identity.

    Spec: plugins/sigstore_core/specs/spec-sigstore-core-v0.md (req-sigstore-core-models).
    """

    ENTITY_TYPE: ClassVar[str] = "rekor_log_entry"
    ENTITY_NAME: ClassVar[str] = "Rekor Log Entry"
    ENTITY_DESCRIPTION: ClassVar[str] = "An entry in a Rekor transparency log recording a Sigstore signature."
    ENTITY_ICON: ClassVar[str] = "rekor-log-entry"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {
        "sigstore.platform": "public-good",
        "sigstore.log_kind": "rekor",
    }
    # White cards with a green border, sitting on the sigstore_ca's green bed.
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "round-rectangle",
            "colors": {"fill": "#FFFFFF", "border": "#1E8E3E", "label": "#0B5323"},
        }
    }
    # The signing identity's OIDC issuer is an authoritative scalar field; the
    # IDENTITY_VOUCHED_BY edge to the matching oidc_issuer node must mirror it
    # exactly. Hotlink makes that drift-impossible (req-grid-hotlink). Uses the
    # `scalar` selector since the field's value IS the identifier.
    HOTLINKS: ClassVar[list[dict]] = [
        {
            "name": "rekor-issuer",
            "field": "signing_identity_issuer",
            "selector_type": "scalar",
            "selector": "",
            "edge_direction": "outbound",
            "edge_type": "IDENTITY_VOUCHED_BY",
            "mode": "exact",
        }
    ]

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "log_key_id": {"type": "string", "minLength": 1},
        "log_index": {"type": "integer", "minimum": 0},
        "rekor_log_url": {"type": "string"},
        "integrated_time": {"type": "string"},
        "entry_uuid": {"type": "string"},
        "tree_id": {"type": "string"},
        "tree_size_at_inclusion": {"type": ["integer", "null"]},
        "root_hash_at_inclusion": {"type": "string"},
        "entry_kind": {"type": "string"},
        "artifact_digest_alg": {"type": "string"},
        "artifact_digest": {"type": "string"},
        "signing_identity_uri": {"type": "string"},
        "signing_identity_issuer": {"type": "string"},
        "tags": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "log_key_id": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "log_index": {"validation": "jsonschema", "schema": {"type": "integer", "minimum": 0}},
        "rekor_log_url": {"validation": "jsonschema", "schema": {"type": "string"}},
        "integrated_time": {"validation": "jsonschema", "schema": {"type": "string"}},
        "entry_uuid": {"validation": "jsonschema", "schema": {"type": "string"}},
        "tree_id": {"validation": "jsonschema", "schema": {"type": "string"}},
        "tree_size_at_inclusion": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "root_hash_at_inclusion": {"validation": "jsonschema", "schema": {"type": "string"}},
        "entry_kind": {"validation": "jsonschema", "schema": {"type": "string"}},
        "artifact_digest_alg": {"validation": "jsonschema", "schema": {"type": "string"}},
        "artifact_digest": {"validation": "jsonschema", "schema": {"type": "string"}},
        "signing_identity_uri": {"validation": "jsonschema", "schema": {"type": "string"}},
        "signing_identity_issuer": {"validation": "jsonschema", "schema": {"type": "string"}},
        "tags": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["log_key_id", "log_index", "integrated_time", "entry_kind"]

    log_key_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    log_index = models.BigIntegerField(null=True, blank=True, db_index=True)
    rekor_log_url = models.URLField(max_length=512, blank=True, default="")
    integrated_time = models.CharField(max_length=64, blank=True, default="")
    entry_uuid = models.CharField(max_length=128, blank=True, default="")
    tree_id = models.CharField(max_length=128, blank=True, default="")
    tree_size_at_inclusion = models.BigIntegerField(null=True, blank=True)
    root_hash_at_inclusion = models.CharField(max_length=128, blank=True, default="")
    entry_kind = models.CharField(max_length=32, blank=True, default="", db_index=True)
    artifact_digest_alg = models.CharField(max_length=32, blank=True, default="")
    artifact_digest = models.CharField(max_length=128, blank=True, default="", db_index=True)
    signing_identity_uri = models.CharField(max_length=512, blank=True, default="", db_index=True)
    signing_identity_issuer = models.CharField(max_length=255, blank=True, default="")
    tags = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "rekor_log_entry"

    def get_name(self) -> str:
        if self.log_index is not None:
            return f"Rekor #{self.log_index}"
        return "Rekor entry"

    def __str__(self) -> str:
        return self.get_name()
