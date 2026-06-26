"""Load and validate the samsite compliance collector's artifact manifest.

Spec: plugins/samsite/specs/spec-samsite-compliance-collector-v0.md
(req-samsite-collector-manifest). The manifest is declarative data — the
collector reads it; an agent reads it to know what the collector fetches
without reading collector code.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from tap.jsonfiles import JsonFileError, load_json_file, load_schema, validate_json

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
        manifest = load_json_file(_MANIFEST_PATH)
    except JsonFileError as exc:
        raise ArtifactManifestError(f"Artifact manifest could not be loaded: {exc}") from exc

    schema = load_schema(_SCHEMA_PATH)
    try:
        validate_json(manifest, schema, source=_MANIFEST_PATH)
    except JsonFileError as exc:
        raise ArtifactManifestError(
            f"Artifact manifest failed schema validation at {exc.location}: {exc.reason}"
        ) from exc

    return manifest
