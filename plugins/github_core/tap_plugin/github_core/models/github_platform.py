"""GitHub Platform — the github.com (or GHES) host instance every account lives under."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class GithubPlatform(BaseModel):
    """A GitHub platform instance — github.com today, a GHES host tomorrow.

    The single top-of-tree node every collected account/repo/workflow hangs
    under. Synthesized by the collector (one per run), not fetched from an API:
    no GitHub endpoint enumerates "the platform." Natural key is the host
    (``github.com``), so a self-hosted GHES tenant becomes a second instance
    rather than a special case.

    Spec: plugins/github_core/specs/spec-github-core-v0.md (req-github-core-models)
    """

    ENTITY_TYPE: ClassVar[str] = "github_platform"
    ENTITY_NAME: ClassVar[str] = "GitHub Platform"
    ENTITY_DESCRIPTION: ClassVar[str] = "A GitHub platform instance (github.com or a GHES host)."
    ENTITY_ICON: ClassVar[str] = "github-platform"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"github.platform": "github.com"}
    # GitHub family palette: a cool blue/neutral scheme that reads as "external
    # source system," distinct from aws_core's warm beige in-boundary nodes.
    # Graduated by nesting depth — platform (outer) is a near-white frame with a
    # GitHub-ink border, account is light blue, repo is deeper blue.
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "round-rectangle",
            "colors": {"fill": "#F6F8FA", "border": "#1F2328", "label": "#1F2328"},
            "label": {"valign": "top", "halign": "center", "position": "outside"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "host": {"type": "string", "minLength": 1},
        "html_url": {"type": "string"},
        "configuration": {"type": "object"},
        "tags": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "host": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "html_url": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
        "tags": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["host"]

    host = models.CharField(max_length=255, blank=True, default="", db_index=True)
    html_url = models.URLField(max_length=512, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "github_platform"

    def get_name(self) -> str:
        return self.host

    def __str__(self) -> str:
        return self.get_name()
