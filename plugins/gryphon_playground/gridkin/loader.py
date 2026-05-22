"""Gridkin scenario discovery and JSON Schema validation.

Discovers `scenarios/*.gridkin.json`, validates each against
`scenarios/gridkin-scenario.schema.json`, and parses them into `Scenario`
objects. A malformed file is a hard, loud failure — not a skipped test.

Per spec-gridkin-v0.md: req-gridkin-scenario-format, req-gridkin-json-schema.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import jsonschema

# plugins/gryphon_playground/ — this file is gridkin/loader.py.
PLUGIN_ROOT: Path = Path(__file__).resolve().parent.parent
SCENARIOS_DIR: Path = PLUGIN_ROOT / "scenarios"
SCHEMA_PATH: Path = SCENARIOS_DIR / "gridkin-scenario.schema.json"

_FEATURE_SUFFIX = ".gridkin.json"

# Truthy environment-variable values. Anything else — unset, "", "0", "false",
# "no", "off" — is False, so GRIDKIN_*=0 cannot accidentally enable a switch.
_TRUTHY_ENV = {"1", "true", "yes", "on"}


def env_flag(name: str) -> bool:
    """True if environment variable `name` is set to a truthy value."""
    return os.environ.get(name, "").strip().lower() in _TRUTHY_ENV


class GridkinScenarioError(Exception):
    """A `.gridkin.json` file is malformed or violates the scenario schema."""


@dataclass(frozen=True)
class Scenario:
    """One Gridkin scenario, with every path resolved against the plugin root."""

    scenario_id: str  # stable pytest-parametrize id, also the -k filter target
    feature: str
    name: str
    tags: tuple[str, ...]
    covers: tuple[str, ...]
    inspired_by: str | None
    layer: Literal["lite", "full", "extended"]
    query: str
    params: dict[str, Any]
    fixture_path: Path
    expected_envelope_path: Path
    expected_sql_path: Path
    source_file: Path
    soft_delete: tuple[str, ...] = ()


def _slugify(text: str) -> str:
    """Lowercase, non-alphanumerics to single hyphens — for stable test ids."""
    out = "".join(ch if ch.isalnum() else "-" for ch in text.lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")


def _load_schema() -> dict[str, Any]:
    schema: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return schema


def discover_scenarios(scenarios_dir: Path = SCENARIOS_DIR) -> list[Scenario]:
    """Discover and validate every Gridkin scenario under `scenarios_dir`.

    Raises `GridkinScenarioError` if any file is invalid JSON or violates the
    scenario JSON Schema — surfaced at pytest collection time as a loud error.
    """
    if not scenarios_dir.is_dir():
        return []
    schema = _load_schema()
    scenarios: list[Scenario] = []
    for path in sorted(scenarios_dir.glob(f"*{_FEATURE_SUFFIX}")):
        scenarios.extend(_parse_file(path, schema))
    return scenarios


def _parse_file(path: Path, schema: dict[str, Any]) -> list[Scenario]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GridkinScenarioError(f"{path.name}: invalid JSON — {exc}") from exc

    try:
        jsonschema.validate(instance=document, schema=schema)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "(root)"
        raise GridkinScenarioError(f"{path.name}: schema violation at {location} — {exc.message}") from exc

    feature = document["feature"]
    background = document["background"]
    fixture_path = PLUGIN_ROOT / background["grift_fixture"]
    soft_delete = tuple(background.get("soft_delete", []))
    feature_stem = path.name[: -len(_FEATURE_SUFFIX)]

    parsed: list[Scenario] = []
    for raw in document["scenarios"]:
        parsed.append(
            Scenario(
                scenario_id=f"{feature_stem}-{_slugify(raw['name'])}",
                feature=feature,
                name=raw["name"],
                tags=tuple(raw.get("tags", [])),
                covers=tuple(raw["covers"]),
                inspired_by=raw.get("inspired_by"),
                layer=raw.get("layer", "full"),
                query=raw["query"],
                params=raw.get("params", {}),
                fixture_path=fixture_path,
                expected_envelope_path=PLUGIN_ROOT / raw["expected_envelope"],
                expected_sql_path=PLUGIN_ROOT / raw["expected_sql_snapshot"],
                source_file=path,
                soft_delete=soft_delete,
            )
        )
    return parsed
