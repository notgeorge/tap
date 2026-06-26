"""Unit tests for the shared JSON load/validate helper (spec-tap-json-files.md).

Pure filesystem + parsing tests — no Django, no DB. Cover the load path
(`req-tap-json-loader`), discovery (`req-tap-json-discovery`), and the uniform
`JsonFileError` contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tap.jsonfiles import (
    JsonFileError,
    discover_json_files,
    instance_id,
    load_json_file,
    load_schema,
)

_SCHEMA = {
    "type": "object",
    "required": ["name"],
    "properties": {"name": {"type": "string"}},
    "additionalProperties": False,
}


def _write(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_ok(tmp_path: Path) -> None:
    path = _write(tmp_path / "a.json", {"name": "x"})
    assert load_json_file(path) == {"name": "x"}


def test_load_with_schema_ok(tmp_path: Path) -> None:
    path = _write(tmp_path / "a.json", {"name": "x"})
    assert load_json_file(path, schema=_SCHEMA) == {"name": "x"}


def test_missing_file_raises_jsonfileerror(tmp_path: Path) -> None:
    with pytest.raises(JsonFileError) as exc:
        load_json_file(tmp_path / "nope.json")
    assert exc.value.location is None
    assert "could not read" in exc.value.reason


def test_malformed_json_raises_jsonfileerror(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(JsonFileError) as exc:
        load_json_file(path)
    assert exc.value.location is None
    assert "invalid JSON" in exc.value.reason


def test_schema_violation_sets_location(tmp_path: Path) -> None:
    path = _write(tmp_path / "a.json", {"name": 123})
    with pytest.raises(JsonFileError) as exc:
        load_json_file(path, schema=_SCHEMA)
    # The single place JSON-pointer location is formatted (req-tap-json-loader-3).
    assert exc.value.location == "name"


def test_schema_violation_root_location(tmp_path: Path) -> None:
    path = _write(tmp_path / "a.json", {"unexpected": 1})
    with pytest.raises(JsonFileError) as exc:
        load_json_file(path, schema=_SCHEMA)
    assert exc.value.location == "<root>"


def test_schema_can_be_a_path(tmp_path: Path) -> None:
    schema_path = _write(tmp_path / "thing.schema.json", _SCHEMA)
    data_path = _write(tmp_path / "a.json", {"name": "x"})
    assert load_json_file(data_path, schema=schema_path) == {"name": "x"}


def test_load_schema_is_cached(tmp_path: Path) -> None:
    schema_path = _write(tmp_path / "thing.schema.json", _SCHEMA)
    first = load_schema(schema_path)
    second = load_schema(schema_path)
    assert first is second  # lru_cache returns the same object


def test_discover_keys_on_role(tmp_path: Path) -> None:
    _write(tmp_path / "base.boot.json", {})
    _write(tmp_path / "prod.boot.json", {})
    _write(tmp_path / "stray.json", {})  # bare .json must NOT be discovered
    _write(tmp_path / "x.secret.json", {})
    found = discover_json_files(tmp_path, role="boot")
    assert [p.name for p in found] == ["base.boot.json", "prod.boot.json"]


def test_discover_skips_dotfiles(tmp_path: Path) -> None:
    _write(tmp_path / "a.boot.json", {})
    _write(tmp_path / ".hidden.boot.json", {})
    assert [p.name for p in discover_json_files(tmp_path, role="boot")] == ["a.boot.json"]


def test_discover_missing_dir_is_empty(tmp_path: Path) -> None:
    assert discover_json_files(tmp_path / "nope", role="boot") == []


def test_discover_recursive(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    _write(tmp_path / "a.grift.json", {})
    _write(tmp_path / "sub" / "b.grift.json", {})
    flat = discover_json_files(tmp_path, role="grift")
    deep = discover_json_files(tmp_path, role="grift", recursive=True)
    assert [p.name for p in flat] == ["a.grift.json"]
    assert sorted(p.name for p in deep) == ["a.grift.json", "b.grift.json"]


def test_instance_id_strips_full_suffix() -> None:
    # Path.stem would give "base.boot" — the helper must strip the full suffix.
    assert instance_id("base.boot.json", role="boot") == "base"
    assert instance_id(Path("/x/prod-readonly.secret.json"), role="secret") == "prod-readonly"


def test_instance_id_wrong_suffix_raises() -> None:
    with pytest.raises(JsonFileError):
        instance_id("base.json", role="boot")
