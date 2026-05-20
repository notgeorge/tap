"""Unit tests for tag normalization + the manifest tags block (no DB).

Covers req-aws-collector-tags: the single canonical normalizer
(list_kv|map → {str:str}, graceful), the rgta join-ARN resolution, and
the manifest schema accepting/rejecting the tags block.
"""

from __future__ import annotations

import json

import jsonschema
import pytest

from plugins.aws_core.collectors.boto3_collector import manifest as manifest_mod
from plugins.aws_core.collectors.boto3_collector.manifest import manifest_entries
from plugins.aws_core.collectors.boto3_collector.tags import (
    TagShapeError,
    normalize_tags,
    rgta_join_arn,
    tags_block,
)


class TestNormalizeTags:
    def test_list_kv_basic(self):
        raw = [{"Key": "Owner", "Value": "sam"}, {"Key": "Env", "Value": "prod"}]
        assert normalize_tags(raw, "list_kv") == {"Owner": "sam", "Env": "prod"}

    def test_list_kv_missing_value_and_bad_elements(self):
        raw = [{"Key": "A"}, {"Value": "orphan"}, "junk", {"Key": "B", "Value": 1}]
        assert normalize_tags(raw, "list_kv") == {"A": "", "B": "1"}

    def test_list_kv_non_list_is_empty(self):
        assert normalize_tags(None, "list_kv") == {}
        assert normalize_tags({"Key": "x"}, "list_kv") == {}

    def test_map_basic_and_coerces(self):
        assert normalize_tags({"a": "1", "b": 2}, "map") == {"a": "1", "b": "2"}

    def test_map_non_dict_is_empty(self):
        assert normalize_tags([], "map") == {}
        assert normalize_tags(None, "map") == {}

    def test_unknown_shape_raises(self):
        with pytest.raises(TagShapeError, match="list_kv | map"):
            normalize_tags([], "list_kv_lower")


class TestRgtaJoinArn:
    def test_arn_from_override(self):
        entry = {"natural_key": "arn", "tags": {"source": "rgta", "arn_from": "logGroupArn"}}
        item = {"arn": "arn:...:log-group:x:*", "logGroupArn": "arn:...:log-group:x"}
        assert rgta_join_arn(entry, item) == "arn:...:log-group:x"

    def test_defaults_to_natural_key(self):
        entry = {"natural_key": "FunctionArn", "tags": {"source": "rgta", "resource_type_filter": "lambda:function"}}
        assert rgta_join_arn(entry, {"FunctionArn": "arn:fn"}) == "arn:fn"

    def test_missing_is_graceful_none(self):
        entry = {"natural_key": "BucketArn", "tags": {"source": "rgta"}}
        assert rgta_join_arn(entry, {}) is None


class TestManifestTagsBlock:
    def test_declared_sources_match_design(self):
        by_type = {e["entity_type"]: e for e in manifest_entries()}
        rgta = {
            "aws_lambda",
            "aws_eventbridge_rule",
            "aws_cloudwatch_log_group",
            "aws_acm_certificate",
            "aws_s3_bucket",
            "aws_dynamodb_table",
        }
        service = {
            "aws_iam_role",
            "aws_cloudfront_distribution",
            "aws_route53_zone",
            "aws_iam_oidc_provider",
        }
        for t in rgta:
            assert tags_block(by_type[t])["source"] == "rgta"
        for t in service:
            blk = tags_block(by_type[t])
            assert blk["source"] == "service"
            assert blk["shape"] in ("list_kv", "map")
            assert {"op", "params", "path"} <= blk.keys()
            # Each params entry is {literal:…} or {from:<path>}; at least one
            # entry must exist (multi-param tag APIs land first-class here).
            assert isinstance(blk["params"], dict) and blk["params"]
            for spec in blk["params"].values():
                assert ("literal" in spec) ^ ("from" in spec)

    def test_schema_rejects_bad_tags_block(self):
        schema = json.loads(manifest_mod.SCHEMA_PATH.read_text())
        # rgta without resource_type_filter; and an unknown source.
        for bad_tags in (
            {"source": "rgta"},
            {"source": "service", "op": "X"},
            {"source": "elsewhere"},
        ):
            bad = {
                "manifest_version": "0",
                "entries": [
                    {
                        "entity_type": "x",
                        "service": "s",
                        "scope": "global",
                        "source": {"aws_op": "L"},
                        "why": "w",
                        "items_path": "[]",
                        "natural_key": "Arn",
                        "fields": {"name": "N"},
                        "tags": bad_tags,
                    }
                ],
            }
            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate(bad, schema)
