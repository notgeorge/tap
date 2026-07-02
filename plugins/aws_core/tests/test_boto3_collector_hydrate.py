"""Unit tests for the fan-out hydrate template (boto3-free, no DB).

Covers req-aws-collector-hydrate: independent per-slot resilience, the
absent/denied/error/ok status distinction (never lossy), and the
self-describing _hydrate / _hydrate_mapping envelope on the item root.
"""

from __future__ import annotations

from botocore.exceptions import ClientError, ConnectTimeoutError

from tap_plugin.aws_core.collectors.boto3_collector.hydrate import hydrate_item

_HYDRATE_OPS = [
    {"key": "loc", "op": "GetBucketLocation", "why": "region"},
    {"key": "pab", "op": "GetPublicAccessBlock", "why": "exposure"},
    {"key": "enc", "op": "GetBucketEncryption", "why": "at-rest"},
    {"key": "pol", "op": "GetBucketPolicyStatus", "why": "public?"},
]


def _client_error(code: str, op: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, op)


class _FakeS3:
    """Per-op behavior: ok payload, or a raised error by code."""

    def get_bucket_location(self, **_):
        return {"LocationConstraint": "us-east-2", "ResponseMetadata": {"x": 1}}

    def get_public_access_block(self, **_):
        raise _client_error("AccessDenied", "GetPublicAccessBlock")

    def get_bucket_encryption(self, **_):
        raise _client_error(
            "ServerSideEncryptionConfigurationNotFoundError", "GetBucketEncryption"
        )

    def get_bucket_policy_status(self, **_):
        raise ConnectTimeoutError(endpoint_url="https://s3")


class TestHydrateItem:
    def test_envelope_shape_and_statuses(self):
        item = {"Name": "b", "BucketArn": "arn:aws:s3:::b"}
        env = hydrate_item(_FakeS3(), item, _HYDRATE_OPS, call_kwargs={"Bucket": "b"})

        # Root enumerate item preserved (identity source, never a slot).
        assert env["Name"] == "b"
        assert env["BucketArn"] == "arn:aws:s3:::b"

        rec = env["_hydrate"]
        # ok: data present, ResponseMetadata stripped.
        assert rec["loc"]["status"] == "ok"
        assert rec["loc"]["data"] == {"LocationConstraint": "us-east-2"}
        # denied: never conflated with absent.
        assert rec["pab"]["status"] == "denied"
        assert rec["pab"]["error_code"] == "AccessDenied"
        # absent: AWS "not configured" signal.
        assert rec["enc"]["status"] == "absent"
        # error: unexpected/transport (BotoCoreError subclass).
        assert rec["pol"]["status"] == "error"
        assert "data" not in rec["pab"]  # failure slots carry error_code, not data

    def test_mapping_is_self_describing(self):
        env = hydrate_item(_FakeS3(), {"Name": "b"}, _HYDRATE_OPS, call_kwargs={"Bucket": "b"})
        assert env["_hydrate_mapping"]["loc"] == {
            "op": "GetBucketLocation",
            "why": "region",
        }
        assert set(env["_hydrate_mapping"]) == {"loc", "pab", "enc", "pol"}

    def test_no_hydrate_ops_yields_empty_records(self):
        env = hydrate_item(_FakeS3(), {"Name": "b"}, [], call_kwargs={"Bucket": "b"})
        assert env["_hydrate"] == {}
        assert env["_hydrate_mapping"] == {}
        assert env["Name"] == "b"
