"""EBS Volume — an Amazon Elastic Block Store volume."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class EbsVolume(BaseModel):
    """An Amazon EBS block storage volume."""

    ENTITY_TYPE: ClassVar[str] = "aws_ebs_volume"
    ENTITY_NAME: ClassVar[str] = "EBS Volume"
    ENTITY_DESCRIPTION: ClassVar[str] = "An Amazon EBS block storage volume."
    ENTITY_ICON: ClassVar[str] = "aws-ebs"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string"},
        "volume_id": {"type": "string"},
        "volume_type": {"type": "string"},
        "size_gb": {"type": ["integer", "null"]},
        "state": {"type": "string"},
        "encrypted": {"type": "boolean"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string"}},
        "volume_id": {"validation": "jsonschema", "schema": {"type": "string"}},
        "volume_type": {"validation": "jsonschema", "schema": {"type": "string"}},
        "size_gb": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "state": {"validation": "jsonschema", "schema": {"type": "string"}},
        "encrypted": {"validation": "jsonschema", "schema": {"type": "boolean"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["volume_id"]

    name = models.CharField(max_length=255, blank=True, default="")
    volume_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    volume_type = models.CharField(max_length=32, blank=True, default="")
    size_gb = models.IntegerField(blank=True, null=True)
    state = models.CharField(max_length=32, blank=True, default="")
    encrypted = models.BooleanField(default=False)
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_ebs_volume"

    def get_name(self) -> str:
        return self.name or self.volume_id

    def __str__(self) -> str:
        return self.get_name()
