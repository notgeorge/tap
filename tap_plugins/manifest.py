"""Plugin manifest reader and validator for tap-plugin.toml.

Implements req-plugin-manifest-v0-* from spec-plugin-manifest-v0.md.

Public API:
    load_manifest(plugin_root) -> PluginManifest
    validate_manifest_classes(manifest) -> None
"""

from __future__ import annotations

import json
import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema

logger = logging.getLogger(__name__)

_ALLOWED_TOP_KEYS = {
    "manifest_version",
    "plugin_version",
    "slug",
    "name",
    "description",
    "models",
    "edges",
    "editors",
    "searches",
    "grift",
}
_REQUIRED_TOP_KEYS = {"manifest_version", "plugin_version", "slug", "name"}

_EDGE_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "tap_grid" / "schemas" / "edge-definition.schema.json"
_edge_schema_cache: dict[str, Any] | None = None


def _load_edge_schema() -> dict[str, Any]:
    """Load and cache the edge definition JSON Schema."""
    global _edge_schema_cache
    if _edge_schema_cache is None:
        with open(_EDGE_SCHEMA_PATH) as fh:
            _edge_schema_cache = json.load(fh)
    return _edge_schema_cache


class PluginManifestError(Exception):
    """Raised when a tap-plugin.toml is invalid or fails validation."""


@dataclass
class ModelEntry:
    """One [models] entry declaring a TAP-managed model type."""

    slug: str
    class_path: str


@dataclass
class EdgeEntry:
    """One [edges] entry + the parsed contents of its .edge.json file."""

    slug: str
    file_path: str  # relative to plugin root
    name: str
    description: str
    sources: list[str] | None  # None = wildcard
    targets: list[str] | None  # None = wildcard
    property_schema: dict[str, Any] | None
    default_dimensions: dict[str, Any] | None


@dataclass
class EditorEntry:
    """One [editors] entry declaring an editor descriptor."""

    entity_type: str
    class_path: str


@dataclass
class SearchEntry:
    """One [searches] entry declaring a search runner callable."""

    runner_key: str
    callable_path: str


@dataclass
class GriftEntry:
    """One [grift] entry declaring a bundled GRIFT data file."""

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
    edges: list[EdgeEntry]
    editors: list[EditorEntry]
    searches: list[SearchEntry]
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

    models = _parse_models(raw.get("models", {}), manifest_path)
    edges = _parse_edges(raw.get("edges", {}), manifest_path, plugin_root)
    editors = _parse_editors(raw.get("editors", {}), manifest_path)
    searches = _parse_searches(raw.get("searches", {}), manifest_path)
    grift = _parse_grift(raw.get("grift", {}), manifest_path)

    manifest = PluginManifest(
        manifest_version=raw["manifest_version"],
        plugin_version=raw["plugin_version"],
        slug=raw["slug"],
        name=raw["name"],
        description=raw.get("description", ""),
        models=models,
        edges=edges,
        editors=editors,
        searches=searches,
        grift=grift,
        plugin_root=plugin_root,
    )

    _validate_convention_dirs(manifest)
    _validate_grift_paths(manifest)

    return manifest


# ---------------------------------------------------------------------------
# Section parsers
# ---------------------------------------------------------------------------


def _parse_models(raw_models: Any, manifest_path: Path) -> list[ModelEntry]:
    if not isinstance(raw_models, dict):
        raise PluginManifestError(f"'models' must be a table in {manifest_path}")

    entries: list[ModelEntry] = []
    for slug, class_path in raw_models.items():
        if not isinstance(class_path, str) or not class_path:
            raise PluginManifestError(f"models.{slug} must be a non-empty string class path in {manifest_path}")
        entries.append(ModelEntry(slug=slug, class_path=class_path))

    return entries


