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
from tap_plugin.aws_core.collectors.boto3_collector import collector as collector_mod
from tap_plugin.aws_core.collectors.boto3_collector import credentials as cred
from tap_plugin.aws_core.collectors.boto3_collector.collector import Boto3Collector
from tap_plugin.aws_core.collectors.boto3_collector.identity import (
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
_ZONE_ID = "/hostedzone/ZSLICE000001"
_CF_DOMAIN = "d111abcdef.cloudfront.net"  # == _CANNED list_distributions DomainName

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
    # Route 53: a hosted zone whose A-alias targets the canned CloudFront
    # distribution — proves ROUTES_TRAFFIC resolves non-dangling via the
    # route53 custom_fn's domain->ARN cross-join (req-aws-collector-edges-7;
    # no transform — the custom_fn does the join, edge keyed by CF ARN).
    "list_hosted_zones": {
        "HostedZones": [
            {
                "Id": _ZONE_ID,
                "Name": "samsite.unified-systems.com.",
                "Config": {"PrivateZone": False},
                "ResourceRecordSetCount": 2,
            }
        ]
    },
    "list_resource_record_sets": {
        "ResourceRecordSets": [
            {  # IPv4 alias -> CloudFront
                "Name": "samsite.unified-systems.com.",
                "Type": "A",
                "AliasTarget": {"DNSName": f"{_CF_DOMAIN}."},
            },
            {  # IPv6 alias -> same CloudFront (the standard pair; must
                # dedupe to ONE edge or GRIFT rejects on duplicate_entity_id)
                "Name": "samsite.unified-systems.com.",
                "Type": "AAAA",
                "AliasTarget": {"DNSName": f"{_CF_DOMAIN}."},
            },
            {  # non-alias record — ignored by the custom_fn
                "Name": "txt.samsite.unified-systems.com.",
                "Type": "TXT",
                "ResourceRecords": [{"Value": '"v=spf1 -all"'}],
            },
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
        ref=SecretRef(scope="aws_core", key="boto_collector"),
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
    assert any(disposition == "imported" for _, disposition in collector._produced_batches)
    assert "Collected" in collector.summary

    # The audit ledger drained as exactly one structured run-log entry
    # (req-aws-collector-audit-ledger). Fake clients don't fire botocore
    # events, so `calls` is empty here — the live run is the real proof;
    # this guards the drain wiring + shape.
    ledger_entries = [e for e in collector.results["info"] if e["message_code"] == "AWS_CALL_LEDGER"]
    assert len(ledger_entries) == 1
    assert isinstance(ledger_entries[0]["message_data"]["calls"], list)

    # The Lambda node landed, typed + lossless, by deterministic identity.
    fn = get_node(node_entity_id("aws_core__aws_lambda", _FN_ARN))
    assert fn.name == "sam-handler"
    assert fn.runtime == "python3.13"
    assert fn.memory_size == 256
    assert fn.configuration["FunctionArn"] == _FN_ARN  # lossless blob
    assert fn.configuration["_source"]["op"] == "ListFunctions"

    # Lambda tags came via the RGTA path (joined by FunctionArn).
    assert fn.tags == {"Owner": "sam"}

    # The IAM role node landed (global-scope entry).
    role = get_node(node_entity_id("aws_core__aws_iam_role", _ROLE_ARN))
    assert role.name == "sam-exec"
    assert role.role_arn == _ROLE_ARN
    # IAM role tags came via the service side-quest (ListRoleTags, list_kv).
    assert role.tags == {"Owner": "sam-aydlette", "Env": "prod"}

    # The ASSUMES_ROLE edge resolved by identity — non-dangling because both
    # endpoints were collected this run (two-phase, identity-resolved).
    edge = get_edge(edge_entity_id("ASSUMES_ROLE__aws_core", _FN_ARN, _ROLE_ARN))
    assert edge.edge_type == "ASSUMES_ROLE__aws_core"
    assert str(edge.from_entity_id) == str(node_entity_id("aws_core__aws_lambda", _FN_ARN))
    assert str(edge.to_entity_id) == str(node_entity_id("aws_core__aws_iam_role", _ROLE_ARN))

    # WRITES_LOGS resolves non-dangling under the v0 make-it-work
    # (req-aws-collector-edges-7): aws_cloudwatch_log_group is keyed by
    # logGroupName, so the Lambda's LoggingConfig.LogGroup and the log-group
    # node's natural_key are the byte-identical string — both ends derive the
    # same uuid5 with no resolver. (Pre-tweak this was a silent dangling edge:
    # name on the Lambda side vs an ARN-keyed log-group node.)
    lg = get_node(node_entity_id("aws_core__aws_cloudwatch_log_group", _LOG_GROUP))
    assert lg.name == _LOG_GROUP
    log_edge = get_edge(edge_entity_id("WRITES_LOGS__aws_core", _FN_ARN, _LOG_GROUP))
    assert log_edge.edge_type == "WRITES_LOGS__aws_core"
    assert str(log_edge.from_entity_id) == str(node_entity_id("aws_core__aws_lambda", _FN_ARN))
    assert str(log_edge.to_entity_id) == str(node_entity_id("aws_core__aws_cloudwatch_log_group", _LOG_GROUP))

    # ROUTES_TRAFFIC resolves non-dangling through the route53 custom_fn's
    # CloudFront cross-join: the zone's A-alias domain -> the already-
    # collected CloudFront node by ARN identity. No transform — the
    # custom_fn did the domain->ARN join (req-aws-collector-edges-7). Note
    # the manifest-registered type is aws_route53_zone (model + plugin),
    # which the collector manifest was reconciled to.
    zone = get_node(node_entity_id("aws_core__aws_route53_zone", _ZONE_ID))
    assert zone.name == "samsite.unified-systems.com."
    route_edge = get_edge(edge_entity_id("ROUTES_TRAFFIC__aws_core", _ZONE_ID, _DIST_ARN))
    assert route_edge.edge_type == "ROUTES_TRAFFIC__aws_core"
    assert str(route_edge.from_entity_id) == str(node_entity_id("aws_core__aws_route53_zone", _ZONE_ID))
    assert str(route_edge.to_entity_id) == str(node_entity_id("aws_core__aws_cloudfront_distribution", _DIST_ARN))


@pytest.mark.django_db
def test_unregistered_custom_fn_is_classified_not_fatal(_stub_aws, monkeypatch):
    """An unregistered custom_fn classifies-and-skips; the run still succeeds.

    route53_zones_with_alias_targets and s3_buckets_hydrated now ship
    registered (#19), so — exactly like the transform regression below —
    this forces an empty custom_fn registry to re-trigger the
    classify-and-skip path deterministically, independent of which
    custom_fns ship registered.
    """
    from tap_plugin.aws_core.collectors.boto3_collector.source import CustomFnRegistry

    monkeypatch.setattr(collector_mod, "build_custom_fn_registry", CustomFnRegistry)

    collector = Boto3Collector(
        CollectorConfig(
            collector_entity_id=uuid.uuid7(),
            collection_job_entity_id=uuid.uuid7(),
        )
    )
    collector.run()
    assert collector.results["error"] == []
    assert collector._produced_batches  # run reached submit_grift
    skips = [w for w in collector.results["warn"] if w["message_code"] == "ENTRY_SKIPPED"]
    assert any("route53_zones_with_alias_targets" in s["message"] for s in skips)


@pytest.mark.django_db
def test_unregistered_edge_transform_is_classified_not_fatal(_stub_aws, monkeypatch):
    """Regression (found on a live run): an EdgeError from the edge pass

    (a manifest transform with no registered callable) must be
    classified-and-skipped exactly like an unregistered custom_fn — it must
    not escape and abort the whole run before submit_grift. Forced
    deterministically with an empty transform registry, independent of which
    transforms ship registered.
    """
    from tap_plugin.aws_core.collectors.boto3_collector.edges import TransformRegistry

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
    assert collector._produced_batches  # run reached submit_grift
    skips = [w for w in collector.results["warn"] if w["message_code"] == "ENTRY_SKIPPED"]
    assert any("s3_bucket_name_from_origin_domain" in s["message"] for s in skips)

    # The distribution node still landed — it is appended before the edge
    # pass runs, so the skipped edge does not lose the node.
    dist = get_node(node_entity_id("aws_core__aws_cloudfront_distribution", _DIST_ARN))
    assert dist.distribution_arn == _DIST_ARN


@pytest.mark.django_db
def test_rejected_grift_batch_fails_loudly_not_silently(_stub_aws, monkeypatch):
    """Regression (found live): GRIFT rejects a batch atomically on a hard
    error (e.g. duplicate_entity_id) -> imported=[] skipped=[]. A rejected
    batch is otherwise invisible (0 imported, 0 errors, false green). The
    abort-on-rejection guard now lives in CollectorBase.submit_grift
    (on_rejection="abort" default, req-tap-cares-collector-grift-import-9):
    it records GRIFT_BATCH_REJECTED on the collector's results and raises
    GriftRejectedError, which the task body turns into FAILED. End-to-end
    proof that the base guard fires through the real aws_core run path.
    """
    from tap_cares.exceptions import GriftRejectedError

    class _Issue:
        code = "duplicate_entity_id"
        message = "Duplicate entity_id 'deadbeef'"

    class _Counts:
        batches_imported = 0

    class _Result:
        imported_batches: list = []
        skipped_batches: list = []
        errors = [_Issue()]
        counts = _Counts()

    monkeypatch.setattr("tap_grid.grift.grift_import", lambda *a, **k: _Result())

    collector = Boto3Collector(
        CollectorConfig(
            collector_entity_id=uuid.uuid7(),
            collection_job_entity_id=uuid.uuid7(),
        )
    )
    with pytest.raises(GriftRejectedError):
        collector.run()

    errs = [e for e in collector.results["error"] if e["message_code"] == "GRIFT_BATCH_REJECTED"]
    assert len(errs) == 1
    assert "duplicate_entity_id" in errs[0]["message"]
    assert "nothing landed" in errs[0]["message"]
