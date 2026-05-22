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

    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "bucket_arn": {"type": "string"},
        "versioning": {"type": "string"},
        "encryption": {"type": "string"},
        "public_access_blocked": {"type": "boolean"},
        "size_bytes": {"type": ["integer", "null"]},
        "object_count": {"type": ["integer", "null"]},
        "size_observed_at": {"type": "string"},
        "configuration": {"type": "object"},
        "tags": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "bucket_arn": {"validation": "jsonschema", "schema": {"type": "string"}},
        "versioning": {"validation": "jsonschema", "schema": {"type": "string"}},
        "encryption": {"validation": "jsonschema", "schema": {"type": "string"}},
        "public_access_blocked": {"validation": "jsonschema", "schema": {"type": "boolean"}},
        "size_bytes": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "object_count": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "size_observed_at": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
        "tags": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    bucket_arn = models.CharField(max_length=512, blank=True, default="")
    versioning = models.CharField(max_length=32, blank=True, default="")
    encryption = models.CharField(max_length=64, blank=True, default="")
    public_access_blocked = models.BooleanField(default=True)
    # Aggregate object stats from CloudWatch daily storage metrics — null when
    # CloudWatch has no datapoint yet (unknown, never a misleading 0).
    # `size_observed_at` is the datapoint's own timestamp (ISO 8601); the
    # consumer derives staleness as `now - size_observed_at`. See
    # req-aws-collector-s3-bucket-size.
    size_bytes = models.BigIntegerField(blank=True, null=True)
    object_count = models.BigIntegerField(blank=True, null=True)
    size_observed_at = models.CharField(max_length=64, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_s3_bucket"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
