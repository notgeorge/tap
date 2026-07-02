"""Field-projection unit tests for the boto3 collector (boto3-free, no DB).

Covers req-aws-collector-field-projection: declared field mapping, graceful
missing, lossless configuration, name fallback, deterministic identity, and
the natural-key failure contract.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tap_plugin.aws_core.collectors.boto3_collector.identity import node_entity_id
from tap_plugin.aws_core.collectors.boto3_collector.projection import (
    ProjectionError,
    project_item,
    source_op_label,
)

# A representative manifest entry (the v0 Lambda entry's shape).
LAMBDA_ENTRY = {
    "entity_type": "aws_lambda",
    "service": "lambda",
    "source": {"aws_op": "ListFunctions"},
    "why": "Enumerate Lambda functions.",
    "natural_key": "FunctionArn",
    "fields": {
        "name": "FunctionName",
        "function_arn": "FunctionArn",
        "runtime": "Runtime",
        "handler": "Handler",
        "memory_size": "MemorySize",
        "timeout": "Timeout",
    },
}


def _lambda_item():
    return {
        "FunctionName": "sam-handler",
        "FunctionArn": "arn:aws:lambda:us-east-1:1:function:sam-handler",
        "Runtime": "python3.13",
        "Handler": "app.handler",
        "MemorySize": 256,
        "Timeout": 30,
        "LastModified": datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    }


class TestProjectItem:
    def test_declared_fields_mapped(self):
        node = project_item(LAMBDA_ENTRY, _lambda_item())
        assert node.entity_type == "aws_lambda"
        assert node.fields == {
            "name": "sam-handler",
            "function_arn": "arn:aws:lambda:us-east-1:1:function:sam-handler",
            "runtime": "python3.13",
            "handler": "app.handler",
            "memory_size": 256,
            "timeout": 30,
        }
        assert node.name == "sam-handler"
        assert node.natural_key == "arn:aws:lambda:us-east-1:1:function:sam-handler"

    def test_graceful_missing_field_is_none(self):
        item = _lambda_item()
        del item["Runtime"]
        node = project_item(LAMBDA_ENTRY, item)
        assert node.fields["runtime"] is None  # never raises

    def test_configuration_is_lossless_and_self_describing(self):
        node = project_item(LAMBDA_ENTRY, _lambda_item())
        # Full raw item retained verbatim ...
        assert node.configuration["FunctionName"] == "sam-handler"
        assert node.configuration["Handler"] == "app.handler"
        # ... datetime normalized to ISO 8601 UTC Z ...
        assert node.configuration["LastModified"] == "2026-01-02T03:04:05Z"
        # ... plus the engine-reserved _source.
        assert node.configuration["_source"] == {
            "op": "ListFunctions",
            "why": "Enumerate Lambda functions.",
        }

    def test_response_metadata_excluded_from_configuration(self):
        item = _lambda_item()
        item["ResponseMetadata"] = {"RequestId": "r"}
        node = project_item(LAMBDA_ENTRY, item)
        assert "ResponseMetadata" not in node.configuration

    def test_name_falls_back_to_natural_key(self):
        item = _lambda_item()
        del item["FunctionName"]
        node = project_item(LAMBDA_ENTRY, item)
        assert node.fields["name"] is None
        assert node.name == node.natural_key

    def test_identity_deterministic_and_keyed(self):
        a = project_item(LAMBDA_ENTRY, _lambda_item())
        b = project_item(LAMBDA_ENTRY, _lambda_item())
        assert a.entity_id == b.entity_id
        assert a.entity_id == node_entity_id("aws_lambda", a.natural_key)
        other = _lambda_item()
        other["FunctionArn"] = "arn:aws:lambda:us-east-1:1:function:other"
        assert project_item(LAMBDA_ENTRY, other).entity_id != a.entity_id

    def test_missing_natural_key_raises(self):
        item = _lambda_item()
        del item["FunctionArn"]
        with pytest.raises(ProjectionError, match="natural_key"):
            project_item(LAMBDA_ENTRY, item)


class TestSourceOpLabel:
    def test_aws_op_label(self):
        assert source_op_label({"source": {"aws_op": "ListFunctions"}}) == "ListFunctions"

    def test_custom_fn_label(self):
        assert source_op_label({"source": {"custom_fn": "route53_zones"}}) == "route53_zones"
