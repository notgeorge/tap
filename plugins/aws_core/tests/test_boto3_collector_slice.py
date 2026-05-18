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
}


class _CannedClient:
    """A boto3-client stand-in: canned ops return payloads, others empty."""

    def can_paginate(self, _method: str) -> bool:
        return False

    def __getattr__(self, name: str):
        return lambda: _CANNED.get(name, {})


@pytest.fixture
def _stub_aws(monkeypatch):
    secret = Secret(
        ref=SecretRef(scope="aws", key="collector"),
        kind="aws_static_access_key",
        description="test",
        data={
            "access_key_id": "AKIA",
            "secret_access_key": "shh",
            "regions": ["us-east-1"],
        },
        metadata={},
        source_path=__import__("pathlib").Path("/dev/null"),
    )
    monkeypatch.setattr(cred, "resolve_secret", lambda _ref: secret)
    monkeypatch.setattr(collector_mod, "build_session", lambda _data: object())
    monkeypatch.setattr(
        collector_mod, "client_factory", lambda _s, _r: (lambda _svc: _CannedClient())
    )
    monkeypatch.setattr(
        collector_mod, "caller_account_id", lambda *a, **k: _ACCOUNT
    )


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

    # The Lambda node landed, typed + lossless, by deterministic identity.
    fn = get_node(node_entity_id("aws_lambda", _FN_ARN))
    assert fn.name == "sam-handler"
    assert fn.runtime == "python3.13"
    assert fn.memory_size == 256
    assert fn.configuration["FunctionArn"] == _FN_ARN  # lossless blob
    assert fn.configuration["_source"]["op"] == "ListFunctions"

    # The IAM role node landed (global-scope entry).
    role = get_node(node_entity_id("aws_iam_role", _ROLE_ARN))
    assert role.name == "sam-exec"
    assert role.role_arn == _ROLE_ARN

    # The ASSUMES_ROLE edge resolved by identity — non-dangling because both
    # endpoints were collected this run (two-phase, identity-resolved).
    edge = get_edge(edge_entity_id("ASSUMES_ROLE", _FN_ARN, _ROLE_ARN))
    assert edge.edge_type == "ASSUMES_ROLE"
    assert str(edge.from_entity_id) == str(node_entity_id("aws_lambda", _FN_ARN))
    assert str(edge.to_entity_id) == str(node_entity_id("aws_iam_role", _ROLE_ARN))


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
