"""Gridkin scenario discovery and JSON Schema validation.

Discovers `scenarios/*.gridkin.json`, validates each against
`scenarios/gridkin-scenario.schema.json`, and parses them into `Scenario`
objects. A malformed file is a hard, loud failure — not a skipped test.

Per spec-gridkin-v0.md: req-gridkin-scenario-format, req-gridkin-json-schema.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from tap.jsonfiles import JsonFileError, discover_json_files, instance_id, load_json_file, load_schema

# plugins/gryphon_playground/ — this file is gridkin/loader.py.
PLUGIN_ROOT: Path = Path(__file__).resolve().parent.parent
SCENARIOS_DIR: Path = PLUGIN_ROOT / "scenarios"
SCHEMA_PATH: Path = SCENARIOS_DIR / "gridkin-scenario.schema.json"

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
    """One Gridkin scenario, with every path resolved against the plugin root.

    `fixture_paths` is always a tuple of one or more paths; the loader
    normalizes the schema's string-or-array `grift_fixture` form into this
    canonical shape. Multi-fixture scenarios import each path in order
    (req-gridkin-multi-fixture-load).
    """

    scenario_id: str  # stable pytest-parametrize id, also the -k filter target
    feature: str
    name: str
    tags: tuple[str, ...]
    covers: tuple[str, ...]
    inspired_by: str | None
    layer: Literal["lite", "full", "extended"]
    query: str
    params: dict[str, Any]
    fixture_paths: tuple[Path, ...]
    # Result scenarios assert an envelope + SQL snapshot; rejection scenarios
    # (expected_error set) assert the query is refused. Exactly one mode applies.
    expected_envelope_path: Path | None
    expected_sql_path: Path | None
    source_file: Path
    soft_delete: tuple[str, ...] = ()
    expected_error: dict[str, Any] | None = None


def _slugify(text: str) -> str:
    """Lowercase, non-alphanumerics to single hyphens — for stable test ids."""
    out = "".join(ch if ch.isalnum() else "-" for ch in text.lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")


def discover_scenarios(scenarios_dir: Path = SCENARIOS_DIR) -> list[Scenario]:
    """Discover and validate every Gridkin scenario under `scenarios_dir`.

    Raises `GridkinScenarioError` if any file is invalid JSON or violates the
    scenario JSON Schema — surfaced at pytest collection time as a loud error.
    """
    schema = load_schema(SCHEMA_PATH)
    scenarios: list[Scenario] = []
    for path in discover_json_files(scenarios_dir, role="gridkin"):
        scenarios.extend(_parse_file(path, schema))
    return scenarios


def _parse_file(path: Path, schema: dict[str, Any]) -> list[Scenario]:
    try:
        document = load_json_file(path, schema=schema)
    except JsonFileError as exc:
        raise GridkinScenarioError(f"{path.name}: {exc}") from exc

    feature = document["feature"]
    background = document["background"]
    # `grift_fixture` is string OR array of strings per
    # gridkin-scenario.schema.json. Normalize both forms into a tuple of
    # Paths so the runner has one uniform shape to loop over
    # (req-gridkin-multi-fixture-load).
    raw_fixture = background["grift_fixture"]
    if isinstance(raw_fixture, str):
        fixture_paths = (PLUGIN_ROOT / raw_fixture,)
    else:
        fixture_paths = tuple(PLUGIN_ROOT / entry for entry in raw_fixture)
    soft_delete = tuple(background.get("soft_delete", []))
    feature_stem = instance_id(path, role="gridkin")

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
                fixture_paths=fixture_paths,
                expected_envelope_path=(
                    PLUGIN_ROOT / raw["expected_envelope"] if "expected_envelope" in raw else None
                ),
                expected_sql_path=(
                    PLUGIN_ROOT / raw["expected_sql_snapshot"] if "expected_sql_snapshot" in raw else None
                ),
                source_file=path,
                soft_delete=soft_delete,
                expected_error=raw.get("expected_error"),
            )
        )
    return parsed
