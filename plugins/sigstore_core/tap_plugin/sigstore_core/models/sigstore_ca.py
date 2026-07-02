"""Sigstore CA — a certificate authority that issues Sigstore signing certs.

v0 sees only the Sigstore public-good Fulcio instance; ``ca_kind`` and
``ca_url`` leave room for private Fulcio deployments and future non-Fulcio
CAs without a schema change.

Spec: plugins/sigstore_core/specs/spec-sigstore-core-v0.md
(req-sigstore-core-models, req-sigstore-core-models-4).
"""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class SigstoreCa(BaseModel):
    """A certificate authority that issued one or more Sigstore signing certs.

    Natural key: ``ca_url``.

    Spec: plugins/sigstore_core/specs/spec-sigstore-core-v0.md (req-sigstore-core-models).
    """

    ENTITY_TYPE: ClassVar[str] = "sigstore_ca"
    ENTITY_NAME: ClassVar[str] = "Sigstore CA"
    ENTITY_DESCRIPTION: ClassVar[str] = "A certificate authority that issues Sigstore signing certificates."
    ENTITY_ICON: ClassVar[str] = "sigstore-ca"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {
        "sigstore.platform": "public-good",
        "sigstore.ca_kind": "fulcio",
    }
    # Sigstore family palette — a green scheme, distinct from github-blue and
    # AWS-beige, marking the external keyless-signing / transparency system.
    # The CA is the outer box; rekor entries are the cards inside it.
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "round-rectangle",
            "colors": {"fill": "#E6F4EA", "border": "#1E8E3E", "label": "#0B5323"},
            "label": {"valign": "top", "halign": "center", "position": "outside"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "ca_url": {"type": "string", "minLength": 1},
        "ca_name": {"type": "string"},
        "ca_kind": {"type": "string"},
        "trust_root_source": {"type": "string"},
        "trust_root_fetched_at": {"type": "string"},
        "tags": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "ca_url": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "ca_name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "ca_kind": {"validation": "jsonschema", "schema": {"type": "string"}},
        "trust_root_source": {"validation": "jsonschema", "schema": {"type": "string"}},
        "trust_root_fetched_at": {"validation": "jsonschema", "schema": {"type": "string"}},
        "tags": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["ca_url", "ca_kind", "trust_root_source"]

    ca_url = models.URLField(max_length=512, blank=True, default="", db_index=True)
    ca_name = models.CharField(max_length=255, blank=True, default="")
    ca_kind = models.CharField(max_length=32, blank=True, default="fulcio", db_index=True)
    trust_root_source = models.CharField(max_length=64, blank=True, default="")
    trust_root_fetched_at = models.CharField(max_length=64, blank=True, default="")
    tags = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "sigstore_ca"

    def get_name(self) -> str:
        return self.ca_name or self.ca_url or "Sigstore CA"

    def __str__(self) -> str:
        return self.get_name()
