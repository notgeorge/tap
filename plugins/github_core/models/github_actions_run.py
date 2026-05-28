"""GitHub Actions Run — one workflow run (latest-attempt snapshot)."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class GithubActionsRun(BaseModel):
    """A GitHub Actions workflow run.

    v0 models a single observation per run_id (latest attempt). Multi-attempt
    tracking is deferred to req-github-core-backlog-run-attempts.

    Spec: plugins/github_core/specs/spec-github-core-v0.md (req-github-core-models)
    """

    ENTITY_TYPE: ClassVar[str] = "github_actions_run"
    ENTITY_NAME: ClassVar[str] = "GitHub Actions Run"
    ENTITY_DESCRIPTION: ClassVar[str] = "An execution of a GitHub Actions workflow."
    ENTITY_ICON: ClassVar[str] = "github-actions-run"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {
        "github.platform": "github.com",
        "github.surface": "actions",
        "github.observation": "execution",
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "full_name": {"type": "string", "minLength": 1},
        "run_id": {"type": ["integer", "null"]},
        "run_number": {"type": ["integer", "null"]},
        "event": {"type": "string"},
        "status": {"type": "string"},
        "conclusion": {"type": "string"},
        "head_sha": {"type": "string"},
        "head_branch": {"type": "string"},
        "run_started_at": {"type": ["string", "null"]},
        "completed_at": {"type": ["string", "null"]},
        "html_url": {"type": "string"},
        "configuration": {"type": "object"},
        "tags": {"type": "object"},
    }

    # FIELD_VALIDATION_SCHEMA runs on save with the post-parse Python value.
    # Datetime fields are typed Django DateTimeFields — their own validation
    # is the right layer. Including a JSON-Schema entry for them would assert
    # against a `datetime` object that the API-input shape "string | null"
    # describes only the inbound JSON shape, not the at-rest Python value.
    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "full_name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "run_id": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "run_number": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "event": {"validation": "jsonschema", "schema": {"type": "string"}},
        "status": {"validation": "jsonschema", "schema": {"type": "string"}},
        "conclusion": {"validation": "jsonschema", "schema": {"type": "string"}},
        "head_sha": {"validation": "jsonschema", "schema": {"type": "string"}},
        "head_branch": {"validation": "jsonschema", "schema": {"type": "string"}},
        "html_url": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
        "tags": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["full_name", "run_id"]

    full_name = models.CharField(max_length=255, blank=True, default="", db_index=True)
    run_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    run_number = models.IntegerField(null=True, blank=True)
    event = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=32, blank=True, default="")
    conclusion = models.CharField(max_length=32, blank=True, default="")
    head_sha = models.CharField(max_length=64, blank=True, default="", db_index=True)
    head_branch = models.CharField(max_length=255, blank=True, default="")
    run_started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    html_url = models.URLField(max_length=512, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "github_actions_run"

    def get_name(self) -> str:
        if self.run_number:
            return f"Run #{self.run_number}"
        if self.run_id:
            return f"Run {self.run_id}"
        return self.full_name

    def __str__(self) -> str:
        return self.get_name()
