"""Tests for the zero-config secret-discovered AWS Steampipe collector."""

from __future__ import annotations

import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from plugins.aws_core.collectors.config import (
    AWS_COLLECTION_SCOPE,
    AWS_STEAMPIPE_SECRET_REF,
    AwsSteampipeConfigError,
    resolve_aws_collection_target,
)
from plugins.aws_core.collectors.credentials import resolve_aws_static_credentials
from plugins.aws_core.collectors.profiles import (
    AWS_CALLER_IDENTITY_QUERY,
    VPC_SUBNET_V0,
)
from plugins.aws_core.collectors.steampipe_inventory import AwsSteampipeInventoryCollector
from plugins.aws_core.collectors.steampipe_runner import (
    SteampipeExecutionError,
    SteampipeProfileResult,
    SteampipeQueryResult,
    SteampipeRunner,
    SteampipeUnavailableError,
    _parse_rows,
    redact_credential_values,
)
from tap_cares.collectors import CollectorConfig
from tap_cares.exceptions import SecretError, SecretNotFoundError
from tap_cares.registry import collector_registry, get_collector
from tap_cares.secrets import Secret, secret_registry

_WELL_KNOWN = AWS_STEAMPIPE_SECRET_REF  # SecretRef("aws", "steampipe-collector")


def _collector_config() -> CollectorConfig:
    return CollectorConfig(collector_entity_id=uuid4(), collection_job_entity_id=uuid4())


def _register_target_secret(
    *,
    account_id: str | None = "123456789012",
    region: str | None = "us-east-1",
    target_regions: list[str] | None = None,
    session_token: str = "",
    kind: str = "aws_static_access_key",
) -> None:
    """Register the well-known AWS collector secret in the test registry."""
    data: dict[str, object] = {
        "access_key_id": "AKIAFAKE",
        "secret_access_key": "secret-fake",
    }
    if region is not None:
        data["region"] = region
    if session_token:
        data["session_token"] = session_token
    metadata: dict[str, object] = {}
    if account_id is not None:
        metadata["account_id"] = account_id
    if target_regions is not None:
        metadata["target_regions"] = target_regions
    secret_registry.register(
        _WELL_KNOWN.key,
        Secret(
            ref=_WELL_KNOWN,
            kind=kind,
            description="Test AWS collector secret.",
            data=data,
            metadata=metadata,
            source_path=Path("/tmp/steampipe-collector.secret.json"),
        ),
        scope=_WELL_KNOWN.scope,
    )


@pytest.fixture(autouse=True)
def isolate_aws_collector_secret_registry():
    saved = secret_registry.all()
    secret_registry._reset_for_testing()
    yield
    secret_registry._reset_for_testing(saved)


class TestSecretDiscoveredTarget:
    def test_resolves_target_from_well_known_secret(self):
        _register_target_secret(account_id="123456789012", region="us-east-1")

        target = resolve_aws_collection_target()

        assert target.account_id == "123456789012"
        assert target.primary_region == "us-east-1"
        assert target.regions == ("us-east-1",)
        assert target.credentials.access_key_id == "AKIAFAKE"

    def test_to_context_is_json_safe_and_non_secret(self):
        _register_target_secret(account_id="123456789012", region="us-east-1")

        context = resolve_aws_collection_target().to_context()

        assert context == {
            "account_id": "123456789012",
            "primary_region": "us-east-1",
            "regions": ["us-east-1"],
            "scope": AWS_COLLECTION_SCOPE,
            "secret_ref": _WELL_KNOWN.qualified,
        }
        assert "AKIAFAKE" not in str(context)
        assert "secret-fake" not in str(context)

    def test_target_regions_downscopes_and_dedupes(self):
        _register_target_secret(
            region="us-east-1",
            target_regions=["us-east-1", "us-west-2", "us-east-1"],
        )

        target = resolve_aws_collection_target()

        assert target.primary_region == "us-east-1"
        assert target.regions == ("us-east-1", "us-west-2")

    def test_missing_secret_raises_not_found(self):
        with pytest.raises(SecretNotFoundError):
            resolve_aws_collection_target()

    def test_wrong_kind_raises_secret_error(self):
        _register_target_secret(kind="some_other_kind")

        with pytest.raises(SecretError):
            resolve_aws_collection_target()

    def test_missing_region_is_config_error(self):
        _register_target_secret(region=None)

        with pytest.raises(AwsSteampipeConfigError, match="data.region"):
            resolve_aws_collection_target()

    def test_missing_account_id_is_config_error(self):
        _register_target_secret(account_id=None)

        with pytest.raises(AwsSteampipeConfigError, match="metadata.account_id"):
            resolve_aws_collection_target()

    def test_bad_account_id_is_config_error(self):
        _register_target_secret(account_id="123")

        with pytest.raises(AwsSteampipeConfigError, match="metadata.account_id"):
            resolve_aws_collection_target()

    def test_bad_target_regions_is_config_error(self):
        _register_target_secret(target_regions=["not-a-region"])

        with pytest.raises(AwsSteampipeConfigError, match="target_regions"):
            resolve_aws_collection_target()


