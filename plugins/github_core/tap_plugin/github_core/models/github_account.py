"""GitHub Account — owner/user/org account on GitHub."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class GithubAccount(BaseModel):
    """A GitHub account (user or organization).

    Spec: plugins/github_core/specs/spec-github-core-v0.md (req-github-core-models)
    """

    ENTITY_TYPE: ClassVar[str] = "github_core__github_account"
    ENTITY_NAME: ClassVar[str] = "GitHub Account"
    ENTITY_DESCRIPTION: ClassVar[str] = "A GitHub user or organization account."
    ENTITY_ICON: ClassVar[str] = "github-account"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"github.platform": "github.com"}
    # Mid level of the GitHub nesting palette — light accent blue. See
    # github_platform.GithubPlatform.DEFAULT_DISPLAY for the family scheme.
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "round-rectangle",
            "colors": {"fill": "#DDF4FF", "border": "#54AEFF", "label": "#0A3069"},
            "label": {"valign": "top", "halign": "center", "position": "outside"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "login": {"type": "string", "minLength": 1},
        "github_id": {"type": ["integer", "null"]},
        "account_type": {"type": "string"},
        "html_url": {"type": "string"},
        "configuration": {"type": "object"},
        "tags": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "login": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "github_id": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "account_type": {"validation": "jsonschema", "schema": {"type": "string"}},
        "html_url": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
        "tags": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["login"]

    login = models.CharField(max_length=255, blank=True, default="", db_index=True)
    github_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    account_type = models.CharField(max_length=32, blank=True, default="")
    html_url = models.URLField(max_length=512, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "github_core__github_account"

    def get_name(self) -> str:
        return self.login or (str(self.github_id) if self.github_id else "")

    def __str__(self) -> str:
        return self.get_name()
