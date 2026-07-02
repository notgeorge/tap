"""Edge-emission unit tests for the boto3 collector (boto3-free, no DB).

Covers req-aws-collector-edges: declarative rules, scalar + fan-out,
identity-resolved endpoints, the unmodeled-target single chokepoint, and
the registered-only transform hook.
"""

from __future__ import annotations

import pytest

from tap_plugin.aws_core.collectors.boto3_collector.edges import (
    EdgeError,
    TransformRegistry,
    emit_edges,
)
from tap_plugin.aws_core.collectors.boto3_collector.identity import (
    edge_entity_id,
    node_entity_id,
)
from tap_plugin.aws_core.collectors.boto3_collector.projection import ProjectedNode

MODELED = {"aws_lambda", "aws_iam_role", "aws_cloudwatch_log_group", "aws_s3_bucket"}
DIMS = {"cloud": "aws", "region": "us-east-1"}


def _node(raw_item):
    return ProjectedNode(
        entity_type="aws_lambda",
        entity_id=node_entity_id("aws_lambda", "arn:fn"),
        natural_key="arn:fn",
        name="fn",
        fields={"name": "fn"},
        configuration={"_source": {"op": "ListFunctions", "why": "x"}},
        raw_item=raw_item,
    )


LAMBDA_EDGE_ENTRY = {
    "edges": [
        {
            "value_path": "Role",
            "target_type": "aws_iam_role",
            "key_kind": "arn",
            "edge_type": "ASSUMES_ROLE",
            "direction": "outbound",
        },
        {
            "value_path": "LoggingConfig.LogGroup",
            "target_type": "aws_cloudwatch_log_group",
            "key_kind": "name",
            "edge_type": "WRITES_LOGS",
            "direction": "outbound",
        },
    ]
}


