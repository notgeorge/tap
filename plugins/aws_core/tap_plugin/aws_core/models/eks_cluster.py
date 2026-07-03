"""EKS Cluster — an Amazon Elastic Kubernetes Service cluster."""

from typing import Any, ClassVar

from django.db import models

from tap_grid.models import BaseModel


class EksCluster(BaseModel):
    """An Amazon EKS Kubernetes cluster."""

    ENTITY_TYPE: ClassVar[str] = "aws_core__aws_eks_cluster"
    ENTITY_NAME: ClassVar[str] = "EKS Cluster"
    ENTITY_DESCRIPTION: ClassVar[str] = "An Amazon Elastic Kubernetes Service cluster."
    ENTITY_ICON: ClassVar[str] = "aws-eks"
    DEFAULT_DIMENSIONS: ClassVar[dict[str, str]] = {"tap.cloud": "aws"}

    DEFAULT_DISPLAY: ClassVar[dict[str, Any]] = {
        "tap_viz": {
            "shape": "rectangle",
            "colors": {"fill": "#F9D7B7", "border": "#ED7100", "label": "#421F00"},
        }
    }

    FIELD_CRUD_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"type": "string", "minLength": 1},
        "cluster_arn": {"type": "string"},
        "status": {"type": "string"},
        "kubernetes_version": {"type": "string"},
        "endpoint": {"type": "string"},
        "configuration": {"type": "object"},
    }

    FIELD_VALIDATION_SCHEMA: ClassVar[dict[str, Any]] = {
        "name": {"validation": "jsonschema", "schema": {"type": "string", "minLength": 1}},
        "cluster_arn": {"validation": "jsonschema", "schema": {"type": "string"}},
        "status": {"validation": "jsonschema", "schema": {"type": "string"}},
        "kubernetes_version": {"validation": "jsonschema", "schema": {"type": "string"}},
        "endpoint": {"validation": "jsonschema", "schema": {"type": "string"}},
        "configuration": {"validation": "jsonschema", "schema": {"type": "object"}},
    }
    CREATE_REQUIRED: ClassVar[list[str]] = ["name"]

    name = models.CharField(max_length=255, blank=True, default="")
    cluster_arn = models.CharField(max_length=512, blank=True, default="")
    status = models.CharField(max_length=64, blank=True, default="")
    kubernetes_version = models.CharField(max_length=32, blank=True, default="")
    endpoint = models.CharField(max_length=512, blank=True, default="")
    configuration = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        db_table = "aws_core__aws_eks_cluster"

    def get_name(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name
