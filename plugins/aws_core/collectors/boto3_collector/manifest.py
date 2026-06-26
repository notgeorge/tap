"""Manifest loader for the boto3 collector.

Spec: plugins/aws_core/specs/spec-aws-core-collector-v0.md
(req-aws-collector-manifest). The manifest is pure data; this loads it and
validates it against the shipped JSON Schema at load. An invalid manifest is
an author error, not a runtime condition — it fails loud (per the AGENTS.md
Core TAP Rule: structured-data formats validate at load).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

from tap.jsonfiles import JsonFileError, load_json_file, load_schema, validate_json

_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = _DIR / "aws_resource_manifest.json"
SCHEMA_PATH = _DIR / "aws_resource_manifest.schema.json"


class ManifestError(Exception):
    """The resource manifest is missing, unparseable, or schema-invalid."""


@lru_cache(maxsize=1)
def load_manifest() -> dict[str, Any]:
    """Load and schema-validate the resource manifest.

    Returns the parsed manifest dict. Raises ``ManifestError`` if the file or
    schema is missing/unparseable or the manifest fails schema validation.
    """
    try:
        manifest: dict[str, Any] = load_json_file(MANIFEST_PATH)
        schema = load_schema(SCHEMA_PATH)
    except (JsonFileError, OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"Cannot read/parse manifest or schema: {exc}") from exc

    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        validate_json(manifest, schema, source=MANIFEST_PATH)
    except jsonschema.SchemaError as exc:
        raise ManifestError(f"Manifest schema is itself invalid: {exc.message}") from exc
    except JsonFileError as exc:
        raise ManifestError(f"Manifest failed schema validation: {exc}") from exc

    return manifest


def manifest_entries() -> list[dict[str, Any]]:
    """The validated manifest entries (one per resource type)."""
    entries: list[dict[str, Any]] = load_manifest()["entries"]
    return entries
