"""GitHub Actions Job — one job within a workflow run."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class GithubActionsJob(BaseModel):
    """A job within a GitHub Actions workflow run.

    Step-level detail lives in the `configuration` JSONField (Steps Not Nodes
    in v0). The `configuration` carries `runs_on`, `needs`, `uses`, the full
    parsed step list, and observed runner fields.

    Spec: plugins/github_core/specs/spec-github-core-v0.md (req-github-core-models)
    """

    ENTITY_TYPE: ClassVar[str] = "github_core__github_actions_job"
    ENTITY_NAME: ClassVar[str] = "GitHub Actions Job"
    ENTITY_DESCRIPTION: ClassVar[str] = "One job within a GitHub Actions workflow run."
    ENTITY_ICON: ClassVar[str] = "github-actions-job"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {
        "github.platform": "github.com",
        "github.surface": "actions",
        "github.observation": "execution",
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "full_name": {"type": "string", "minLength": 1},
        "job_id": {"type": ["integer", "null"]},
        "name": {"type": "string"},
        "status": {"type": "string"},
        "conclusion": {"type": "string"},
        "started_at": {"type": ["string", "null"]},
        "completed_at": {"type": ["string", "null"]},
        "html_url": {"type": "string"},
        "configuration": {"type": "object"},
        "tags": {"type": "object"},
    }

    # See github_actions_run.py for why datetime fields are NOT in the
    # FIELD_VALIDATION_SCHEMA (Django's typed DateTimeField handles validation;
    # JSON-schema "string | null" describes inbound JSON, not at-rest Python).
    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "full_name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "job_id": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "status": {"validation": "jsonschema", "schema": {"type": "string"}},
        "conclusion": {"validation": "jsonschema", "schema": {"type": "string"}},
        "html_url": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
        "tags": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["full_name", "job_id"]

    full_name = models.CharField(max_length=255, blank=True, default="", db_index=True)
    job_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    name = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=32, blank=True, default="")
    conclusion = models.CharField(max_length=32, blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    html_url = models.URLField(max_length=512, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "github_core__github_actions_job"

    def get_name(self) -> str:
        return self.name or (f"Job {self.job_id}" if self.job_id else self.full_name)

    def __str__(self) -> str:
        return self.get_name()
