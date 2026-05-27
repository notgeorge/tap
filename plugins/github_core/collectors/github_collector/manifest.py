"""Schema-validated loaders for the two collector manifests.

Spec: plugins/github_core/specs/spec-github-core-v0.md
(req-github-core-manifests-1/2). Manifests are JSON, validated against
JSON Schemas at load. Invalid manifests fail the run visibly (`jsonschema`
raises with the offending path).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

_HERE = Path(__file__).resolve().parent

COLLECTION_MANIFEST_PATH = _HERE / "github_collection_manifest.json"
COLLECTION_MANIFEST_SCHEMA_PATH = _HERE / "github_collection_manifest.schema.json"
LINK_MANIFEST_PATH = _HERE / "github_grid_link_manifest.json"
LINK_MANIFEST_SCHEMA_PATH = _HERE / "github_grid_link_manifest.schema.json"


def _load_validated(manifest_path: Path, schema_path: Path) -> dict[str, Any]:
    manifest: dict[str, Any] = json.loads(manifest_path.read_text())
    schema: dict[str, Any] = json.loads(schema_path.read_text())
    jsonschema.validate(instance=manifest, schema=schema)
    return manifest


def load_collection_manifest() -> dict[str, Any]:
    """Load + validate the github_collection_manifest.json document."""
    return _load_validated(COLLECTION_MANIFEST_PATH, COLLECTION_MANIFEST_SCHEMA_PATH)


def load_link_manifest() -> dict[str, Any]:
    """Load + validate the github_grid_link_manifest.json document."""
    return _load_validated(LINK_MANIFEST_PATH, LINK_MANIFEST_SCHEMA_PATH)
