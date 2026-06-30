"""Unit tests for the app-neutral runtime-secret resolver (tap/runtime_secrets.py).

Covers the envelope-shape validation contract and the by-scope/key file
discovery shared by tap_cares (the major secrets manager) and tap_auth. The
tap_cares loader and tap_auth provider have their own suites that assert the
domain-wrapped behavior; these test the shared kernel directly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tap.runtime_secrets import (
    SECRET_SUFFIX,
    RuntimeSecretError,
    SecretEnvelope,
    find_secret_file,
    load_secret_envelope,
    parse_secret_envelope,
    resolve_secret_envelope,
)


def _valid_payload(scope: str = "auth", key: str = "criticalsec-google") -> dict:
    return {
        "scope": scope,
        "key": key,
        "kind": "oidc_client",
        "description": "Google OIDC client for criticalsec.",
        "data": {"client_id": "abc", "client_secret": "shh"},
    }


def _write_secret(root: Path, payload: dict, *, basename: str | None = None) -> Path:
    name = basename if basename is not None else f"{payload['key']}{SECRET_SUFFIX}"
    path = root / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestParseSecretEnvelope:
    def test_valid(self) -> None:
        env = parse_secret_envelope(_valid_payload(), Path("x.secret.json"))
        assert isinstance(env, SecretEnvelope)
        assert env.scope == "auth"
        assert env.key == "criticalsec-google"
        assert env.qualified == "auth:criticalsec-google"
        assert env.data["client_id"] == "abc"
        assert env.metadata == {}  # defaulted when absent

    def test_not_a_json_object(self) -> None:
        with pytest.raises(RuntimeSecretError, match="must contain a JSON object"):
            parse_secret_envelope(["not", "a", "dict"], Path("x.secret.json"))

    def test_missing_required_field(self) -> None:
        payload = _valid_payload()
        del payload["kind"]
        with pytest.raises(RuntimeSecretError, match="missing required field"):
            parse_secret_envelope(payload, Path("x.secret.json"))

    def test_empty_description_rejected(self) -> None:
        payload = _valid_payload()
        payload["description"] = "   "
        with pytest.raises(RuntimeSecretError, match="description must be a non-empty string"):
            parse_secret_envelope(payload, Path("x.secret.json"))

    def test_data_must_be_object(self) -> None:
        payload = _valid_payload()
        payload["data"] = "nope"
        with pytest.raises(RuntimeSecretError, match="data must be a JSON object"):
            parse_secret_envelope(payload, Path("x.secret.json"))

    def test_metadata_must_be_object_when_present(self) -> None:
        payload = _valid_payload()
        payload["metadata"] = "nope"
        with pytest.raises(RuntimeSecretError, match="metadata must be a JSON object"):
            parse_secret_envelope(payload, Path("x.secret.json"))

    def test_repr_omits_secret_material(self) -> None:
        env = parse_secret_envelope(_valid_payload(), Path("x.secret.json"))
        rendered = repr(env)
        assert "shh" not in rendered
        assert "auth:criticalsec-google" in rendered


class TestLoadSecretEnvelope:
    def test_loads_valid_file(self, tmp_path: Path) -> None:
        path = _write_secret(tmp_path, _valid_payload())
        env = load_secret_envelope(path)
        assert env.qualified == "auth:criticalsec-google"

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.secret.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(RuntimeSecretError, match="invalid JSON"):
            load_secret_envelope(path)


class TestFindSecretFile:
    def test_found_at_root(self, tmp_path: Path) -> None:
        path = _write_secret(tmp_path, _valid_payload())
        assert find_secret_file(tmp_path, "auth", "criticalsec-google") == path

    def test_found_in_subdir(self, tmp_path: Path) -> None:
        sub = tmp_path / "nested" / "deeper"
        sub.mkdir(parents=True)
        path = _write_secret(sub, _valid_payload())
        assert find_secret_file(tmp_path, "auth", "criticalsec-google") == path

    def test_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(RuntimeSecretError, match="no secret file found"):
            find_secret_file(tmp_path, "auth", "absent")

    def test_root_not_a_directory_raises(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist"
        with pytest.raises(RuntimeSecretError, match="does not exist"):
            find_secret_file(missing, "auth", "x")

    def test_basename_match_but_wrong_scope_is_skipped(self, tmp_path: Path) -> None:
        # File whose basename matches the key glob but whose envelope declares a
        # different scope must not be returned.
        _write_secret(tmp_path, _valid_payload(scope="other"))
        with pytest.raises(RuntimeSecretError, match="no secret file found"):
            find_secret_file(tmp_path, "auth", "criticalsec-google")

    def test_unreadable_candidate_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "criticalsec-google.secret.json"
        bad.write_text("{not json", encoding="utf-8")
        with pytest.raises(RuntimeSecretError, match="unreadable/invalid JSON"):
            find_secret_file(tmp_path, "auth", "criticalsec-google")


class TestResolveSecretEnvelope:
    def test_discover_and_load(self, tmp_path: Path) -> None:
        _write_secret(tmp_path, _valid_payload())
        env = resolve_secret_envelope(tmp_path, "auth", "criticalsec-google")
        assert env.kind == "oidc_client"
        assert env.data["client_secret"] == "shh"
