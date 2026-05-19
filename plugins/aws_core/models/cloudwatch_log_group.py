"""CloudWatch Log Group — an Amazon CloudWatch Logs log group."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class CloudwatchLogGroup(BaseModel):
    """An Amazon CloudWatch Logs log group.

    Spec: plugins/aws_core/specs/spec-aws-core-v0.md (req-aws-core-models),
    plugins/aws_core/specs/spec-aws-core-collector-v0.md
    (req-aws-collector-model-deps).

    Note: AWS returns the log group ``creationTime`` as epoch milliseconds
    (a botocore ``long``, not a ``timestamp``); the collector normalizes it
    per the temporal rule in spec-aws-core-collector-v0
    (req-aws-collector-field-projection). The raw value is retained in
    ``configuration`` verbatim.
    """

    ENTITY_TYPE: ClassVar[str] = "aws_cloudwatch_log_group"
    ENTITY_NAME: ClassVar[str] = "CloudWatch Log Group"
    ENTITY_DESCRIPTION: ClassVar[str] = "An Amazon CloudWatch Logs log group."
    ENTITY_ICON: ClassVar[str] = "aws-cloudwatch"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "colors": {"fill": "#F4B6D2", "border": "#E7157B", "label": "#5A0A30"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "log_group_arn": {"type": "string"},
        "retention_in_days": {"type": ["integer", "null"]},
        "configuration": {"type": "object"},
        "tags": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "log_group_arn": {"validation": "jsonschema", "schema": {"type": "string"}},
        "retention_in_days": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
        "tags": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=512, blank=True, default="")
    log_group_arn = models.CharField(max_length=512, blank=True, default="")
    retention_in_days = models.IntegerField(blank=True, null=True)
    configuration = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_cloudwatch_log_group"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
