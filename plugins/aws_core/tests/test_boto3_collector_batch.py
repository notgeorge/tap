"""GRIFT batch-assembly unit tests for the boto3 collector (no DB).

Covers req-aws-collector-grift-batch: one batch per run, provenance
recorded, no deletion content, GRIFT document root shape.
"""

from __future__ import annotations

from datetime import UTC, datetime

from plugins.aws_core.collectors.boto3_collector.batch import (
    COLLECTION_FORMAT,
    assemble_batch,
    node_envelope,
)
from plugins.aws_core.collectors.boto3_collector.identity import node_entity_id
from plugins.aws_core.collectors.boto3_collector.projection import ProjectedNode

FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
FIXED_BATCH_ID = "00000000-0000-7000-8000-000000000000"


def _projected(entity_type, key):
    return ProjectedNode(
        entity_type=entity_type,
        entity_id=node_entity_id(entity_type, key),
        natural_key=key,
        name=key,
        fields={"name": key, "arn": key},
        configuration={key: 1, "_source": {"op": "Op", "why": "w"}},
        raw_item={key: 1},
    )


class TestNodeEnvelope:
    def test_shape_and_payload(self):
        env = node_envelope(_projected("aws_lambda", "arn:fn"), {"region": "us-east-1"})
        assert env["entity"] == {
            "entity_id": str(node_entity_id("aws_lambda", "arn:fn")),
            "entity_type": "aws_lambda",
            "name": "arn:fn",
            "dimensions": {"region": "us-east-1"},
        }
        # node payload is typed fields + the lossless configuration blob
        assert env["node"]["name"] == "arn:fn"
        assert env["node"]["configuration"]["_source"] == {"op": "Op", "why": "w"}


class TestAssembleBatch:
    def _doc(self, nodes, edges):
        return assemble_batch(
            source="plugins.aws_core.collectors.boto3_collector",
            manifest_version="0",
            account_id="123456789012",
            regions=["us-east-1", "us-west-2"],
            node_envelopes=nodes,
            edge_envelopes=edges,
            now=FIXED_NOW,
            batch_entity_id=FIXED_BATCH_ID,
        )

    def test_document_root_shape(self):
        doc = self._doc([], [])
        assert doc["metadata"] == {"grift_version": "0"}
        assert doc["_reserved"] == {}
        assert len(doc["batches"]) == 1  # one batch per run

    def test_batch_entity_and_provenance(self):
        n1 = node_envelope(_projected("aws_lambda", "a"), {})
        n2 = node_envelope(_projected("aws_lambda", "b"), {})
        n3 = node_envelope(_projected("aws_iam_role", "r"), {})
        edge = {"entity": {"entity_type": "edge"}, "edge": {}}
        batch = self._doc([n1, n2, n3], [edge])["batches"][0]

        assert batch["batch_entity"] == {
            "entity_id": FIXED_BATCH_ID,
            "entity_type": "batch",
            "name": "AWS collection 2026-01-02T03:04:05Z",
            "dimensions": {},
        }
        bn = batch["batch_node"]
        assert bn["source"] == "plugins.aws_core.collectors.boto3_collector"
        assert bn["description_json"]["format"] == COLLECTION_FORMAT
        data = bn["description_json"]["data"]
        assert data["manifest_version"] == "0"
        assert data["account_id"] == "123456789012"
        assert data["regions"] == ["us-east-1", "us-west-2"]
        assert data["counts"] == {
            "nodes": 3,
            "edges": 1,
            "by_entity_type": {"aws_iam_role": 1, "aws_lambda": 2},
        }

    def test_nodes_and_edges_pass_through(self):
        n = node_envelope(_projected("aws_s3_bucket", "bkt"), {})
        edge = {"entity": {"entity_type": "edge"}, "edge": {"edge_type": "X"}}
        batch = self._doc([n], [edge])["batches"][0]
        assert batch["nodes"] == [n]
        assert batch["edges"] == [edge]

    def test_no_deletion_or_tombstone_content(self):
        batch = self._doc([node_envelope(_projected("aws_lambda", "a"), {})], [])["batches"][0]
        # Assembler injects no deleted_at / tombstone / implied-absence keys.
        assert "deleted_at" not in batch["batch_entity"]
        assert all("deleted_at" not in n["entity"] for n in batch["nodes"])

    def test_account_id_may_be_none(self):
        doc = assemble_batch(
            source="s",
            manifest_version="0",
            account_id=None,
            regions=[],
            node_envelopes=[],
            edge_envelopes=[],
            now=FIXED_NOW,
            batch_entity_id=FIXED_BATCH_ID,
        )
        assert doc["batches"][0]["batch_node"]["description_json"]["data"]["account_id"] is None

    def test_batch_id_minted_when_not_overridden(self):
        doc = assemble_batch(
            source="s",
            manifest_version="0",
            account_id=None,
            regions=[],
            node_envelopes=[],
            edge_envelopes=[],
            now=FIXED_NOW,
        )
        minted = doc["batches"][0]["batch_entity"]["entity_id"]
        assert minted and minted != FIXED_BATCH_ID  # fresh uuid7 per run
