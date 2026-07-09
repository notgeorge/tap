"""Unit tests for the AWS Secrets Manager source.

The distribution is not installed in most stacks, so the module is loaded by file path
and boto3 is stubbed via ``sys.modules`` — the tests therefore collect and pass in any
lane without the AWS SDK or a live AWS account. The end-to-end path (ambient IAM →
GetSecretValue → git credential) is exercised by the CodeBuild samsite lane.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

_SRC = Path(__file__).resolve().parents[1] / "aws_secrets_source" / "source.py"


def _load_source() -> Any:
    spec = importlib.util.spec_from_file_location("aws_secrets_source_source_under_test", _SRC)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AwsSecretsManagerSource


AwsSecretsManagerSource = _load_source()


class _FakeSMClient:
    def __init__(self, secret_string: str | None) -> None:
        self._secret_string = secret_string
        self.requested: list[str] = []

    def get_secret_value(self, *, SecretId: str) -> dict[str, str]:
        self.requested.append(SecretId)
        return {"SecretString": self._secret_string} if self._secret_string is not None else {}


def _install_fake_boto3(
    monkeypatch: pytest.MonkeyPatch, client: _FakeSMClient, *, expect_region: str | None = None
) -> None:
    fake = types.ModuleType("boto3")

    def _client(service: str, region_name: str | None = None) -> _FakeSMClient:
        assert service == "secretsmanager"
        assert region_name == expect_region
        return client

    fake.client = _client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", fake)


def test_fetch_parses_json_object(monkeypatch):
    client = _FakeSMClient(json.dumps({"token": "t", "host": "github.com", "username": "x-access-token"}))
    _install_fake_boto3(monkeypatch, client)
    data = AwsSecretsManagerSource().fetch({"secret_id": "tap-ci/ghp"}, scope="tap_plugins.source", key="ghp")
    assert data == {"token": "t", "host": "github.com", "username": "x-access-token"}
    assert client.requested == ["tap-ci/ghp"]


def test_region_is_passed_through(monkeypatch):
    client = _FakeSMClient(json.dumps({"token": "t"}))
    _install_fake_boto3(monkeypatch, client, expect_region="us-east-1")
    data = AwsSecretsManagerSource().fetch({"secret_id": "tap-ci/ghp", "region": "us-east-1"}, scope="s.x", key="k")
    assert data == {"token": "t"}


def test_missing_secret_id_raises():
    with pytest.raises(ValueError, match="requires a non-empty source_ref.secret_id"):
        AwsSecretsManagerSource().fetch({}, scope="s.x", key="k")


def test_no_secret_string_raises(monkeypatch):
    _install_fake_boto3(monkeypatch, _FakeSMClient(None))
    with pytest.raises(ValueError, match="no SecretString"):
        AwsSecretsManagerSource().fetch({"secret_id": "x"}, scope="s.x", key="k")


def test_non_json_raises(monkeypatch):
    _install_fake_boto3(monkeypatch, _FakeSMClient("not json"))
    with pytest.raises(ValueError, match="not valid JSON"):
        AwsSecretsManagerSource().fetch({"secret_id": "x"}, scope="s.x", key="k")


def test_non_object_json_raises(monkeypatch):
    _install_fake_boto3(monkeypatch, _FakeSMClient(json.dumps(["a", "b"])))
    with pytest.raises(ValueError, match="must be a JSON object"):
        AwsSecretsManagerSource().fetch({"secret_id": "x"}, scope="s.x", key="k")
