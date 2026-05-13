"""Bedrock Model — an Amazon Bedrock foundation model."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class BedrockModel(BaseModel):
    """An Amazon Bedrock foundation model."""

    ENTITY_TYPE: ClassVar[str] = "aws_bedrock_model"
    ENTITY_NAME: ClassVar[str] = "Bedrock Model"
    ENTITY_DESCRIPTION: ClassVar[str] = "An Amazon Bedrock foundation model."
    ENTITY_ICON: ClassVar[str] = "aws-bedrock"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "model_id": {"type": "string"},
        "provider": {"type": "string"},
        "input_modalities": {"type": "array", "items": {"type": "string"}},
        "output_modalities": {"type": "array", "items": {"type": "string"}},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "model_id": {"validation": "jsonschema", "schema": {"type": "string"}},
        "provider": {"validation": "jsonschema", "schema": {"type": "string"}},
        "input_modalities": {"validation": "jsonschema", "schema": {"type": "array", "items": {"type": "string"}}},
        "output_modalities": {"validation": "jsonschema", "schema": {"type": "array", "items": {"type": "string"}}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name", "model_id"]

    name = models.CharField(max_length=255, blank=True, default="")
    model_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    provider = models.CharField(max_length=128, blank=True, default="")
    input_modalities = models.JSONField(default=list, blank=True)
    output_modalities = models.JSONField(default=list, blank=True)
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_bedrock_model"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