class TestQuerySet:
    def test_vpc_subnet_query_set_is_fixed(self):
        assert VPC_SUBNET_V0.key == "vpc-subnet-v0"
        assert [q.table for q in VPC_SUBNET_V0.queries] == ["aws_vpc", "aws_vpc_subnet"]
        assert [q.sql for q in VPC_SUBNET_V0.queries] == [
            "select * from aws_vpc;",
            "select * from aws_vpc_subnet;",
        ]

    def test_caller_identity_query_is_read_only_single_table(self):
        assert AWS_CALLER_IDENTITY_QUERY.table == "aws_caller_identity"
        assert AWS_CALLER_IDENTITY_QUERY.sql.strip().lower().startswith("select")


class TestAwsSteampipeCredentials:
    def test_resolves_static_credentials(self):
        _register_target_secret(session_token="session-fake")

        credentials = resolve_aws_static_credentials(_WELL_KNOWN)

        assert credentials.as_steampipe_env(region="us-west-2") == {
            "AWS_ACCESS_KEY_ID": "AKIAFAKE",
            "AWS_SECRET_ACCESS_KEY": "secret-fake",
            "AWS_SESSION_TOKEN": "session-fake",
            "AWS_REGION": "us-west-2",
            "AWS_DEFAULT_REGION": "us-west-2",
        }
        assert credentials.redaction_values() == (
            "AKIAFAKE",
            "secret-fake",
            "session-fake",
        )
        assert "secret-fake" not in repr(credentials)


class TestSteampipeRunner:
    def test_parse_rows_accepts_array(self):
        assert _parse_rows('[{"vpc_id": "vpc-1"}]') == [{"vpc_id": "vpc-1"}]

    def test_parse_rows_accepts_rows_object(self):
        assert _parse_rows('{"rows": [{"subnet_id": "subnet-1"}]}') == [
            {"subnet_id": "subnet-1"}
        ]

    def test_run_query_unavailable(self):
        query = VPC_SUBNET_V0.queries[0]
        runner = SteampipeRunner(binary="/definitely/not/steampipe")
        with pytest.raises(SteampipeUnavailableError, match="not found"):
            runner.run_query(query, region="us-east-1")

    def test_run_query_nonzero_redacts_stderr(self, monkeypatch):
        query = VPC_SUBNET_V0.queries[0]

        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=args[0],
                returncode=1,
                stdout="",
                stderr="bad AWS_SECRET_ACCESS_KEY value",
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(SteampipeExecutionError) as exc_info:
            SteampipeRunner().run_query(query, region="us-east-1")
        assert "AWS_SECRET_ACCESS_KEY" not in str(exc_info.value)
        assert "[redacted-key]" in str(exc_info.value)

    def test_run_query_nonzero_redacts_secret_values(self, monkeypatch):
        query = VPC_SUBNET_V0.queries[0]

        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=args[0],
                returncode=1,
                stdout="",
                stderr="credential secret-fake failed",
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(SteampipeExecutionError) as exc_info:
            SteampipeRunner().run_query(
                query,
                region="us-east-1",
                redaction_values=("secret-fake",),
            )
        assert "secret-fake" not in str(exc_info.value)
        assert "[redacted-value]" in str(exc_info.value)

    def test_redact_credential_values_ignores_empty_extra_values(self):
        assert redact_credential_values("ok", extra_values=("",)) == "ok"


