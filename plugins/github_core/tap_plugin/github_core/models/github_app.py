"""GitHub App — a GitHub App or first-party platform app (e.g. Dependabot)."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class GithubApp(BaseModel):
    """A GitHub App or first-party platform app enabled on a repository.

    Generic across GitHub's app surface: GitHub's own managed apps (Dependabot,
    code scanning) and third-party / OIDC token-issuing apps all model as a
    ``github_app``, linked to the repositories they are enabled on via the
    ``ENABLED_ON`` edge. Identity is the app ``slug`` (e.g. ``dependabot``), so
    one app node is shared across every repo that enables it.

    Spec: plugins/github_core/specs/spec-github-core-v0.md (req-github-core-app)
    """

    ENTITY_TYPE: ClassVar[str] = "github_core__github_app"
    ENTITY_NAME: ClassVar[str] = "GitHub App"
    ENTITY_DESCRIPTION: ClassVar[str] = (
        "A GitHub App or first-party platform app (e.g. Dependabot) enabled on a repository."
    )
    ENTITY_ICON: ClassVar[str] = "github-app"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {
        "github.platform": "github.com",
        "github.surface": "apps",
    }
    # Same family scheme as the other github_core nodes — white fill so it reads
    # as a card; GitHub-purple border to distinguish apps from the blue Actions
    # surface.
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "round-rectangle",
            "colors": {"fill": "#FFFFFF", "border": "#8250DF", "label": "#1F2328"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "slug": {"type": "string", "minLength": 1},
        "name": {"type": "string"},
        "app_id": {"type": ["integer", "null"]},
        "html_url": {"type": "string"},
        "description": {"type": "string"},
        "configuration": {"type": "object"},
        "tags": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "slug": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "app_id": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "html_url": {"validation": "jsonschema", "schema": {"type": "string"}},
        "description": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
        "tags": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["slug"]

    slug = models.CharField(max_length=255, blank=True, default="", db_index=True)
    name = models.CharField(max_length=255, blank=True, default="")
    app_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    html_url = models.URLField(max_length=512, blank=True, default="")
    description = models.TextField(blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "github_core__github_app"

    def get_name(self) -> str:
        return self.name or self.slug

    def __str__(self) -> str:
        return self.get_name()
