"""OIDC Issuer — an OpenID Connect identity provider (the federated-identity convergence node)."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class OidcIssuer(BaseModel):
    """An OIDC identity provider, keyed by its canonical issuer host.

    The convergence node for federated identity. Independent observers reference
    the same issuer and land on one node: github enables its Actions issuer on a
    repo (``oidc_issuer —ENABLED_ON→ github_repository``), AWS IAM registers trust
    in it (``aws_iam_oidc_provider —TRUSTS_ISSUER→ oidc_issuer``), and Sigstore
    binds signing certs to identities it vouches for (``rekor_log_entry
    —IDENTITY_VOUCHED_BY→ oidc_issuer``). Ownership of those edges follows the
    principal that asserts the relationship; this node owns none of them.

    Existence is not trust: the presence of this node records only that an issuer
    identity was *referenced* by some observer. It asserts nothing about whether
    the issuer exists, is reachable, or is trusted — trust lives exclusively on
    explicit edges owned by the asserting plugin.

    ``issuer_url`` is the OIDC ``iss`` as observed (scheme'd when available), the
    display/reference value. ``host`` is the canonical, scheme-less form (see
    ``identity_core.issuer.canonical_issuer_url``); it is the identity key and the
    value AWS IAM's OIDC provider ``url`` matches. Independent observers converge
    because both the node id and this host derive from the one canonical form.

    Spec: plugins/identity_core/specs/spec-identity-core-v0.md (req-identity-core-model).
    """

    ENTITY_TYPE: ClassVar[str] = "identity_core__oidc_issuer"
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
        db_table = "identity_core__oidc_issuer"

    def get_name(self) -> str:
        # The node's name is its issuer_url — honest for every issuer, including
        # unknown ones. v0 deliberately ships no well-known-name catalog (that was
        # the same special-case-the-known-issuer pattern the github_core original
        # carried; see req-identity-core-nongoals).
        return self.issuer_url

    def __str__(self) -> str:
        return self.get_name()