def _parse_edges(raw_edges: Any, manifest_path: Path, plugin_root: Path) -> list[EdgeEntry]:
    if not isinstance(raw_edges, dict):
        raise PluginManifestError(f"'edges' must be a table in {manifest_path}")

    seen_paths: set[str] = set()
    entries: list[EdgeEntry] = []

    for slug, rel_path in raw_edges.items():
        if not isinstance(rel_path, str) or not rel_path:
            raise PluginManifestError(f"edges.{slug} must be a non-empty string path in {manifest_path}")

        if ".." in Path(rel_path).parts:
            raise PluginManifestError(f"edges.{slug} path '{rel_path}' contains path traversal in {manifest_path}")

        if not rel_path.endswith(".edge.json"):
            raise PluginManifestError(
                f"edges.{slug} path '{rel_path}' must use the .edge.json extension in {manifest_path}"
            )

        if rel_path in seen_paths:
            raise PluginManifestError(f"Duplicate edge file path '{rel_path}' in {manifest_path}")
        seen_paths.add(rel_path)

        full_path = plugin_root / rel_path
        if not full_path.exists():
            raise PluginManifestError(
                f"Declared edge path '{rel_path}' not found at {full_path} (plugin manifest: {manifest_path})"
            )

        entry = _load_edge_file(slug, rel_path, full_path, manifest_path)
        entries.append(entry)

    return entries