class TestEmitEdges:
    def test_scalar_outbound_edges_identity_resolved(self):
        node = _node({"Role": "arn:role", "LoggingConfig": {"LogGroup": "/aws/lambda/fn"}})
        result = emit_edges(
            node, LAMBDA_EDGE_ENTRY, modeled_types=MODELED, transforms=TransformRegistry(), dimensions=DIMS
        )
        assert result.warnings == []
        assert len(result.envelopes) == 2

        assumes = next(e for e in result.envelopes if e["edge"]["edge_type"] == "ASSUMES_ROLE")
        assert assumes["edge"]["from_entity_id"] == str(node_entity_id("aws_lambda", "arn:fn"))
        assert assumes["edge"]["to_entity_id"] == str(node_entity_id("aws_iam_role", "arn:role"))
        assert assumes["entity"]["entity_type"] == "edge"
        assert assumes["entity"]["entity_id"] == str(edge_entity_id("ASSUMES_ROLE", "arn:fn", "arn:role"))
        assert assumes["entity"]["dimensions"] == DIMS
        assert assumes["edge"]["properties"] == {}

    def test_list_value_path_fans_out(self):
        entry = {
            "edges": [
                {
                    "value_path": "Buckets[]",
                    "target_type": "aws_s3_bucket",
                    "key_kind": "name",
                    "edge_type": "RETRIEVES_CONTENT_FROM",
                    "direction": "outbound",
                }
            ]
        }
        node = _node({"Buckets": ["b1", "b2", "b3"]})
        result = emit_edges(node, entry, modeled_types=MODELED, transforms=TransformRegistry(), dimensions=DIMS)
        assert len(result.envelopes) == 3
        assert {e["edge"]["to_entity_id"] for e in result.envelopes} == {
            str(node_entity_id("aws_s3_bucket", b)) for b in ("b1", "b2", "b3")
        }

    def test_inbound_direction_swaps_endpoints(self):
        entry = {
            "edges": [
                {
                    "value_path": "Owner",
                    "target_type": "aws_iam_role",
                    "key_kind": "arn",
                    "edge_type": "ASSUMES_ROLE",
                    "direction": "inbound",
                }
            ]
        }
        node = _node({"Owner": "arn:role"})
        env = emit_edges(node, entry, modeled_types=MODELED, transforms=TransformRegistry(), dimensions=DIMS).envelopes[
            0
        ]
        assert env["edge"]["from_entity_id"] == str(node_entity_id("aws_iam_role", "arn:role"))
        assert env["edge"]["to_entity_id"] == str(node_entity_id("aws_lambda", "arn:fn"))
        assert env["entity"]["entity_id"] == str(edge_entity_id("ASSUMES_ROLE", "arn:role", "arn:fn"))

    def test_unmodeled_target_dropped_with_warning(self):
        entry = {
            "edges": [
                {
                    "value_path": "Role",
                    "target_type": "aws_not_modeled_yet",
                    "key_kind": "arn",
                    "edge_type": "ASSUMES_ROLE",
                    "direction": "outbound",
                }
            ]
        }
        result = emit_edges(
            _node({"Role": "arn:role"}),
            entry,
            modeled_types=MODELED,
            transforms=TransformRegistry(),
            dimensions=DIMS,
        )
        assert result.envelopes == []
        assert len(result.warnings) == 1
        assert "aws_not_modeled_yet" in result.warnings[0]
        assert "v0 fence" in result.warnings[0]

    def test_transform_applied(self):
        reg = TransformRegistry()
        reg.register("strip_suffix", lambda v: v.split(".")[0])
        entry = {
            "edges": [
                {
                    "value_path": "Origin",
                    "target_type": "aws_s3_bucket",
                    "key_kind": "name",
                    "edge_type": "RETRIEVES_CONTENT_FROM",
                    "direction": "outbound",
                    "transform": "strip_suffix",
                }
            ]
        }
        env = emit_edges(
            _node({"Origin": "mybucket.s3.amazonaws.com"}),
            entry,
            modeled_types=MODELED,
            transforms=reg,
            dimensions=DIMS,
        ).envelopes[0]
        assert env["edge"]["to_entity_id"] == str(node_entity_id("aws_s3_bucket", "mybucket"))

    def test_list_value_path_with_transform_applies_per_element(self):
        # Regression (found live, RETRIEVES_CONTENT_FROM = 0 on the real
        # account): a list value_path (Origins.Items[]) WITH a transform must
        # apply the transform PER ELEMENT after fan-out — not to the whole
        # list. The old code transformed `raw` (a list) before expansion, so
        # the transform saw a list, returned None, and silently emitted zero
        # edges. Also pins the None-drop contract: a non-S3 origin -> None ->
        # that element is dropped, no bogus "None" edge, no warning.
        from tap_plugin.aws_core.collectors.boto3_collector.transforms import (
            s3_bucket_name_from_origin_domain,
        )

        reg = TransformRegistry()
        reg.register("s3_origin", s3_bucket_name_from_origin_domain)
        entry = {
            "edges": [
                {
                    "value_path": "Origins.Items[].DomainName",
                    "target_type": "aws_s3_bucket",
                    "key_kind": "arn",
                    "edge_type": "RETRIEVES_CONTENT_FROM",
                    "direction": "outbound",
                    "transform": "s3_origin",
                }
            ]
        }
        node = _node(
            {
                "Origins": {
                    "Items": [
                        {"DomainName": "samsite-prod-1.s3.us-east-2.amazonaws.com"},
                        {"DomainName": "api.example.com"},  # non-S3 -> None -> dropped
                    ]
                }
            }
        )
        result = emit_edges(node, entry, modeled_types=MODELED, transforms=reg, dimensions=DIMS)
        assert result.warnings == []
        assert len(result.envelopes) == 1  # only the S3 origin; None dropped
        assert result.envelopes[0]["edge"]["to_entity_id"] == str(
            node_entity_id("aws_s3_bucket", "arn:aws:s3:::samsite-prod-1")
        )

    def test_unregistered_transform_raises(self):
        entry = {
            "edges": [
                {
                    "value_path": "Origin",
                    "target_type": "aws_s3_bucket",
                    "key_kind": "name",
                    "edge_type": "RETRIEVES_CONTENT_FROM",
                    "direction": "outbound",
                    "transform": "missing",
                }
            ]
        }
        with pytest.raises(EdgeError, match="not registered"):
            emit_edges(
                _node({"Origin": "x"}),
                entry,
                modeled_types=MODELED,
                transforms=TransformRegistry(),
                dimensions=DIMS,
            )

    def test_missing_and_empty_values_are_graceful(self):
        node = _node({"LoggingConfig": {}})  # Role absent, LogGroup absent
        result = emit_edges(
            node, LAMBDA_EDGE_ENTRY, modeled_types=MODELED, transforms=TransformRegistry(), dimensions=DIMS
        )
        assert result.envelopes == []
        assert result.warnings == []  # absent value is normal, not a drop

    def test_no_edges_key_is_noop(self):
        result = emit_edges(_node({}), {}, modeled_types=MODELED, transforms=TransformRegistry(), dimensions=DIMS)
        assert result.envelopes == []
        assert result.warnings == []
