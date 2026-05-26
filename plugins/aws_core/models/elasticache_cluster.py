"""ElastiCache Cluster — an Amazon ElastiCache cluster (Redis/Memcached)."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class ElasticacheCluster(BaseModel):
    """An Amazon ElastiCache cluster."""

    ENTITY_TYPE: ClassVar[str] = "aws_elasticache_cluster"
    ENTITY_NAME: ClassVar[str] = "ElastiCache Cluster"
    ENTITY_DESCRIPTION: ClassVar[str] = "An Amazon ElastiCache cluster (Redis or Memcached)."
    ENTITY_ICON: ClassVar[str] = "aws-elasticache"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}
    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "colors": {"fill": "#C3CFDC", "border": "#2B5783", "label": "#0C1824"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "cluster_id": {"type": "string"},
        "engine": {"type": "string"},
        "engine_version": {"type": "string"},
        "node_type": {"type": "string"},
        "num_nodes": {"type": ["integer", "null"]},
        "status": {"type": "string"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "cluster_id": {"validation": "jsonschema", "schema": {"type": "string"}},
        "engine": {"validation": "jsonschema", "schema": {"type": "string"}},
        "engine_version": {"validation": "jsonschema", "schema": {"type": "string"}},
        "node_type": {"validation": "jsonschema", "schema": {"type": "string"}},
        "num_nodes": {"validation": "jsonschema", "schema": {"type": ["integer", "null"]}},
        "status": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    cluster_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    engine = models.CharField(max_length=32, blank=True, default="")
    engine_version = models.CharField(max_length=64, blank=True, default="")
    node_type = models.CharField(max_length=64, blank=True, default="")
    num_nodes = models.IntegerField(blank=True, null=True)
    status = models.CharField(max_length=64, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_elasticache_cluster"

    def get_name(self) -> str:
        return self.name or self.cluster_id

    def __str__(self) -> str:
        return self.get_name()
