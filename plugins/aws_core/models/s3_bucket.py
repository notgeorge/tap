"""S3 Bucket — an Amazon Simple Storage Service bucket."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class S3Bucket(BaseModel):
    """An Amazon S3 storage bucket."""

    ENTITY_TYPE: ClassVar[str] = "aws_s3_bucket"
    ENTITY_NAME: ClassVar[str] = "S3 Bucket"
    ENTITY_DESCRIPTION: ClassVar[str] = "An Amazon S3 storage bucket."
    ENTITY_ICON: ClassVar[str] = "aws-s3"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "bucket_arn": {"type": "string"},
        "versioning": {"type": "string"},
        "encryption": {"type": "string"},
        "public_access_blocked": {"type": "boolean"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "bucket_arn": {"validation": "jsonschema", "schema": {"type": "string"}},
        "versioning": {"validation": "jsonschema", "schema": {"type": "string"}},
        "encryption": {"validation": "jsonschema", "schema": {"type": "string"}},
        "public_access_blocked": {"validation": "jsonschema", "schema": {"type": "boolean"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    bucket_arn = models.CharField(max_length=512, blank=True, default="")
    versioning = models.CharField(max_length=32, blank=True, default="")
    encryption = models.CharField(max_length=64, blank=True, default="")
    public_access_blocked = models.BooleanField(default=True)
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_s3_bucket"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
