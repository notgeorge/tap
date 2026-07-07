"""Unit tests for the boto3 collector credential resolution.

Covers the two credential kinds and the cross-account assume-role path:
kind dispatch + consumer-side schema validation
(req-aws-core-secret-aws-static / req-aws-core-secret-aws-assumed-role) and the
session/assert helpers. Pure unit tests — no DB, no live AWS; STS is faked at
the boto3-session boundary.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tap_plugin.aws_core.collectors.boto3_collector import credentials as cred

from tap_cares.exceptions import SecretValidationError
from tap_cares.secrets import SecretRef
from tap_cares.secrets.models import Secret


def _secret(kind: str, data: dict[str, Any]) -> Secret:
    return Secret(
        ref=SecretRef(scope="aws_core", key="boto_collector"),
        kind=kind,
        description="test",
        data=data,
        metadata={},
        source_path=Path("/dev/null"),
    )


_BASE = {"access_key_id": "AKIA", "secret_access_key": "shh"}
_VALID_ASSUMED = {
    "role_arn": "arn:aws:iam::123456789012:role/TapAwsCoreCollectorReadOnly",
    "external_id": "shared-external-id",
    "base": _BASE,
    "regions_allowed": ["us-east-1"],
}


# --- kind dispatch + schema validation ------------------------------------


def test_resolve_accepts_assumed_role_kind(monkeypatch):
    monkeypatch.setattr(cred, "resolve_secret", lambda _ref: _secret(cred.AWS_ASSUMED_ROLE_KIND, dict(_VALID_ASSUMED)))
    secret = cred.resolve_aws_secret()
    assert secret.kind == cred.AWS_ASSUMED_ROLE_KIND
    assert cred.is_assumed_role(secret.data)


def test_resolve_still_accepts_static_kind(monkeypatch):
    data = {**_BASE, "regions_allowed": ["us-east-1"]}
    monkeypatch.setattr(cred, "resolve_secret", lambda _ref: _secret(cred.AWS_SECRET_KIND, data))
    secret = cred.resolve_aws_secret()
    assert secret.kind == cred.AWS_SECRET_KIND
    assert not cred.is_assumed_role(secret.data)


def test_resolve_rejects_assumed_role_missing_external_id(monkeypatch):
    # req-aws-core-secret-aws-assumed-role-2: external_id is mandatory.
    data = {"role_arn": _VALID_ASSUMED["role_arn"], "base": _BASE}
    monkeypatch.setattr(cred, "resolve_secret", lambda _ref: _secret(cred.AWS_ASSUMED_ROLE_KIND, data))
    with pytest.raises(SecretValidationError):
        cred.resolve_aws_secret()


def test_resolve_rejects_assumed_role_missing_base(monkeypatch):
    data = {"role_arn": _VALID_ASSUMED["role_arn"], "external_id": "x" * 8}
    monkeypatch.setattr(cred, "resolve_secret", lambda _ref: _secret(cred.AWS_ASSUMED_ROLE_KIND, data))
    with pytest.raises(SecretValidationError):
        cred.resolve_aws_secret()


def test_resolve_rejects_unsupported_kind(monkeypatch):
    monkeypatch.setattr(cred, "resolve_secret", lambda _ref: _secret("aws_wat", dict(_BASE)))
    with pytest.raises(SecretValidationError):
        cred.resolve_aws_secret()


def test_static_kind_rejects_role_arn(monkeypatch):
    # additionalProperties:false — a static secret carrying role_arn is invalid,
    # keeping the two kinds' shapes disjoint (so is_assumed_role is unambiguous).
    data = {**_BASE, "role_arn": "arn:aws:iam::123456789012:role/R", "regions_allowed": ["us-east-1"]}
    monkeypatch.setattr(cred, "resolve_secret", lambda _ref: _secret(cred.AWS_SECRET_KIND, data))
    with pytest.raises(SecretValidationError):
        cred.resolve_aws_secret()


def test_is_assumed_role_discriminates():
    assert cred.is_assumed_role({"role_arn": "arn"})
    assert not cred.is_assumed_role({"access_key_id": "a"})


# --- assume_role_session ---------------------------------------------------


class _FakeSTS:
    def __init__(self) -> None:
        self.captured: dict[str, Any] | None = None

    def assume_role(self, **kwargs: Any) -> dict[str, Any]:
        self.captured = kwargs
        return {
            "Credentials": {
                "AccessKeyId": "ASIATMP",
                "SecretAccessKey": "tmp-secret",
                "SessionToken": "tmp-token",
            }
        }


class _FakeBase:
    """Stands in for the base boto3 Session; records how the STS client is built."""

    def __init__(self, sts: _FakeSTS) -> None:
        self._sts = sts
        self.client_calls: list[tuple[str, dict[str, Any]]] = []

    def client(self, service: str, **kwargs: Any) -> _FakeSTS:
        self.client_calls.append((service, kwargs))
        return self._sts


def test_assume_role_session_sends_external_id_and_binds_temp_creds():
    sts = _FakeSTS()
    base = _FakeBase(sts)
    data = {**_VALID_ASSUMED, "duration_seconds": 1800}

    session = cred.assume_role_session(base, data, "us-east-1", role_session_name="run-xyz", timeout_seconds=5)

    assert sts.captured is not None
    assert sts.captured["RoleArn"] == data["role_arn"]
    assert sts.captured["ExternalId"] == "shared-external-id"  # always sent
    assert sts.captured["RoleSessionName"] == "run-xyz"  # explicit arg wins
    assert sts.captured["DurationSeconds"] == 1800
    # STS client built in the requested region.
    assert base.client_calls[0][0] == "sts"
    assert base.client_calls[0][1]["region_name"] == "us-east-1"
    # Returned session carries only the short-lived credentials.
    creds = session.get_credentials()
    assert creds.access_key == "ASIATMP"
    assert creds.token == "tmp-token"


def test_assume_role_session_defaults_session_name_and_omits_duration():
    sts = _FakeSTS()
    base = _FakeBase(sts)

    cred.assume_role_session(base, dict(_VALID_ASSUMED), "us-west-2")

    assert sts.captured is not None
    assert sts.captured["RoleSessionName"] == cred.DEFAULT_ROLE_SESSION_NAME
    assert "DurationSeconds" not in sts.captured  # omitted when unset


def test_assume_role_session_prefers_secret_session_name_over_default():
    sts = _FakeSTS()
    base = _FakeBase(sts)
    data = {**_VALID_ASSUMED, "role_session_name": "from-secret"}

    cred.assume_role_session(base, data, "us-east-1")

    assert sts.captured is not None
    assert sts.captured["RoleSessionName"] == "from-secret"


# --- assert-on-land --------------------------------------------------------


def test_account_mismatch_error():
    # req-aws-core-secret-aws-assumed-role-4
    assert cred.account_mismatch_error({"expected_account_id": "123456789012"}, "123456789012") is None
    assert cred.account_mismatch_error({}, "123456789012") is None  # no expectation → no error
    msg = cred.account_mismatch_error({"expected_account_id": "123456789012"}, "999999999999")
    assert msg is not None
    assert "999999999999" in msg and "123456789012" in msg
