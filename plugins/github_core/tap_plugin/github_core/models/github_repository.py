"""GitHub Repository — a repository under a GitHub account."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class GithubRepository(BaseModel):
    """A GitHub repository.

    Spec: plugins/github_core/specs/spec-github-core-v0.md (req-github-core-models)
    """

    ENTITY_TYPE: ClassVar[str] = "github_core__github_repository"
    ENTITY_NAME: ClassVar[str] = "GitHub Repository"
    ENTITY_DESCRIPTION: ClassVar[str] = "A repository hosted on GitHub."
    ENTITY_ICON: ClassVar[str] = "github-repository"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"github.platform": "github.com"}
    # Inner level of the GitHub nesting palette — deeper accent blue; the white
    # workflow leaf cards sit on this bed. See github_platform for the scheme.
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "round-rectangle",
            "colors": {"fill": "#B6E3FF", "border": "#0969DA", "label": "#0A3069"},
            "label": {"valign": "top", "halign": "center", "position": "outside"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "full_name": {"type": "string", "minLength": 1},
        "owner_login": {"type": "string"},
        "name": {"type": "string"},
        "github_id": {"type": ["integer", "null"]},
        "default_branch": {"type": "string"},
        "visibility": {"type": "string"},
        "html_url": {"type": "string"},
        "configuration": {"type": "object"},
        "tags": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "full_name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "owner_login": {"validation": "jsonschema", "schema": {"type": "string"}},
        "name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "github_id": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "default_branch": {"validation": "jsonschema", "schema": {"type": "string"}},
        "visibility": {"validation": "jsonschema", "schema": {"type": "string"}},
        "html_url": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
        "tags": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["full_name"]

    full_name = models.CharField(max_length=255, blank=True, default="", db_index=True)
    owner_login = models.CharField(max_length=255, blank=True, default="", db_index=True)
    name = models.CharField(max_length=255, blank=True, default="")
    github_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    default_branch = models.CharField(max_length=255, blank=True, default="")
    visibility = models.CharField(max_length=32, blank=True, default="")
    html_url = models.URLField(max_length=512, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "github_core__github_repository"

    def get_name(self) -> str:
        return self.full_name or self.name

    def __str__(self) -> str:
        return self.get_name()
