"""Tests for the AWS Steampipe collector shell."""

from __future__ import annotations

import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from plugins.aws_core.collectors.config import (
    AwsSteampipeCollectorConfig,
    AwsSteampipeConfigError,
)
from plugins.aws_core.collectors.credentials import resolve_aws_static_credentials
from plugins.aws_core.collectors.profiles import (
    AwsSteampipeProfileError,
    get_profile,
    list_profiles,
)
from plugins.aws_core.collectors.steampipe_inventory import AwsSteampipeInventoryCollector
from plugins.aws_core.collectors.steampipe_runner import (
    SteampipeExecutionError,
    SteampipeProfileResult,
    SteampipeRunner,
    SteampipeUnavailableError,
    _parse_rows,
    redact_credential_values,
)
from tap_cares.collectors import CollectorConfig
from tap_cares.registry import collector_registry, get_collector
from tap_cares.secrets import Secret, SecretRef, secret_registry


def _config_payload(**overrides):
    payload = {
        "target_key": "demo",
        "account_id": "123456789012",
        "partition": "aws",
        "secret_ref": {"scope": "aws", "key": "demo-readonly"},
        "regions": ["us-east-1"],
        "profile": "vpc-subnet-v0",
    }
    payload.update(overrides)
    return payload


def _collector_config() -> CollectorConfig:
    return CollectorConfig(collector_entity_id=uuid4(), collection_job_entity_id=uuid4())


def _register_aws_secret(
    *,
    access_key_id: str = "AKIAFAKE",
    secret_access_key: str = "secret-fake",
    session_token: str = "",
    region: str = "us-east-1",
    kind: str = "aws_static_access_key",
) -> None:
    data = {
        "access_key_id": access_key_id,
        "secret_access_key": secret_access_key,
        "region": region,
    }
    if session_token:
        data["session_token"] = session_token
    secret_registry.register(
        "demo-readonly",
        Secret(
            ref=SecretRef("aws", "demo-readonly"),
            kind=kind,
            description="Test AWS collector secret.",
            data=data,
            metadata={},
            source_path=Path("/tmp/demo-readonly.secret.json"),
        ),
        scope="aws",
    )


@pytest.fixture(autouse=True)
def isolate_aws_collector_secret_registry():
    saved = secret_registry.all()
    secret_registry._reset_for_testing()
    yield
    secret_registry._reset_for_testing(saved)


class TestAwsSteampipeCollectorConfig:
    def test_valid_config(self):
        cfg = AwsSteampipeCollectorConfig.from_mapping(_config_payload())
        assert cfg.target_key == "demo"
        assert cfg.account_id == "123456789012"
        assert cfg.partition == "aws"
        assert cfg.secret_ref == SecretRef(scope="aws", key="demo-readonly")
        assert cfg.regions == ("us-east-1",)
        assert cfg.profile == "vpc-subnet-v0"

    def test_context_is_json_safe_and_non_secret(self):
        cfg = AwsSteampipeCollectorConfig.from_mapping(_config_payload())
        assert cfg.to_context() == {
            "target_key": "demo",
            "account_id": "123456789012",
            "partition": "aws",
            "secret_ref": {"scope": "aws", "key": "demo-readonly"},
            "regions": ["us-east-1"],
            "profile": "vpc-subnet-v0",
        }

    @pytest.mark.parametrize(
        "overrides, message",
        [
            ({"target_key": "bad key"}, "target_key"),
            ({"account_id": "123"}, "account_id"),
            ({"partition": "aws-mars"}, "partition"),
            ({"secret_ref": {"scope": "aws"}}, "secret_ref.key"),
            ({"regions": []}, "regions"),
            ({"regions": ["not-a-region"]}, "regions"),
            ({"profile": "bad profile"}, "profile"),
        ],
    )
    def test_invalid_config(self, overrides, message):
        with pytest.raises(AwsSteampipeConfigError, match=message):
            AwsSteampipeCollectorConfig.from_mapping(_config_payload(**overrides))

    def test_deduplicates_regions_preserving_order(self):
        cfg = AwsSteampipeCollectorConfig.from_mapping(
            _config_payload(regions=["us-east-1", "us-west-2", "us-east-1"])
        )
        assert cfg.regions == ("us-east-1", "us-west-2")


