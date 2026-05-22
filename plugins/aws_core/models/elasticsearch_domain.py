"""Elasticsearch Domain — an Amazon OpenSearch / Elasticsearch Service domain."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class ElasticsearchDomain(BaseModel):
    """An Amazon OpenSearch (Elasticsearch) Service domain."""

    ENTITY_TYPE: ClassVar[str] = "aws_elasticsearch_domain"
    ENTITY_NAME: ClassVar[str] = "Elasticsearch Domain"
    ENTITY_DESCRIPTION: ClassVar[str] = "An Amazon OpenSearch / Elasticsearch Service domain."
    ENTITY_ICON: ClassVar[str] = "aws-elasticsearch"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "domain_arn": {"type": "string"},
        "engine_version": {"type": "string"},
        "node_type": {"type": "string"},
        "instance_count": {"type": ["integer", "null"]},
        "encrypted": {"type": "boolean"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "domain_arn": {"validation": "jsonschema", "schema": {"type": "string"}},
        "engine_version": {"validation": "jsonschema", "schema": {"type": "string"}},
        "node_type": {"validation": "jsonschema", "schema": {"type": "string"}},
        "instance_count": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "encrypted": {"validation": "jsonschema", "schema": {"type": "boolean"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    domain_arn = models.CharField(max_length=512, blank=True, default="")
    engine_version = models.CharField(max_length=64, blank=True, default="")
    node_type = models.CharField(max_length=64, blank=True, default="")
    instance_count = models.IntegerField(blank=True, null=True)
    encrypted = models.BooleanField(default=False)
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_elasticsearch_domain"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
