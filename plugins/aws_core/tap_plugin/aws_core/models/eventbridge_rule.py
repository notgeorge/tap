"""EventBridge Rule — an Amazon EventBridge (CloudWatch Events) rule."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class EventbridgeRule(BaseModel):
    """An Amazon EventBridge rule.

    Spec: plugins/aws_core/specs/spec-aws-core-v0.md (req-aws-core-models),
    plugins/aws_core/specs/spec-aws-core-collector-v0.md
    (req-aws-collector-model-deps).

    A rule's invocation ``RoleArn`` drives the EventBridge rule → IAM role
    ``ASSUMES_ROLE`` edge; the resolution is a manifest edge rule, not a
    field on this model.
    """

    ENTITY_TYPE: ClassVar[str] = "aws_core__aws_eventbridge_rule"
    ENTITY_NAME: ClassVar[str] = "EventBridge Rule"
    ENTITY_DESCRIPTION: ClassVar[str] = "An Amazon EventBridge rule."
    ENTITY_ICON: ClassVar[str] = "aws-eventbridge"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "colors": {"fill": "#EFC1F2", "border": "#C925D1", "label": "#380A3A"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "rule_arn": {"type": "string"},
        "state": {"type": "string"},
        "schedule_expression": {"type": "string"},
        "event_bus_name": {"type": "string"},
        "configuration": {"type": "object"},
        "tags": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "rule_arn": {"validation": "jsonschema", "schema": {"type": "string"}},
        "state": {"validation": "jsonschema", "schema": {"type": "string"}},
        "schedule_expression": {"validation": "jsonschema", "schema": {"type": "string"}},
        "event_bus_name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
        "tags": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    rule_arn = models.CharField(max_length=512, blank=True, default="")
    state = models.CharField(max_length=32, blank=True, default="")
    schedule_expression = models.CharField(max_length=255, blank=True, default="")
    event_bus_name = models.CharField(max_length=255, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_core__aws_eventbridge_rule"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
