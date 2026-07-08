"""Runtime-integration tests for the boto3 collector (no live AWS).

Covers req-aws-collector-runtime / -credentials: the aws_core-owned secret
schema, region resolution, self_test classification, class shape, and
dual-existence registration. The end-to-end run() proof is the next
increment (canned response -> grid).
"""

from __future__ import annotations

import inspect
from pathlib import Path

import jsonschema
import pytest
from tap_plugin.aws_core.collectors.boto3_collector import credentials as cred
from tap_plugin.aws_core.collectors.boto3_collector.collector import Boto3Collector
from tap_plugin.aws_core.collectors.boto3_collector.credentials import (
    AWS_STATIC_SCHEMA,
    CredentialError,
    resolve_regions,
)

from tap_cares.collectors import CollectorBase, CollectorReadinessStatus
from tap_cares.exceptions import SecretNotFoundError
from tap_cares.registry import collector_registry
from tap_cares.secrets.models import Secret, SecretRef

_REF = SecretRef(scope="aws_core", key="boto_collector")


def _secret(kind: str, data: dict) -> Secret:
    return Secret(
        ref=_REF,
        kind=kind,
        description="test",
        data=data,
        metadata={},
        source_path=Path("/dev/null"),
    )


_GOOD_DATA = {
    "access_key_id": "AKIA",
    "secret_access_key": "shh",
    "regions_allowed": ["us-east-1", "us-west-2"],
}


class TestAwsStaticSchema:
    def test_accepts_minimal_and_full(self):
        jsonschema.validate({"access_key_id": "a", "secret_access_key": "b"}, AWS_STATIC_SCHEMA)
        jsonschema.validate(
            {
                "access_key_id": "a",
                "secret_access_key": "b",
                "session_token": "t",
                "region": "us-east-1",
                "regions_allowed": ["us-east-1"],
            },
            AWS_STATIC_SCHEMA,
        )

    def test_rejects_missing_required(self):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"access_key_id": "a"}, AWS_STATIC_SCHEMA)

    def test_rejects_unknown_key_and_empty_regions(self):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                {"access_key_id": "a", "secret_access_key": "b", "role_arn": "x"},
                AWS_STATIC_SCHEMA,
            )
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                {"access_key_id": "a", "secret_access_key": "b", "regions_allowed": []},
                AWS_STATIC_SCHEMA,
            )


class TestResolveRegions:
    def test_regions_list_wins(self):
        assert resolve_regions({"regions_allowed": ["a", "b"], "region": "c"}) == ["a", "b"]

    def test_falls_back_to_singular_region(self):
        assert resolve_regions({"region": "us-east-1"}) == ["us-east-1"]

    def test_neither_raises(self):
        with pytest.raises(CredentialError, match="no region"):
            resolve_regions({})


class TestCollectorShape:
    def test_is_concrete_collectorbase(self):
        assert issubclass(Boto3Collector, CollectorBase)
        assert not inspect.isabstract(Boto3Collector)
        assert callable(Boto3Collector.run)
        assert callable(Boto3Collector.self_test)

    def test_registered_dual_existence(self):
        # apps.py ready() registered it during Django setup.
        assert collector_registry.get("boto3", scope="aws_core") is Boto3Collector


class TestSelfTest:
    def test_missing_secret_is_unconfigured(self, monkeypatch):
        def _raise(_ref):
            raise SecretNotFoundError("no secret registered")

        monkeypatch.setattr(cred, "resolve_secret", _raise)
        result = Boto3Collector.self_test()
        assert result.status == CollectorReadinessStatus.UNCONFIGURED
        assert not result.runnable

    def test_wrong_kind_is_misconfigured(self, monkeypatch):
        monkeypatch.setattr(cred, "resolve_secret", lambda _ref: _secret("other_kind", _GOOD_DATA))
        result = Boto3Collector.self_test()
        assert result.status == CollectorReadinessStatus.MISCONFIGURED

    def test_schema_invalid_is_misconfigured(self, monkeypatch):
        monkeypatch.setattr(
            cred, "resolve_secret", lambda _ref: _secret("aws_static_access_key", {"access_key_id": "a"})
        )
        result = Boto3Collector.self_test()
        assert result.status == CollectorReadinessStatus.MISCONFIGURED

    def test_reachable_is_ready(self, monkeypatch):
        monkeypatch.setattr(cred, "resolve_secret", lambda _ref: _secret("aws_static_access_key", _GOOD_DATA))
        monkeypatch.setattr(
            "tap_plugin.aws_core.collectors.boto3_collector.collector.caller_account_id",
            lambda *a, **k: "123456789012",
        )
        result = Boto3Collector.self_test()
        assert result.status == CollectorReadinessStatus.READY
        assert result.runnable

    def test_sts_unreachable_is_error(self, monkeypatch):
        from botocore.exceptions import NoCredentialsError

        monkeypatch.setattr(cred, "resolve_secret", lambda _ref: _secret("aws_static_access_key", _GOOD_DATA))

        def _boom(*_a, **_k):
            raise NoCredentialsError()

        monkeypatch.setattr("tap_plugin.aws_core.collectors.boto3_collector.collector.caller_account_id", _boom)
        result = Boto3Collector.self_test()
        assert result.status == CollectorReadinessStatus.ERROR
        assert not result.runnable