def _load_edge_file(
    manifest_slug: str,
    rel_path: str,
    full_path: Path,
    manifest_path: Path,
) -> EdgeEntry:
    try:
        with open(full_path) as fh:
            data: dict[str, Any] = json.load(fh)
    except json.JSONDecodeError as exc:
        raise PluginManifestError(f"Edge file '{rel_path}' is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise PluginManifestError(f"Edge file '{rel_path}' must be a JSON object")

    # Validate against the edge definition JSON Schema.
    schema = _load_edge_schema()
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as exc:
        raise PluginManifestError(
            f"Edge file '{rel_path}' schema validation failed: {exc.message}"
        ) from exc

    # Slug must match the manifest key.
    file_slug = data["slug"]
    if file_slug != manifest_slug:
        raise PluginManifestError(
            f"Edge file '{rel_path}' slug '{file_slug}' does not match manifest key '{manifest_slug}'"
        )

    return EdgeEntry(
        slug=file_slug,
        file_path=rel_path,
        name=data["name"],
        description=data["description"],
        sources=data.get("sources"),
        targets=data.get("targets"),
        property_schema=data.get("property_schema"),
        default_dimensions=data.get("default_dimensions"),
    )


def _parse_editors(raw_editors: Any, manifest_path: Path) -> list[EditorEntry]:
    if not isinstance(raw_editors, dict):
        raise PluginManifestError(f"'editors' must be a table in {manifest_path}")

    entries: list[EditorEntry] = []
    for entity_type, class_path in raw_editors.items():
        if not isinstance(class_path, str) or not class_path:
            raise PluginManifestError(f"editors.{entity_type} must be a non-empty string class path in {manifest_path}")
        entries.append(EditorEntry(entity_type=entity_type, class_path=class_path))

    return entries


def _parse_searches(raw_searches: Any, manifest_path: Path) -> list[SearchEntry]:
    if not isinstance(raw_searches, dict):
        raise PluginManifestError(f"'searches' must be a table in {manifest_path}")

    entries: list[SearchEntry] = []
    for runner_key, callable_path in raw_searches.items():
        if not isinstance(callable_path, str) or not callable_path:
            raise PluginManifestError(
                f"searches.{runner_key} must be a non-empty string callable path in {manifest_path}"
            )
        entries.append(SearchEntry(runner_key=runner_key, callable_path=callable_path))

    return entries


def _parse_grift(raw_grift: Any, manifest_path: Path) -> list[GriftEntry]:
    if not isinstance(raw_grift, dict):
        raise PluginManifestError(f"'grift' must be a table in {manifest_path}")

    seen_paths: set[str] = set()
    entries: list[GriftEntry] = []

    for name, path in raw_grift.items():
        if not isinstance(path, str) or not path:
            raise PluginManifestError(f"grift.{name} must be a non-empty string path in {manifest_path}")

        if ".." in Path(path).parts:
            raise PluginManifestError(f"grift.{name} path '{path}' contains path traversal in {manifest_path}")

        if path in seen_paths:
            raise PluginManifestError(f"Duplicate GRIFT bundle path '{path}' in {manifest_path}")
        seen_paths.add(path)

        entries.append(GriftEntry(name=name, path=path))

    return entries


# ---------------------------------------------------------------------------
# Directory and path validators
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


def _validate_convention_dirs(manifest: PluginManifest) -> None:
    """Validate that convention directories exist when the corresponding surface is declared."""
    checks = [
        (manifest.models, "models"),
        (manifest.edges, "edges"),
        (manifest.searches, "searches"),
        (manifest.grift, "grift"),
    ]
    for entries, dirname in checks:
        if not entries:
            continue
        dir_path = manifest.plugin_root / dirname
        if not dir_path.is_dir():
            raise PluginManifestError(
                f"Plugin '{manifest.slug}' declares [{dirname}] but is missing "
                f"required '{dirname}/' directory at {manifest.plugin_root}"
            )


def _validate_grift_paths(manifest: PluginManifest) -> None:
    for entry in manifest.grift:
        full_path = manifest.plugin_root / entry.path
        if not full_path.exists():
            raise PluginManifestError(
                f"Declared GRIFT path '{entry.path}' not found at {full_path} " f"(plugin '{manifest.slug}')"
            )


# ---------------------------------------------------------------------------
# Runtime class validation (called after Django app registry is ready)
# ---------------------------------------------------------------------------


def validate_manifest_classes(manifest: PluginManifest) -> None:
    """Validate model, editor, and search callable classes declared in the manifest.

    Called during plugin startup after the Django app registry is ready.

    Args:
        manifest: A loaded PluginManifest.

    Raises:
        PluginManifestError: If any declared class cannot be imported or fails contract checks.
    """
    _validate_model_classes(manifest)
    _validate_editor_classes(manifest)
    _validate_search_callables(manifest)


def _validate_model_classes(manifest: PluginManifest) -> None:
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


def _validate_editor_classes(manifest: PluginManifest) -> None:
    from django.utils.module_loading import import_string

    from tap_web.editor import EditorDescriptor

    for entry in manifest.editors:
        try:
            cls = import_string(entry.class_path)
        except ImportError as exc:
            raise PluginManifestError(
                f"Cannot import editor class '{entry.class_path}' declared in plugin '{manifest.slug}': {exc}"
            ) from exc

        try:
            instance = cls()
        except Exception as exc:
            raise PluginManifestError(
                f"Editor class '{entry.class_path}' could not be instantiated in plugin '{manifest.slug}': {exc}"
            ) from exc

        if not isinstance(instance, EditorDescriptor):
            raise PluginManifestError(
                f"Editor class '{entry.class_path}' is not an EditorDescriptor subclass " f"in plugin '{manifest.slug}'"
            )

        if instance.entity_type != entry.entity_type:
            raise PluginManifestError(
                f"Editor class '{entry.class_path}' has entity_type='{instance.entity_type}' "
                f"but manifest declares '{entry.entity_type}' in plugin '{manifest.slug}'"
            )


def _validate_search_callables(manifest: PluginManifest) -> None:
    from django.utils.module_loading import import_string

    for entry in manifest.searches:
        try:
            obj = import_string(entry.callable_path)
        except ImportError as exc:
            raise PluginManifestError(
                f"Cannot import search callable '{entry.callable_path}' declared in plugin '{manifest.slug}': {exc}"
            ) from exc

        if not callable(obj):
            raise PluginManifestError(
                f"Search entry '{entry.runner_key}' resolves to a non-callable "
                f"'{entry.callable_path}' in plugin '{manifest.slug}'"
            )


# ---------------------------------------------------------------------------
# Undeclared file warnings
# ---------------------------------------------------------------------------


def warn_undeclared_convention_files(manifest: PluginManifest) -> None:
    """Warn about files in convention directories that are not declared in the manifest."""
    declared_grift_paths = {entry.path for entry in manifest.grift}
    declared_edge_paths = {entry.file_path for entry in manifest.edges}

    grift_dir = manifest.plugin_root / "grift"
    if grift_dir.is_dir():
        for grift_file in grift_dir.rglob("*.grift.json"):
            rel = str(grift_file.relative_to(manifest.plugin_root))
            if rel not in declared_grift_paths:
                logger.warning(
                    "[5fcb] Plugin '%s': undeclared GRIFT file '%s' in grift/ — not part of load contract",
                    manifest.slug,
                    rel,
                )

    edges_dir = manifest.plugin_root / "edges"
    if edges_dir.is_dir():
        for edge_file in edges_dir.glob("*.edge.json"):
            rel = str(edge_file.relative_to(manifest.plugin_root))
            if rel not in declared_edge_paths:
                logger.warning(
                    "[924b] Plugin '%s': undeclared edge file '%s' in edges/ — not part of load contract",
                    manifest.slug,
                    rel,
                )
