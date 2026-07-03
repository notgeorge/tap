"""IAM OIDC Provider — a federated identity provider registered in IAM."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class IamOidcProvider(BaseModel):
    """An AWS IAM OpenID Connect identity provider.

    Registers an external OIDC issuer (e.g. GitHub Actions' token issuer at
    ``token.actions.githubusercontent.com``) as a trusted federated identity
    provider in this AWS account. IAM roles can then have trust policies
    that allow ``sts:AssumeRoleWithWebIdentity`` from this provider.

    Separate from AWS IAM Identity Center (formerly SSO): that's a different
    service for human-user SSO; this is for federated machine identities
    (CI runners, K8s service accounts, etc.).
    """

    ENTITY_TYPE: ClassVar[str] = "aws_core__aws_iam_oidc_provider"
    ENTITY_NAME: ClassVar[str] = "IAM OIDC Provider"
    ENTITY_DESCRIPTION: ClassVar[str] = "A federated OpenID Connect identity provider registered in AWS IAM."
    ENTITY_ICON: ClassVar[str] = "aws-iam"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "colors": {"fill": "#F5C6CC", "border": "#DD344C", "label": "#3D0E15"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "provider_arn": {"type": "string"},
        "url": {"type": "string"},
        "client_ids": {"type": "array"},
        "thumbprints": {"type": "array"},
        "tags": {"type": "object"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "provider_arn": {"validation": "jsonschema", "schema": {"type": "string"}},
        "url": {"validation": "jsonschema", "schema": {"type": "string"}},
        "client_ids": {"validation": "jsonschema", "schema": {"type": "array"}},
        "thumbprints": {"validation": "jsonschema", "schema": {"type": "array"}},
        "tags": {"validation": "jsonschema", "schema": {"type": "object"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    provider_arn = models.CharField(max_length=512, blank=True, default="")
    url = models.CharField(max_length=512, blank=True, default="")
    client_ids = models.JSONField(default=list, blank=True)
    thumbprints = models.JSONField(default=list, blank=True)
    tags = models.JSONField(default=dict, blank=True)
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_core__aws_iam_oidc_provider"

    def get_name(self) -> str:
        return self.name or self.url or self.provider_arn

    def __str__(self) -> str:
        return self.get_name()
