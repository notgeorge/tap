"""End-to-end vertical-slice proof: canned AWS payload -> real grid.

Drives the real Boto3Collector.run() pipeline (credentials -> manifest ->
source -> projection -> two-phase edges -> one GRIFT batch -> submit_grift)
with the AWS boundary stubbed by canned ListFunctions + ListRoles
responses, and asserts the typed nodes and the non-dangling ASSUMES_ROLE
edge actually landed on the grid by deterministic identity.

This is the make-it-work proof for the aws_op path; fan-out (S3, Route 53
custom_fn) and the hydrate seam are the next increment.
"""

from __future__ import annotations

import uuid

import pytest

from plugins.aws_core.collectors.boto3_collector import collector as collector_mod
from plugins.aws_core.collectors.boto3_collector import credentials as cred
from plugins.aws_core.collectors.boto3_collector.collector import Boto3Collector
from plugins.aws_core.collectors.boto3_collector.identity import (
    edge_entity_id,
    node_entity_id,
)
from tap_cares.collectors.config import CollectorConfig
from tap_cares.secrets.models import Secret, SecretRef

_ACCOUNT = "111122223333"
_FN_ARN = f"arn:aws:lambda:us-east-1:{_ACCOUNT}:function:sam-handler"
_ROLE_ARN = f"arn:aws:iam::{_ACCOUNT}:role/sam-exec"
_DIST_ARN = f"arn:aws:cloudfront::{_ACCOUNT}:distribution/E1ABCDEF"
_LOG_GROUP = "/aws/lambda/sam-handler"  # == the Lambda's LoggingConfig.LogGroup

_CANNED = {
    "list_functions": {
        "Functions": [
            {
                "FunctionName": "sam-handler",
                "FunctionArn": _FN_ARN,
                "Runtime": "python3.13",
                "Handler": "app.handler",
                "MemorySize": 256,
                "Timeout": 30,
                "Role": _ROLE_ARN,
                "LoggingConfig": {"LogGroup": "/aws/lambda/sam-handler"},
                "LastModified": "2026-01-02T03:04:05.000+0000",
            }
        ]
    },
    "list_roles": {
        "Roles": [
            {
                "RoleName": "sam-exec",
                "Arn": _ROLE_ARN,
                "Path": "/",
                "MaxSessionDuration": 3600,
            }
        ]
    },
    # Exercises CloudFront's RETRIEVES_CONTENT_FROM edge rule and its
    # s3_bucket_name_from_origin_domain transform (now registered); the
    # classify-skip regression test forces an empty registry to re-trigger
    # the EdgeError path deterministically.
    "list_distributions": {
        "DistributionList": {
            "Items": [
                {
                    "ARN": _DIST_ARN,
                    "DomainName": "d111abcdef.cloudfront.net",
                    "Status": "Deployed",
                    "Enabled": True,
                    "Origins": {"Items": [{"DomainName": "sam-site.s3.amazonaws.com"}]},
                    "ViewerCertificate": {},
                }
            ]
        }
    },
    # CloudWatch log group — proves the WRITES_LOGS edge resolves under the
    # v0 make-it-work (req-aws-collector-edges-7): the log group is keyed by
    # logGroupName, which equals the Lambda's LoggingConfig.LogGroup, so both
    # ends derive the identical natural_key and the edge is non-dangling.
    "describe_log_groups": {
        "logGroups": [
            {
                "logGroupName": _LOG_GROUP,
                "arn": f"arn:aws:logs:us-east-1:{_ACCOUNT}:log-group:{_LOG_GROUP}:*",
                "logGroupArn": f"arn:aws:logs:us-east-1:{_ACCOUNT}:log-group:{_LOG_GROUP}",
                "retentionInDays": 14,
            }
        ]
    },
    # IAM role tags — service side-quest (RGTA excludes IAM roles).
    "list_role_tags": {"Tags": [{"Key": "Owner", "Value": "sam-aydlette"}, {"Key": "Env", "Value": "prod"}]},
    # RGTA sweep result: the Lambda (rgta-source) tagged by its FunctionArn.
    "_rgta_pages": [
        {
            "ResourceTagMappingList": [
                {"ResourceARN": _FN_ARN, "Tags": [{"Key": "Owner", "Value": "sam"}]},
            ]
        }
    ],
}


class _RgtaPaginator:
    def paginate(self, **_kw):
        yield from _CANNED["_rgta_pages"]


class _CannedClient:
    """A boto3-client stand-in: canned ops return payloads, others empty."""

    def can_paginate(self, _method: str) -> bool:
        return False

    def get_paginator(self, _name: str) -> _RgtaPaginator:
        return _RgtaPaginator()

    def __getattr__(self, name: str):
        return lambda **_kw: _CANNED.get(name, {})


class _FakeEvents:
    """No-op botocore event emitter (fake clients fire no real events)."""

    def register(self, _name: str, _handler: object) -> None:
        return None


class _FakeSession:
    """Stands in for a boto3 Session for custom_fn (S3) paths."""

    events = _FakeEvents()

    def client(self, _service: str, **_kwargs: object) -> _CannedClient:
        return _CannedClient()


@pytest.fixture
def _stub_aws(monkeypatch):
    secret = Secret(
        ref=SecretRef(scope="aws", key="boto_collector"),
        kind="aws_static_access_key",
        description="test",
        data={
            "access_key_id": "AKIA",
            "secret_access_key": "shh",
            "regions_allowed": ["us-east-1"],
        },
        metadata={},
        source_path=__import__("pathlib").Path("/dev/null"),
    )
    monkeypatch.setattr(cred, "resolve_secret", lambda _ref: secret)
    monkeypatch.setattr(collector_mod, "build_session", lambda _data: _FakeSession())
    monkeypatch.setattr(collector_mod, "client_factory", lambda _s, _r: (lambda _svc: _CannedClient()))
    monkeypatch.setattr(collector_mod, "caller_account_id", lambda *a, **k: _ACCOUNT)