class FakeQuerySetRunner:
    """Stand-in for SteampipeRunner.run_query_set in collector run() tests."""

    def run_query_set(self, query_set, *, region, env=None, redaction_values=()):
        assert query_set is VPC_SUBNET_V0
        assert region == "us-east-1"
        assert env == {
            "AWS_ACCESS_KEY_ID": "AKIAFAKE",
            "AWS_SECRET_ACCESS_KEY": "secret-fake",
            "AWS_REGION": "us-east-1",
            "AWS_DEFAULT_REGION": "us-east-1",
        }
        assert redaction_values == ("AKIAFAKE", "secret-fake")
        return SteampipeProfileResult(
            rows_by_table={
                "aws_vpc": [{"vpc_id": "vpc-1"}],
                "aws_vpc_subnet": [
                    {"subnet_id": "subnet-1"},
                    {"subnet_id": "subnet-2"},
                ],
            },
            warnings=[],
        )


class _IdentityRunner:
    """Stand-in runner whose run_query answers the identity probe."""

    account_id = "123456789012"
    raises: type[Exception] | None = None

    def __init__(self, *, timeout_seconds: int = 120, **_: object) -> None:
        self.timeout_seconds = timeout_seconds

    def run_query(self, query, *, region, env=None, redaction_values=()):
        assert query is AWS_CALLER_IDENTITY_QUERY
        if self.raises is not None:
            raise self.raises("boom")
        return SteampipeQueryResult(
            table="aws_caller_identity",
            rows=[{"account_id": self.account_id, "arn": "arn:aws:iam::x:user/y"}],
        )


class TestAwsSteampipeInventoryCollectorRun:
    def test_run_collects_rows(self):
        _register_target_secret(account_id="123456789012", region="us-east-1")
        collector = AwsSteampipeInventoryCollector(_collector_config())
        collector.runner_cls = FakeQuerySetRunner

        collector.run()

        assert collector.summary == (
            "Collected AWS vpc-subnet-v0 (acct 123456789012): "
            "1 VPC rows, 2 subnet rows (normalization pending)."
        )
        assert collector.profile_result is not None
        assert collector.results["error"] == []
        assert [entry["message_code"] for entry in collector.results["info"]] == [
            "RUN_STARTED",
            "COLLECTED",
            "RUN_COMPLETED",
        ]

    def test_run_records_secret_missing(self):
        collector = AwsSteampipeInventoryCollector(_collector_config())

        with pytest.raises(SecretNotFoundError):
            collector.run()

        error = collector.results["error"][0]
        assert error["message_code"] == "SECRET_MISSING_FILE"
        assert "steampipe-collector.secret.json" in error["message"]
        assert "restart the web container" in error["message"]
        assert error["message_data"]["secret_ref"] == _WELL_KNOWN.qualified
        assert (
            error["message_data"]["expected_secret_filename"]
            == "steampipe-collector.secret.json"
        )
        assert "not loaded" in collector.summary

    def test_run_records_secret_invalid(self):
        _register_target_secret(kind="some_other_kind")
        collector = AwsSteampipeInventoryCollector(_collector_config())

        with pytest.raises(SecretError):
            collector.run()

        assert collector.results["error"][0]["message_code"] == "SECRET_INVALID"

    def test_run_records_target_invalid(self):
        _register_target_secret(account_id=None)
        collector = AwsSteampipeInventoryCollector(_collector_config())

        with pytest.raises(AwsSteampipeConfigError):
            collector.run()

        assert collector.results["error"][0]["message_code"] == "TARGET_INVALID"


