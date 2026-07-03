"""GitHub Workflow — a workflow definition under a repository's Actions surface."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class GithubWorkflow(BaseModel):
    """A GitHub Actions workflow definition.

    The `configuration` JSONField carries parsed workflow YAML — triggers,
    permissions, the raw YAML body (`configuration.raw_yaml`), and other
    extracted fields per req-github-core-workflow-parse.

    Spec: plugins/github_core/specs/spec-github-core-v0.md (req-github-core-models)
    """

    ENTITY_TYPE: ClassVar[str] = "github_core__github_workflow"
    ENTITY_NAME: ClassVar[str] = "GitHub Workflow"
    ENTITY_DESCRIPTION: ClassVar[str] = "A GitHub Actions workflow definition."
    ENTITY_ICON: ClassVar[str] = "github-workflow"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {
        "github.platform": "github.com",
        "github.surface": "actions",
    }
    # Leaf cards inside the repo box — white fill, accent-blue border so they
    # pop on the deeper-blue repo bed. See github_platform for the family scheme.
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "round-rectangle",
            "colors": {"fill": "#FFFFFF", "border": "#0969DA", "label": "#1F2328"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "full_name": {"type": "string", "minLength": 1},
        "workflow_id": {"type": ["integer", "null"]},
        "path": {"type": "string"},
        "name": {"type": "string"},
        "state": {"type": "string"},
        "html_url": {"type": "string"},
        "configuration": {"type": "object"},
        "tags": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "full_name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "workflow_id": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "path": {"validation": "jsonschema", "schema": {"type": "string"}},
        "name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "state": {"validation": "jsonschema", "schema": {"type": "string"}},
        "html_url": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
        "tags": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["full_name"]

    full_name = models.CharField(max_length=255, blank=True, default="", db_index=True)
    workflow_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    path = models.CharField(max_length=512, blank=True, default="", db_index=True)
    name = models.CharField(max_length=255, blank=True, default="")
    state = models.CharField(max_length=32, blank=True, default="")
    html_url = models.URLField(max_length=512, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "github_core__github_workflow"

    def get_name(self) -> str:
        return self.name or self.path or self.full_name

    def __str__(self) -> str:
        return self.get_name()