@pytest.mark.django_db
def test_canned_lambda_and_role_land_on_grid(_stub_aws):
    from tap_grid.services import get_edge, get_node

    collector = Boto3Collector(
        CollectorConfig(
            collector_entity_id=uuid.uuid7(),
            collection_job_entity_id=uuid.uuid7(),
        )
    )
    collector.run()

    # Pipeline completed cleanly: a batch imported, no structured errors.
    assert collector.results["error"] == []
    assert collector.grift_batches["imported"]
    assert "Collected" in collector.summary

    # The audit ledger drained as exactly one structured run-log entry
    # (req-aws-collector-audit-ledger). Fake clients don't fire botocore
    # events, so `calls` is empty here — the live run is the real proof;
    # this guards the drain wiring + shape.
    ledger_entries = [e for e in collector.results["info"] if e["message_code"] == "AWS_CALL_LEDGER"]
    assert len(ledger_entries) == 1
    assert isinstance(ledger_entries[0]["message_data"]["calls"], list)

    # The Lambda node landed, typed + lossless, by deterministic identity.
    fn = get_node(node_entity_id("aws_lambda", _FN_ARN))
    assert fn.name == "sam-handler"
    assert fn.runtime == "python3.13"
    assert fn.memory_size == 256
    assert fn.configuration["FunctionArn"] == _FN_ARN  # lossless blob
    assert fn.configuration["_source"]["op"] == "ListFunctions"

    # Lambda tags came via the RGTA path (joined by FunctionArn).
    assert fn.tags == {"Owner": "sam"}

    # The IAM role node landed (global-scope entry).
    role = get_node(node_entity_id("aws_iam_role", _ROLE_ARN))
    assert role.name == "sam-exec"
    assert role.role_arn == _ROLE_ARN
    # IAM role tags came via the service side-quest (ListRoleTags, list_kv).
    assert role.tags == {"Owner": "sam-aydlette", "Env": "prod"}

    # The ASSUMES_ROLE edge resolved by identity — non-dangling because both
    # endpoints were collected this run (two-phase, identity-resolved).
    edge = get_edge(edge_entity_id("ASSUMES_ROLE", _FN_ARN, _ROLE_ARN))
    assert edge.edge_type == "ASSUMES_ROLE"
    assert str(edge.from_entity_id) == str(node_entity_id("aws_lambda", _FN_ARN))
    assert str(edge.to_entity_id) == str(node_entity_id("aws_iam_role", _ROLE_ARN))

    # WRITES_LOGS resolves non-dangling under the v0 make-it-work
    # (req-aws-collector-edges-7): aws_cloudwatch_log_group is keyed by
    # logGroupName, so the Lambda's LoggingConfig.LogGroup and the log-group
    # node's natural_key are the byte-identical string — both ends derive the
    # same uuid5 with no resolver. (Pre-tweak this was a silent dangling edge:
    # name on the Lambda side vs an ARN-keyed log-group node.)
    lg = get_node(node_entity_id("aws_cloudwatch_log_group", _LOG_GROUP))
    assert lg.name == _LOG_GROUP
    log_edge = get_edge(edge_entity_id("WRITES_LOGS", _FN_ARN, _LOG_GROUP))
    assert log_edge.edge_type == "WRITES_LOGS"
    assert str(log_edge.from_entity_id) == str(node_entity_id("aws_lambda", _FN_ARN))
    assert str(log_edge.to_entity_id) == str(node_entity_id("aws_cloudwatch_log_group", _LOG_GROUP))


@pytest.mark.django_db
def test_unregistered_custom_fn_is_classified_not_fatal(_stub_aws):
    """Route 53 (custom_fn, unregistered until #19) skips, run still succeeds."""
    collector = Boto3Collector(
        CollectorConfig(
            collector_entity_id=uuid.uuid7(),
            collection_job_entity_id=uuid.uuid7(),
        )
    )
    collector.run()
    assert collector.results["error"] == []
    skips = [w for w in collector.results["warn"] if w["message_code"] == "ENTRY_SKIPPED"]
    assert any("route53" in s["message"] or "hosted_zone" in s["message"] for s in skips)


@pytest.mark.django_db
def test_unregistered_edge_transform_is_classified_not_fatal(_stub_aws, monkeypatch):
    """Regression (found on a live run): an EdgeError from the edge pass

    (a manifest transform with no registered callable) must be
    classified-and-skipped exactly like an unregistered custom_fn — it must
    not escape and abort the whole run before submit_grift. Forced
    deterministically with an empty transform registry, independent of which
    transforms ship registered.
    """
    from plugins.aws_core.collectors.boto3_collector.edges import TransformRegistry
    from tap_grid.services import get_node

    monkeypatch.setattr(collector_mod, "build_transform_registry", TransformRegistry)

    collector = Boto3Collector(
        CollectorConfig(
            collector_entity_id=uuid.uuid7(),
            collection_job_entity_id=uuid.uuid7(),
        )
    )
    collector.run()

    assert collector.results["error"] == []
    assert collector.grift_batches["imported"]  # run reached submit_grift
    skips = [w for w in collector.results["warn"] if w["message_code"] == "ENTRY_SKIPPED"]
    assert any("s3_bucket_name_from_origin_domain" in s["message"] for s in skips)

    # The distribution node still landed — it is appended before the edge
    # pass runs, so the skipped edge does not lose the node.
    dist = get_node(node_entity_id("aws_cloudfront_distribution", _DIST_ARN))
    assert dist.distribution_arn == _DIST_ARN
