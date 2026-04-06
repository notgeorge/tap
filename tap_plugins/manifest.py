"""Plugin manifest reader and validator for tap-plugin.toml.

Implements req-plugin-manifest-v0-* from spec-plugin-manifest-v0.md.

Public API:
    load_manifest(plugin_root) -> PluginManifest
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ALLOWED_TOP_KEYS = {"manifest_version", "plugin_version", "slug", "name", "description", "models", "grift"}
_REQUIRED_TOP_KEYS = {"manifest_version", "plugin_version", "slug", "name"}
_ALLOWED_MODEL_KEYS = {"slug", "class"}
_ALLOWED_GRIFT_KEYS = {"name", "path"}


class PluginManifestError(Exception):
    """Raised when a tap-plugin.toml is invalid or fails validation."""


@dataclass
class ModelEntry:
    """One [[models]] entry declaring a TAP-managed model type."""

    slug: str
    class_path: str  # 'class' is reserved; stored as class_path


@dataclass
class GriftEntry:
    """One [[grift]] entry declaring a bundled GRIFT data file."""

    name: str
    path: str


@dataclass
class PluginManifest:
    """Parsed and validated contents of a tap-plugin.toml file."""

    manifest_version: str
    plugin_version: str
    slug: str
    name: str
    description: str
    models: list[ModelEntry]
    grift: list[GriftEntry]
    plugin_root: Path


def load_manifest(plugin_root: Path) -> PluginManifest:
    """Load, parse, and validate tap-plugin.toml at *plugin_root*.

    Args:
        plugin_root: Absolute path to the plugin root directory.

    Returns:
        A validated PluginManifest.

    Raises:
        PluginManifestError: If the manifest is missing, malformed, or fails validation.
    """
    manifest_path = plugin_root / "tap-plugin.toml"
    if not manifest_path.exists():
        raise PluginManifestError(f"Missing tap-plugin.toml at {plugin_root}")

    try:
        with open(manifest_path, "rb") as fh:
            raw: dict[str, Any] = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise PluginManifestError(f"tap-plugin.toml is not valid TOML: {exc}") from exc

    _validate_top_level(raw, manifest_path)
    models = _parse_models(raw.get("models", []), manifest_path)
    grift = _parse_grift(raw.get("grift", []), manifest_path)

    manifest = PluginManifest(
        manifest_version=raw["manifest_version"],
        plugin_version=raw["plugin_version"],
        slug=raw["slug"],
        name=raw["name"],
        description=raw.get("description", ""),
        models=models,
        grift=grift,
        plugin_root=plugin_root,
    )

    _validate_models_dir(manifest)
    _validate_grift_paths(manifest)

    return manifest


# ---------------------------------------------------------------------------
# Internal validators
# ---------------------------------------------------------------------------


def _validate_top_level(raw: dict[str, Any], manifest_path: Path) -> None:
    unknown = set(raw.keys()) - _ALLOWED_TOP_KEYS
    if unknown:
        raise PluginManifestError(f"Unknown top-level keys in {manifest_path}: {sorted(unknown)}")

    for key in _REQUIRED_TOP_KEYS:
        value = raw.get(key)
        if not isinstance(value, str) or not value:
            raise PluginManifestError(f"Required field '{key}' must be a non-empty string in {manifest_path}")

    if raw["manifest_version"] != "0":
        raise PluginManifestError(
            f"Unsupported manifest_version '{raw['manifest_version']}' in {manifest_path}; expected '0'"
        )


def _parse_models(raw_models: Any, manifest_path: Path) -> list[ModelEntry]:
    if not isinstance(raw_models, list):
        raise PluginManifestError(f"'models' must be an array in {manifest_path}")

    seen_slugs: set[str] = set()
    entries: list[ModelEntry] = []

    for i, entry in enumerate(raw_models):
        if not isinstance(entry, dict):
            raise PluginManifestError(f"models[{i}] must be a table in {manifest_path}")

        unknown = set(entry.keys()) - _ALLOWED_MODEL_KEYS
        if unknown:
            raise PluginManifestError(f"Unknown keys in models[{i}] in {manifest_path}: {sorted(unknown)}")

        slug = entry.get("slug")
        class_path = entry.get("class")

        if not isinstance(slug, str) or not slug:
            raise PluginManifestError(f"models[{i}].slug must be a non-empty string in {manifest_path}")
        if not isinstance(class_path, str) or not class_path:
            raise PluginManifestError(f"models[{i}].class must be a non-empty string in {manifest_path}")

        if slug in seen_slugs:
            raise PluginManifestError(f"Duplicate model slug '{slug}' in {manifest_path}")
        seen_slugs.add(slug)

        entries.append(ModelEntry(slug=slug, class_path=class_path))

    return entries


def _parse_grift(raw_grift: Any, manifest_path: Path) -> list[GriftEntry]:
    if not isinstance(raw_grift, list):
        raise PluginManifestError(f"'grift' must be an array in {manifest_path}")

    seen_names: set[str] = set()
    seen_paths: set[str] = set()
    entries: list[GriftEntry] = []

    for i, entry in enumerate(raw_grift):
        if not isinstance(entry, dict):
            raise PluginManifestError(f"grift[{i}] must be a table in {manifest_path}")

        unknown = set(entry.keys()) - _ALLOWED_GRIFT_KEYS
        if unknown:
            raise PluginManifestError(f"Unknown keys in grift[{i}] in {manifest_path}: {sorted(unknown)}")

        name = entry.get("name")
        path = entry.get("path")

        if not isinstance(name, str) or not name:
            raise PluginManifestError(f"grift[{i}].name must be a non-empty string in {manifest_path}")
        if not isinstance(path, str) or not path:
            raise PluginManifestError(f"grift[{i}].path must be a non-empty string in {manifest_path}")

        if name in seen_names:
            raise PluginManifestError(f"Duplicate GRIFT bundle name '{name}' in {manifest_path}")
        if path in seen_paths:
            raise PluginManifestError(f"Duplicate GRIFT bundle path '{path}' in {manifest_path}")
        seen_names.add(name)
        seen_paths.add(path)

        # Reject path traversal outside plugin root
        resolved = (Path(".") / path).resolve()
        if ".." in Path(path).parts:
            raise PluginManifestError(f"grift[{i}].path '{path}' contains path traversal in {manifest_path}")

        entries.append(GriftEntry(name=name, path=path))

    return entries


def _validate_models_dir(manifest: PluginManifest) -> None:
    models_dir = manifest.plugin_root / "models"
    if not models_dir.is_dir():
        raise PluginManifestError(
            f"Plugin '{manifest.slug}' is missing required 'models/' directory at {manifest.plugin_root}"
        )


def _validate_grift_paths(manifest: PluginManifest) -> None:
    for entry in manifest.grift:
        full_path = manifest.plugin_root / entry.path
        if not full_path.exists():
            raise PluginManifestError(
                f"Declared GRIFT path '{entry.path}' not found at {full_path} "
                f"(plugin '{manifest.slug}')"
            )


def validate_model_classes(manifest: PluginManifest) -> None:
    """Validate that each declared model class resolves and matches its slug.

    Called during plugin startup after Django app registry is ready.

    Args:
        manifest: A loaded PluginManifest.

    Raises:
        PluginManifestError: If any declared class cannot be imported or slug mismatches.
    """
    from django.utils.module_loading import import_string

    for entry in manifest.models:
        try:
            cls = import_string(entry.class_path)
        except ImportError as exc:
            raise PluginManifestError(
                f"Cannot import model class '{entry.class_path}' declared in plugin '{manifest.slug}': {exc}"
            ) from exc

        entity_type = getattr(cls, "ENTITY_TYPE", None)
        if entity_type != entry.slug:
            raise PluginManifestError(
                f"Model class '{entry.class_path}' has ENTITY_TYPE='{entity_type}' "
                f"but manifest declares slug='{entry.slug}' in plugin '{manifest.slug}'"
            )


def warn_undeclared_convention_files(manifest: PluginManifest) -> None:
    """Warn about files in models/ or data/ that are not declared in the manifest.

    Emits logger warnings; does not raise.
    """
    declared_grift_paths = {entry.path for entry in manifest.grift}

    data_dir = manifest.plugin_root / "data"
    if data_dir.is_dir():
        for grift_file in data_dir.rglob("*.grift.json"):
            rel = str(grift_file.relative_to(manifest.plugin_root))
            if rel not in declared_grift_paths:
                logger.warning(
                    "Plugin '%s': undeclared GRIFT file '%s' in data/ — not part of load contract",
                    manifest.slug,
                    rel,
                )
