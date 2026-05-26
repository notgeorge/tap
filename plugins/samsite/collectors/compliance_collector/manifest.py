"""Load and validate the samsite compliance collector's artifact manifest.

Spec: plugins/samsite/specs/spec-samsite-compliance-collector-v0.md
(req-samsite-collector-manifest). The manifest is declarative data — the
collector reads it; an agent reads it to know what the collector fetches
without reading collector code.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

_MANIFEST_PATH = Path(__file__).resolve().parent / "artifact_manifest.json"
_SCHEMA_PATH = Path(__file__).resolve().parent / "artifact_manifest.schema.json"


class ArtifactManifestError(Exception):
    """The artifact manifest is missing, malformed, or fails schema validation."""


@lru_cache(maxsize=1)
def load_manifest() -> dict[str, Any]:
    """Load and schema-validate the artifact manifest.

    Raises:
        ArtifactManifestError: the manifest file is missing, is not valid
            JSON, or fails validation against the manifest JSON Schema.
    """
    try:
        manifest = json.loads(_MANIFEST_PATH.read_text())
    except FileNotFoundError as exc:
        raise ArtifactManifestError(f"Artifact manifest not found: {_MANIFEST_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise ArtifactManifestError(f"Artifact manifest is not valid JSON: {exc}") from exc

    schema = json.loads(_SCHEMA_PATH.read_text())
    try:
        jsonschema.validate(manifest, schema)
    except jsonschema.ValidationError as exc:
        raise ArtifactManifestError(f"Artifact manifest failed schema validation: {exc.message}") from exc

    return manifest
