"""OIDC Issuer — an OpenID Connect identity provider (the GitHub Actions issuer in v0)."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class OidcIssuer(BaseModel):
    """An OIDC identity provider, keyed by its issuer URL.

    The convergence node for federated identity: AWS IAM registers trust in it
    (``aws_iam_oidc_provider —TRUSTS_ISSUER→``) and Sigstore binds signing certs
    to identities from it (``rekor_log_entry —IDENTITY_VOUCHED_BY→``). v0 models
    one instance — GitHub Actions' issuer, ``https://token.actions.githubusercontent.com``
    — synthesized as a singleton by the github_core collector.

    ``issuer_url`` is the canonical OIDC ``iss`` (with scheme), the natural key and
    the value Sigstore's cert carries. ``host`` is the scheme-less form AWS IAM
    stores on its OIDC provider, kept as a separate field so the derived
    ``TRUSTS_ISSUER`` link can match ``aws_iam_oidc_provider.url`` exactly.

    Spec: plugins/github_core/specs/spec-github-core-v0.md (req-github-core-models).
    """

    ENTITY_TYPE: ClassVar[str] = "oidc_issuer"
    ENTITY_NAME: ClassVar[str] = "OIDC Issuer"
    ENTITY_DESCRIPTION: ClassVar[str] = "An OpenID Connect identity provider (issuer)."
    ENTITY_ICON: ClassVar[str] = "oidc-issuer"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"identity.protocol": "oidc"}
    # Identity-anchor palette — amber/gold, distinct from github-blue, AWS-beige,
    # and sigstore-green; the hub all three reference.
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "round-rectangle",
            "colors": {"fill": "#FFF8E1", "border": "#F9A825", "label": "#5F4300"},
            "label": {"valign": "top", "halign": "center", "position": "outside"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "issuer_url": {"type": "string", "minLength": 1},
        "host": {"type": "string"},
        "provider": {"type": "string"},
        "configuration": {"type": "object"},
        "tags": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "issuer_url": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "host": {"validation": "jsonschema", "schema": {"type": "string"}},
        "provider": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
        "tags": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["issuer_url"]

    issuer_url = models.CharField(max_length=512, blank=True, default="", db_index=True)
    host = models.CharField(max_length=255, blank=True, default="", db_index=True)
    provider = models.CharField(max_length=64, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "oidc_issuer"

    def get_name(self) -> str:
        return self.issuer_url

    def __str__(self) -> str:
        return self.get_name()
