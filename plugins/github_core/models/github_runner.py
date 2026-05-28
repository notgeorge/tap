"""GitHub Runner — durable registered self-hosted runner."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class GithubRunner(BaseModel):
    """A durable registered self-hosted GitHub Actions runner.

    v0 creates runner nodes only for durable registered runners visible via
    the runner API (req-github-core-runner-1). GitHub-hosted ephemeral
    runners are NOT modeled as nodes; observed runner fields live in
    `github_actions_job.configuration` instead.

    Spec: plugins/github_core/specs/spec-github-core-v0.md (req-github-core-models, req-github-core-runner)
    """

    ENTITY_TYPE: ClassVar[str] = "github_runner"
    ENTITY_NAME: ClassVar[str] = "GitHub Runner"
    ENTITY_DESCRIPTION: ClassVar[str] = "A durable registered self-hosted GitHub Actions runner."
    ENTITY_ICON: ClassVar[str] = "github-runner"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {
        "github.platform": "github.com",
        "github.surface": "actions",
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "full_name": {"type": "string", "minLength": 1},
        "runner_id": {"type": ["integer", "null"]},
        "name": {"type": "string"},
        "os": {"type": "string"},
        "status": {"type": "string"},
        "busy": {"type": "boolean"},
        "labels": {"type": "array"},
        "configuration": {"type": "object"},
        "tags": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "full_name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "runner_id": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "os": {"validation": "jsonschema", "schema": {"type": "string"}},
        "status": {"validation": "jsonschema", "schema": {"type": "string"}},
        "busy": {"validation": "jsonschema", "schema": {"type": "boolean"}},
        "labels": {"validation": "jsonschema", "schema": {"type": "array"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
        "tags": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["full_name", "runner_id"]

    full_name = models.CharField(max_length=255, blank=True, default="", db_index=True)
    runner_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    name = models.CharField(max_length=255, blank=True, default="")
    os = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=32, blank=True, default="")
    busy = models.BooleanField(default=False)
    labels = models.JSONField(default=list, blank=True)
    configuration = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "github_runner"

    def get_name(self) -> str:
        return self.name or (f"Runner {self.runner_id}" if self.runner_id else self.full_name)

    def __str__(self) -> str:
        return self.get_name()