class TestAwsSteampipeInventoryCollectorSelfTest:
    @staticmethod
    def _force_steampipe(monkeypatch, present: bool):
        monkeypatch.setattr(
            "plugins.aws_core.collectors.steampipe_inventory.shutil.which",
            lambda _: "/usr/local/bin/steampipe" if present else None,
        )

    def test_missing_secret_is_unconfigured(self, monkeypatch):
        self._force_steampipe(monkeypatch, present=True)

        result = AwsSteampipeInventoryCollector.self_test()

        assert result.status.value == "unconfigured"
        assert result.runnable is False
        codes = {c.code: c.status.value for c in result.checks}
        assert codes["AWS_SECRET_PRESENT"] == "fail"
        assert codes["SECRET_VALID"] == "skip"
        assert codes["AWS_IDENTITY"] == "skip"
        assert "secret-file" in result.checks[0].docs[0].ref

    def test_invalid_secret_is_misconfigured(self, monkeypatch):
        _register_target_secret(account_id=None)
        self._force_steampipe(monkeypatch, present=True)

        result = AwsSteampipeInventoryCollector.self_test()

        assert result.status.value == "misconfigured"
        assert [c.code for c in result.failed_checks] == ["SECRET_VALID"]

    def test_steampipe_missing_is_error_and_identity_skips(self, monkeypatch):
        _register_target_secret()
        self._force_steampipe(monkeypatch, present=False)

        result = AwsSteampipeInventoryCollector.self_test()

        assert result.status.value == "error"
        codes = {c.code: c.status.value for c in result.checks}
        assert codes["AWS_SECRET_PRESENT"] == "pass"
        assert codes["SECRET_VALID"] == "pass"
        assert codes["STEAMPIPE_AVAILABLE"] == "fail"
        assert codes["AWS_IDENTITY"] == "skip"

    def test_identity_match_is_ready(self, monkeypatch):
        _register_target_secret(account_id="123456789012")
        self._force_steampipe(monkeypatch, present=True)
        runner = type("R", (_IdentityRunner,), {"account_id": "123456789012"})
        monkeypatch.setattr(AwsSteampipeInventoryCollector, "runner_cls", runner)

        result = AwsSteampipeInventoryCollector.self_test()

        assert result.status.value == "ready"
        assert result.runnable is True
        assert {c.code: c.status.value for c in result.checks}["AWS_IDENTITY"] == "pass"

    def test_identity_account_mismatch_is_misconfigured(self, monkeypatch):
        _register_target_secret(account_id="123456789012")
        self._force_steampipe(monkeypatch, present=True)
        runner = type("R", (_IdentityRunner,), {"account_id": "999999999999"})
        monkeypatch.setattr(AwsSteampipeInventoryCollector, "runner_cls", runner)

        result = AwsSteampipeInventoryCollector.self_test()

        assert result.status.value == "misconfigured"
        assert [c.code for c in result.failed_checks] == ["AWS_IDENTITY"]

    def test_identity_query_failure_is_error(self, monkeypatch):
        _register_target_secret(account_id="123456789012")
        self._force_steampipe(monkeypatch, present=True)
        runner = type("R", (_IdentityRunner,), {"raises": SteampipeExecutionError})
        monkeypatch.setattr(AwsSteampipeInventoryCollector, "runner_cls", runner)

        result = AwsSteampipeInventoryCollector.self_test()

        assert result.status.value == "error"
        assert [c.code for c in result.failed_checks] == ["AWS_IDENTITY"]


def test_aws_core_ready_registers_collector():
    assert (
        get_collector("plugins.aws_core.collectors.steampipe_inventory:steampipe-inventory")
        is AwsSteampipeInventoryCollector
    )
    assert "plugins.aws_core.collectors.steampipe_inventory:steampipe-inventory" in (
        collector_registry.keys()
    )