class TestAwsSteampipeProfiles:
    def test_vpc_subnet_profile_is_fixed(self):
        profile = get_profile("vpc-subnet-v0")
        assert profile.key == "vpc-subnet-v0"
        assert [q.table for q in profile.queries] == ["aws_vpc", "aws_vpc_subnet"]
        assert [q.sql for q in profile.queries] == [
            "select * from aws_vpc;",
            "select * from aws_vpc_subnet;",
        ]

    def test_unknown_profile_rejected(self):
        with pytest.raises(AwsSteampipeProfileError, match="Unknown"):
            get_profile("select-*")

    def test_list_profiles(self):
        assert list_profiles() == ("vpc-subnet-v0",)


class TestAwsSteampipeCredentials:
    def test_resolves_static_credentials(self):
        _register_aws_secret(session_token="session-fake")

        credentials = resolve_aws_static_credentials(SecretRef("aws", "demo-readonly"))

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
        cfg = AwsSteampipeCollectorConfig.from_mapping(_config_payload())
        query = get_profile("vpc-subnet-v0").queries[0]
        runner = SteampipeRunner(binary="/definitely/not/steampipe")
        with pytest.raises(SteampipeUnavailableError, match="not found"):
            runner.run_query(query, config=cfg)

    def test_run_query_nonzero_redacts_stderr(self, monkeypatch):
        cfg = AwsSteampipeCollectorConfig.from_mapping(_config_payload())
        query = get_profile("vpc-subnet-v0").queries[0]

        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(
                args=args[0],
                returncode=1,
                stdout="",
                stderr="bad AWS_SECRET_ACCESS_KEY value",
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(SteampipeExecutionError) as exc_info:
            SteampipeRunner().run_query(query, config=cfg)
        assert "AWS_SECRET_ACCESS_KEY" not in str(exc_info.value)
        assert "[redacted-key]" in str(exc_info.value)

    def test_run_query_nonzero_redacts_secret_values(self, monkeypatch):
        cfg = AwsSteampipeCollectorConfig.from_mapping(_config_payload())
        query = get_profile("vpc-subnet-v0").queries[0]

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
                config=cfg,
                redaction_values=("secret-fake",),
            )
        assert "secret-fake" not in str(exc_info.value)
        assert "[redacted-value]" in str(exc_info.value)

    def test_redact_credential_values_ignores_empty_extra_values(self):
        assert redact_credential_values("ok", extra_values=("",)) == "ok"


class FakeRunner:
    def run_profile(self, profile, config, *, env=None, redaction_values=()):
        assert profile.key == "vpc-subnet-v0"
        assert config.target_key == "demo"
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
                "aws_vpc_subnet": [{"subnet_id": "subnet-1"}, {"subnet_id": "subnet-2"}],
            },
            warnings=[],
        )


class TestAwsSteampipeInventoryCollector:
    def test_run_collects_profile_rows(self, settings):
        settings.AWS_CORE_STEAMPIPE_COLLECTOR = _config_payload()
        _register_aws_secret()
        collector = AwsSteampipeInventoryCollector(_collector_config())
        collector.runner_cls = FakeRunner

        collector.run()

        assert collector.summary == (
            "Collected AWS demo vpc-subnet-v0: 1 VPC rows, 2 subnet rows "
            "(normalization pending)."
        )
        assert collector.profile_result is not None
        assert collector.results["error"] == []
        assert [entry["code"] for entry in collector.results["info"]] == [
            "RUN_STARTED",
            "PROFILE_COLLECTED",
            "RUN_COMPLETED",
        ]

    def test_run_records_config_failure(self, settings):
        settings.AWS_CORE_STEAMPIPE_COLLECTOR = _config_payload(regions=[])
        collector = AwsSteampipeInventoryCollector(_collector_config())

        with pytest.raises(AwsSteampipeConfigError):
            collector.run()

        assert collector.results["error"][0]["code"] == "CONFIG_INVALID"

    def test_run_records_secret_failure(self, settings):
        settings.AWS_CORE_STEAMPIPE_COLLECTOR = _config_payload()
        collector = AwsSteampipeInventoryCollector(_collector_config())

        with pytest.raises(Exception, match="No secret registered"):
            collector.run()

        assert collector.results["error"][0]["code"] == "SECRET_INVALID"
        assert collector.results["error"][0]["context"]["secret_ref"] == {
            "scope": "aws",
            "key": "demo-readonly",
        }
        assert "invalid or missing" in collector.summary


def test_aws_core_ready_registers_collector():
    assert (
        get_collector("plugins.aws_core.collectors.steampipe_inventory:steampipe-inventory")
        is AwsSteampipeInventoryCollector
    )
    assert "plugins.aws_core.collectors.steampipe_inventory:steampipe-inventory" in (
        collector_registry.keys()
    )
