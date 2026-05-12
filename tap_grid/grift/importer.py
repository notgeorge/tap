"""GRIFT v0 importer — Grid Interchange Format.

Parses, validates, and imports a GRIFT document into the local TAP grid.

Public API:
    grift_import(document, *, dangling_edge_mode, actor) -> GriftImportResult
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import jsonschema
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from tap_grid.batch import close_batch, create_batch
from tap_grid.caller_context import CallerContext
from tap_grid.models import Entity
from tap_grid.service_types import WriteOperation
from tap_grid.services import write_batch

if TYPE_CHECKING:
    pass


GRIFT_VERSION = "0"
IMPORT_MODE = "upsert"
_GRIFT_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "grift-document.schema.json"
_grift_schema_cache: dict[str, Any] | None = None

# ---------------------------------------------------------------------------
# Result types (mirror the JSON schema in spec-grid-import-grift.md)
# ---------------------------------------------------------------------------


@dataclass
class GriftIssue:
    """One validation or execution issue from a GRIFT import run."""

    code: str
    message: str
    phase: Literal["parse", "schema", "validation", "preflight", "execution"]
    path: str
    entity_id: str | None
    batch_entity_id: str | None
    entity_type: str | None
    operation: str | None
    from_entity_id: str | None = None
    to_entity_id: str | None = None
    edge_entity_id: str | None = None


@dataclass
class GriftCounts:
    """Aggregate counts for a completed GRIFT import."""

    batches_imported: int = 0
    batches_skipped: int = 0
    batches_force_reimported: int = 0
    nodes_imported: int = 0
    edges_imported: int = 0
    edges_skipped: int = 0
    entities_swept: int = 0
    entities_purged: int = 0
    sweep_skipped: int = 0
    entities_upserted: int = 0
    errors: int = 0
    warnings: int = 0


@dataclass
class GriftSweptEntity:
    """Per-entity record for an entity tombstoned or purged by a batch-scoped sweep."""

    entity_id: str
    entity_type: str
    action: Literal["tombstone", "purge"]
    reason: str  # always "orphaned" for now; reserved for future taxonomy


@dataclass
class GriftSweepSkipped:
    """Per-entity record for a sweep candidate that failed a guardrail."""

    entity_id: str
    entity_type: str
    reason: Literal["sweep_skipped_external_write", "sweep_skipped_referenced"]


@dataclass
class GriftUpsertedEntity:
    """Per-entity record for a node or edge whose entity_id already existed in
    the grid and was replaced in-place by this batch's content.

    Emitted to make GRIFT's last-write-wins-per-entity contract visible during
    development. See req-grid-import-grift-ordering.
    """

    entity_id: str
    entity_type: str
    name: str | None
    kind: Literal["node", "edge"]


@dataclass
class GriftImportedBatch:
    """Per-batch summary for a successfully imported batch."""

    batch_entity_id: str
    path: str
    nodes_imported: int
    edges_imported: int
    edges_skipped: int
    errors_count: int
    warnings_count: int
    # Force-reimport specific fields (default empty for normal imports).
    force_reimported: bool = False
    swept_entities: list[GriftSweptEntity] = None  # type: ignore[assignment]
    sweep_skipped: list[GriftSweepSkipped] = None  # type: ignore[assignment]
    sweep_strict_aborted: bool = False
    # Per-entity upsert visibility: nodes/edges whose entity_id already existed
    # in the grid and were replaced in-place by this batch. See
    # req-grid-import-grift-ordering.
    upserted_entities: list[GriftUpsertedEntity] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.swept_entities is None:
            self.swept_entities = []
        if self.sweep_skipped is None:
            self.sweep_skipped = []
        if self.upserted_entities is None:
            self.upserted_entities = []


@dataclass
class GriftSkippedBatch:
    """Per-batch record for a batch that was skipped (e.g. already imported)."""

    batch_entity_id: str
    path: str
    reason: str


@dataclass
class GriftImportResult:
    """Full result of a grift_import() call."""

    success: bool
    grift_version: str
    import_mode: str
    dangling_edge_mode: str
    reference_time: str
    counts: GriftCounts
    imported_batches: list[GriftImportedBatch]
    skipped_batches: list[GriftSkippedBatch]
    errors: list[GriftIssue]
    warnings: list[GriftIssue]


# ---------------------------------------------------------------------------
# Internal preflight state
# ---------------------------------------------------------------------------


@dataclass
class _PreflightResult:
    ok: bool
    batches_to_import: list[tuple[int, dict[str, Any]]]
    batches_to_skip: list[GriftSkippedBatch]
    dangling_edge_ids: set[str]
    issues: list[GriftIssue]


# ---------------------------------------------------------------------------
# Schema sets
# ---------------------------------------------------------------------------

_DOC_REQUIRED = frozenset(["metadata", "_reserved", "batches"])
_DOC_ALLOWED = frozenset(["metadata", "_reserved", "batches"])
_METADATA_ALLOWED = frozenset(["grift_version"])
_BATCH_REQUIRED = frozenset(["batch_entity", "batch_node", "nodes", "edges"])
_BATCH_ALLOWED = frozenset(["batch_entity", "batch_node", "nodes", "edges"])
_NODE_REQUIRED = frozenset(["entity", "node"])
_NODE_ALLOWED = frozenset(["entity", "node"])
_EDGE_REQUIRED = frozenset(["entity", "edge"])
_EDGE_ALLOWED = frozenset(["entity", "edge"])
_ENVELOPE_REQUIRED = frozenset(["entity_id", "entity_type", "dimensions"])
_ENVELOPE_ALLOWED = frozenset(
    ["entity_id", "entity_type", "name", "dimensions", "created_at", "updated_at", "deleted_at"]
)
_EDGE_PAYLOAD_REQUIRED = frozenset(["from_entity_id", "to_entity_id", "edge_type", "properties"])
_EDGE_PAYLOAD_ALLOWED = frozenset(["from_entity_id", "to_entity_id", "edge_type", "properties"])

# Codes that are always treated as hard errors (not warnings).
_ERROR_CODES = frozenset(
    [
        "invalid_json",
        "schema_validation_failed",
        "duplicate_entity_id",
        "duplicate_batch_id",
        "unknown_entity_type",
        "payload_validation_failed",
        "timestamp_in_future",
        "timestamp_order_invalid",
        "entity_type_mismatch",
        "envelope_payload_name_mismatch",
        "dangling_edge",  # hard error in strict mode; warning surfaced separately in permissive
        "execution_failed",
        "force_reimport_refused_production",
        "sweep_purge_refused_production",
        "sweep_strict_aborted",
        "force_reimport_batch_not_found",
        "purge_requires_force_reimport",
    ]
)


# ---------------------------------------------------------------------------
# Issue factory
# ---------------------------------------------------------------------------


def _issue(
    code: str,
    message: str,
    phase: str,
    path: str,
    *,
    entity_id: str | None = None,
    batch_entity_id: str | None = None,
    entity_type: str | None = None,
    operation: str | None = None,
    from_entity_id: str | None = None,
    to_entity_id: str | None = None,
    edge_entity_id: str | None = None,
) -> GriftIssue:
    return GriftIssue(
        code=code,
        message=message,
        phase=phase,  # type: ignore[arg-type]
        path=path,
        entity_id=entity_id,
        batch_entity_id=batch_entity_id,
        entity_type=entity_type,
        operation=operation,
        from_entity_id=from_entity_id,
        to_entity_id=to_entity_id,
        edge_entity_id=edge_entity_id,
    )


# ---------------------------------------------------------------------------
# Low-level validators
# ---------------------------------------------------------------------------


def _check_uuid(value: Any, path: str, issues: list[GriftIssue], *, batch_entity_id: str | None = None) -> str | None:
    """Validate value is a UUID string. Returns the string if valid, else None."""
    if not isinstance(value, str):
        issues.append(
            _issue(
                "schema_validation_failed",
                f"Expected UUID string at {path}, got {type(value).__name__}",
                "schema",
                path,
                batch_entity_id=batch_entity_id,
            )
        )
        return None
    try:
        uuid.UUID(value)
        return value
    except ValueError:
        issues.append(
            _issue(
                "schema_validation_failed",
                f"Invalid UUID at {path}: {value!r}",
                "schema",
                path,
                batch_entity_id=batch_entity_id,
            )
        )
        return None


def _check_datetime(
    value: Any, path: str, issues: list[GriftIssue], *, batch_entity_id: str | None = None
) -> datetime | None:
    """Validate value is an RFC 3339 datetime string. Returns parsed datetime or None."""
    if value is None:
        return None
    if not isinstance(value, str):
        issues.append(
            _issue(
                "schema_validation_failed",
                f"Expected datetime string at {path}, got {type(value).__name__}",
                "schema",
                path,
                batch_entity_id=batch_entity_id,
            )
        )
        return None
    dt = parse_datetime(value)
    if dt is None:
        issues.append(
            _issue(
                "schema_validation_failed",
                f"Invalid datetime at {path}: {value!r}",
                "schema",
                path,
                batch_entity_id=batch_entity_id,
            )
        )
    return dt


def _make_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return timezone.make_aware(dt)
    return dt


# ---------------------------------------------------------------------------
# Entity envelope validator
# ---------------------------------------------------------------------------


def _validate_envelope(
    envelope: Any,
    path: str,
    issues: list[GriftIssue],
    *,
    reference_time: datetime,
    batch_entity_id: str | None = None,
) -> str | None:
    """Validate a GriftEntityEnvelope. Returns entity_id string if valid."""
    if not isinstance(envelope, dict):
        issues.append(
            _issue(
                "schema_validation_failed",
                f"Entity envelope at {path} must be an object",
                "schema",
                path,
                batch_entity_id=batch_entity_id,
            )
        )
        return None

    for key in envelope:
        if key not in _ENVELOPE_ALLOWED:
            issues.append(
                _issue(
                    "schema_validation_failed",
                    f"Unknown key '{key}' in entity envelope at {path}.{key}",
                    "schema",
                    f"{path}.{key}",
                    batch_entity_id=batch_entity_id,
                )
            )

    for req in _ENVELOPE_REQUIRED:
        if req not in envelope:
            issues.append(
                _issue(
                    "schema_validation_failed",
                    f"Missing required field '{req}' in entity envelope at {path}",
                    "schema",
                    f"{path}.{req}",
                    batch_entity_id=batch_entity_id,
                )
            )

    entity_id = _check_uuid(envelope.get("entity_id", ""), f"{path}.entity_id", issues, batch_entity_id=batch_entity_id)

    if "entity_type" in envelope:
        if not isinstance(envelope["entity_type"], str) or not envelope["entity_type"]:
            issues.append(
                _issue(
                    "schema_validation_failed",
                    f"entity_type must be a non-empty string at {path}.entity_type",
                    "schema",
                    f"{path}.entity_type",
                    batch_entity_id=batch_entity_id,
                )
            )

    if "dimensions" in envelope:
        dims = envelope["dimensions"]
        if not isinstance(dims, dict):
            issues.append(
                _issue(
                    "schema_validation_failed",
                    f"dimensions must be an object at {path}.dimensions",
                    "schema",
                    f"{path}.dimensions",
                    batch_entity_id=batch_entity_id,
                )
            )
        else:
            for k, v in dims.items():
                if not isinstance(k, str) or not isinstance(v, str):
                    issues.append(
                        _issue(
                            "schema_validation_failed",
                            f"dimensions must be string-to-string at {path}.dimensions",
                            "schema",
                            f"{path}.dimensions",
                            batch_entity_id=batch_entity_id,
                        )
                    )
                    break

    if "name" in envelope and envelope["name"] is not None:
        if not isinstance(envelope["name"], str) or not envelope["name"]:
            issues.append(
                _issue(
                    "schema_validation_failed",
                    f"name must be a non-empty string at {path}.name",
                    "schema",
                    f"{path}.name",
                    batch_entity_id=batch_entity_id,
                )
            )

    # Timestamp validation and ordering.
    created_at = _check_datetime(
        envelope.get("created_at"), f"{path}.created_at", issues, batch_entity_id=batch_entity_id
    )
    updated_at = _check_datetime(
        envelope.get("updated_at"), f"{path}.updated_at", issues, batch_entity_id=batch_entity_id
    )
    deleted_at_raw = envelope.get("deleted_at")
    deleted_at = (
        _check_datetime(deleted_at_raw, f"{path}.deleted_at", issues, batch_entity_id=batch_entity_id)
        if deleted_at_raw is not None
        else None
    )

    if deleted_at_raw is not None and "updated_at" not in envelope:
        issues.append(
            _issue(
                "timestamp_order_invalid",
                f"deleted_at requires updated_at to also be present at {path}",
                "validation",
                f"{path}.deleted_at",
                entity_id=entity_id,
                batch_entity_id=batch_entity_id,
            )
        )

    if created_at and updated_at and _make_aware(updated_at) < _make_aware(created_at):
        issues.append(
            _issue(
                "timestamp_order_invalid",
                f"updated_at must be >= created_at at {path}",
                "validation",
                f"{path}.updated_at",
                entity_id=entity_id,
                batch_entity_id=batch_entity_id,
            )
        )

    if updated_at and deleted_at and _make_aware(deleted_at) < _make_aware(updated_at):
        issues.append(
            _issue(
                "timestamp_order_invalid",
                f"deleted_at must be >= updated_at at {path}",
                "validation",
                f"{path}.deleted_at",
                entity_id=entity_id,
                batch_entity_id=batch_entity_id,
            )
        )

    for ts_name, ts_val in [("created_at", created_at), ("updated_at", updated_at), ("deleted_at", deleted_at)]:
        if ts_val is not None and _make_aware(ts_val) > reference_time:
            issues.append(
                _issue(
                    "timestamp_in_future",
                    f"{ts_name} is in the future at {path}.{ts_name}",
                    "validation",
                    f"{path}.{ts_name}",
                    entity_id=entity_id,
                    batch_entity_id=batch_entity_id,
                )
            )

    return entity_id


# ---------------------------------------------------------------------------
# Node payload validator
# ---------------------------------------------------------------------------


def _validate_node_payload(
    payload: Any,
    entity_type: str,
    path: str,
    issues: list[GriftIssue],
    *,
    batch_entity_id: str | None = None,
    entity_id: str | None = None,
) -> bool:
    """Validate node payload against the model's replace schema. Returns True if valid."""
    from tap_grid.registry import get_model_class

    if not isinstance(payload, dict):
        issues.append(
            _issue(
                "schema_validation_failed",
                f"node payload at {path} must be an object",
                "schema",
                path,
                entity_id=entity_id,
                batch_entity_id=batch_entity_id,
            )
        )
        return False

    try:
        model_cls = get_model_class(entity_type)
    except KeyError:
        issues.append(
            _issue(
                "unknown_entity_type",
                f"Unknown entity type '{entity_type}' at {path}",
                "validation",
                path,
                entity_id=entity_id,
                batch_entity_id=batch_entity_id,
                entity_type=entity_type,
            )
        )
        return False

    replace_schema = model_cls.SERVICE_CRUD_SCHEMA.get("replace", {})
    if replace_schema:
        try:
            jsonschema.validate(instance=payload, schema=replace_schema)
        except jsonschema.ValidationError as exc:
            issues.append(
                _issue(
                    "payload_validation_failed",
                    exc.message,
                    "validation",
                    f"{path}.{exc.json_path}" if exc.json_path != "$" else path,
                    entity_id=entity_id,
                    batch_entity_id=batch_entity_id,
                    entity_type=entity_type,
                )
            )
            return False

    return True


# ---------------------------------------------------------------------------
# Edge payload validator
# ---------------------------------------------------------------------------


def _validate_edge_payload(
    payload: Any,
    path: str,
    issues: list[GriftIssue],
    *,
    batch_entity_id: str | None = None,
    entity_id: str | None = None,
) -> bool:
    """Validate GriftEdgePayload shape. Returns True if structurally valid."""
    if not isinstance(payload, dict):
        issues.append(
            _issue(
                "schema_validation_failed",
                f"edge payload at {path} must be an object",
                "schema",
                path,
                entity_id=entity_id,
                batch_entity_id=batch_entity_id,
            )
        )
        return False

    for key in payload:
        if key not in _EDGE_PAYLOAD_ALLOWED:
            issues.append(
                _issue(
                    "schema_validation_failed",
                    f"Unknown key '{key}' in edge payload at {path}.{key}",
                    "schema",
                    f"{path}.{key}",
                    entity_id=entity_id,
                    batch_entity_id=batch_entity_id,
                )
            )

    for req in _EDGE_PAYLOAD_REQUIRED:
        if req not in payload:
            issues.append(
                _issue(
                    "schema_validation_failed",
                    f"Missing required field '{req}' in edge payload at {path}",
                    "schema",
                    f"{path}.{req}",
                    entity_id=entity_id,
                    batch_entity_id=batch_entity_id,
                )
            )

    ok = True
    for uuid_field in ("from_entity_id", "to_entity_id"):
        if (
            uuid_field in payload
            and _check_uuid(payload[uuid_field], f"{path}.{uuid_field}", issues, batch_entity_id=batch_entity_id)
            is None
        ):
            ok = False

    if "edge_type" in payload and (not isinstance(payload["edge_type"], str) or not payload["edge_type"]):
        issues.append(
            _issue(
                "schema_validation_failed",
                f"edge_type must be a non-empty string at {path}.edge_type",
                "schema",
                f"{path}.edge_type",
                entity_id=entity_id,
                batch_entity_id=batch_entity_id,
            )
        )
        ok = False

    if "properties" in payload and not isinstance(payload["properties"], dict):
        issues.append(
            _issue(
                "schema_validation_failed",
                f"properties must be an object at {path}.properties",
                "schema",
                f"{path}.properties",
                entity_id=entity_id,
                batch_entity_id=batch_entity_id,
            )
        )
        ok = False

    return ok


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


def _load_grift_schema() -> dict[str, Any]:
    """Load and cache the GRIFT document JSON Schema."""
    global _grift_schema_cache
    if _grift_schema_cache is None:
        with open(_GRIFT_SCHEMA_PATH) as fh:
            _grift_schema_cache = json.load(fh)
    return _grift_schema_cache


def _validate_document_schema(document: dict[str, Any], issues: list[GriftIssue]) -> bool:
    """Validate document against the GRIFT JSON Schema. Returns True if valid."""
    schema = _load_grift_schema()
    try:
        jsonschema.validate(instance=document, schema=schema)
        return True
    except jsonschema.ValidationError as exc:
        issues.append(
            _issue(
                "schema_validation_failed",
                f"GRIFT document schema validation failed: {exc.message}",
                "schema",
                exc.json_path if hasattr(exc, "json_path") else "$",
            )
        )
        return False


def _run_preflight(
    document: dict[str, Any],
    *,
    reference_time: datetime,
    dangling_edge_mode: Literal["strict", "permissive"],
    force_batches: set[str] | None = None,
) -> _PreflightResult:
    """Full-file preflight pass. No mutations — returns a _PreflightResult.

    When ``force_batches`` contains a batch's entity_id, the default
    skip-if-exists guard is bypassed and that batch is added to
    batches_to_import even when a Batch row already exists locally.
    """
    issues: list[GriftIssue] = []
    force_batches = force_batches or set()

    # --- JSON Schema structural validation ---
    if not _validate_document_schema(document, issues):
        return _PreflightResult(
            ok=False, batches_to_import=[], batches_to_skip=[], dangling_edge_ids=set(), issues=issues
        )

    # --- Top-level structure ---
    for key in document:
        if key not in _DOC_ALLOWED:
            issues.append(_issue("schema_validation_failed", f"Unknown top-level key '{key}'", "schema", f"$.{key}"))

    for req in _DOC_REQUIRED:
        if req not in document:
            issues.append(
                _issue("schema_validation_failed", f"Missing required top-level key '{req}'", "schema", f"$.{req}")
            )

    if any(i.code == "schema_validation_failed" for i in issues):
        return _PreflightResult(
            ok=False, batches_to_import=[], batches_to_skip=[], dangling_edge_ids=set(), issues=issues
        )

    # --- metadata ---
    metadata = document["metadata"]
    if not isinstance(metadata, dict):
        issues.append(_issue("schema_validation_failed", "metadata must be an object", "schema", "$.metadata"))
    else:
        for key in metadata:
            if key not in _METADATA_ALLOWED:
                issues.append(
                    _issue(
                        "schema_validation_failed", f"Unknown key '{key}' in metadata", "schema", f"$.metadata.{key}"
                    )
                )
        gv = metadata.get("grift_version")
        if gv is None:
            issues.append(
                _issue(
                    "schema_validation_failed",
                    "Missing grift_version in metadata",
                    "schema",
                    "$.metadata.grift_version",
                )
            )
        elif not isinstance(gv, str) or not gv:
            issues.append(
                _issue(
                    "schema_validation_failed",
                    "grift_version must be a non-empty string",
                    "schema",
                    "$.metadata.grift_version",
                )
            )

    if not isinstance(document.get("_reserved"), dict):
        issues.append(_issue("schema_validation_failed", "_reserved must be an object", "schema", "$._reserved"))

    if not isinstance(document.get("batches"), list):
        issues.append(_issue("schema_validation_failed", "batches must be an array", "schema", "$.batches"))
        return _PreflightResult(
            ok=False, batches_to_import=[], batches_to_skip=[], dangling_edge_ids=set(), issues=issues
        )

    if any(i.code == "schema_validation_failed" for i in issues):
        return _PreflightResult(
            ok=False, batches_to_import=[], batches_to_skip=[], dangling_edge_ids=set(), issues=issues
        )

    # --- Per-batch validation ---
    all_entity_ids: set[str] = set()
    all_batch_ids: set[str] = set()
    # Entity IDs that will be present after this import (in-file nodes, excluding edges).
    file_node_ids: set[str] = set()
    dangling_edge_ids: set[str] = set()
    batches_to_import: list[tuple[int, dict[str, Any]]] = []
    batches_to_skip: list[GriftSkippedBatch] = []

    for batch_idx, batch_container in enumerate(document["batches"]):
        batch_path = f"$.batches[{batch_idx}]"

        if not isinstance(batch_container, dict):
            issues.append(
                _issue("schema_validation_failed", f"Batch at {batch_path} must be an object", "schema", batch_path)
            )
            continue

        for key in batch_container:
            if key not in _BATCH_ALLOWED:
                issues.append(
                    _issue(
                        "schema_validation_failed",
                        f"Unknown key '{key}' in batch at {batch_path}.{key}",
                        "schema",
                        f"{batch_path}.{key}",
                    )
                )

        for req in _BATCH_REQUIRED:
            if req not in batch_container:
                issues.append(
                    _issue(
                        "schema_validation_failed",
                        f"Missing required key '{req}' in batch at {batch_path}",
                        "schema",
                        f"{batch_path}.{req}",
                    )
                )

        if not all(k in batch_container for k in _BATCH_REQUIRED):
            continue

        # Validate batch_entity envelope.
        batch_entity_id = _validate_envelope(
            batch_container["batch_entity"],
            f"{batch_path}.batch_entity",
            issues,
            reference_time=reference_time,
        )
        if batch_entity_id is None:
            continue

        # batch_entity.entity_type must be "batch".
        if batch_container["batch_entity"].get("entity_type") != "batch":
            got = batch_container["batch_entity"].get("entity_type")
            issues.append(
                _issue(
                    "entity_type_mismatch",
                    f"batch_entity.entity_type must be 'batch', got '{got}'",
                    "validation",
                    f"{batch_path}.batch_entity.entity_type",
                    entity_id=batch_entity_id,
                    batch_entity_id=batch_entity_id,
                )
            )

        # Duplicate batch-level checks.
        if batch_entity_id in all_batch_ids:
            issues.append(
                _issue(
                    "duplicate_batch_id",
                    f"Duplicate batch entity_id '{batch_entity_id}'",
                    "preflight",
                    f"{batch_path}.batch_entity.entity_id",
                    entity_id=batch_entity_id,
                    batch_entity_id=batch_entity_id,
                )
            )
            continue
        all_batch_ids.add(batch_entity_id)

        if batch_entity_id in all_entity_ids:
            issues.append(
                _issue(
                    "duplicate_entity_id",
                    f"Duplicate entity_id '{batch_entity_id}'",
                    "preflight",
                    f"{batch_path}.batch_entity.entity_id",
                    entity_id=batch_entity_id,
                    batch_entity_id=batch_entity_id,
                )
            )
            continue
        all_entity_ids.add(batch_entity_id)

        # Validate batch_node payload against Batch replace schema.
        if not isinstance(batch_container["batch_node"], dict):
            issues.append(
                _issue(
                    "schema_validation_failed",
                    f"batch_node at {batch_path}.batch_node must be an object",
                    "schema",
                    f"{batch_path}.batch_node",
                    batch_entity_id=batch_entity_id,
                )
            )
        else:
            from tap_grid.models import Batch

            replace_schema = Batch.SERVICE_CRUD_SCHEMA.get("replace", {})
            if replace_schema:
                try:
                    jsonschema.validate(instance=batch_container["batch_node"], schema=replace_schema)
                except jsonschema.ValidationError as exc:
                    issues.append(
                        _issue(
                            "payload_validation_failed",
                            exc.message,
                            "validation",
                            f"{batch_path}.batch_node",
                            entity_id=batch_entity_id,
                            batch_entity_id=batch_entity_id,
                        )
                    )

        # nodes/edges must be arrays.
        if not isinstance(batch_container["nodes"], list):
            issues.append(
                _issue(
                    "schema_validation_failed",
                    f"nodes at {batch_path}.nodes must be an array",
                    "schema",
                    f"{batch_path}.nodes",
                    batch_entity_id=batch_entity_id,
                )
            )
            continue
        if not isinstance(batch_container["edges"], list):
            issues.append(
                _issue(
                    "schema_validation_failed",
                    f"edges at {batch_path}.edges must be an array",
                    "schema",
                    f"{batch_path}.edges",
                    batch_entity_id=batch_entity_id,
                )
            )
            continue

        # Validate each node object.
        for node_idx, node_obj in enumerate(batch_container["nodes"]):
            node_path = f"{batch_path}.nodes[{node_idx}]"

            if not isinstance(node_obj, dict):
                issues.append(
                    _issue(
                        "schema_validation_failed",
                        f"Node at {node_path} must be an object",
                        "schema",
                        node_path,
                        batch_entity_id=batch_entity_id,
                    )
                )
                continue

            for key in node_obj:
                if key not in _NODE_ALLOWED:
                    issues.append(
                        _issue(
                            "schema_validation_failed",
                            f"Unknown key '{key}' in node at {node_path}.{key}",
                            "schema",
                            f"{node_path}.{key}",
                            batch_entity_id=batch_entity_id,
                        )
                    )

            for req in _NODE_REQUIRED:
                if req not in node_obj:
                    issues.append(
                        _issue(
                            "schema_validation_failed",
                            f"Missing required key '{req}' in node at {node_path}",
                            "schema",
                            f"{node_path}.{req}",
                            batch_entity_id=batch_entity_id,
                        )
                    )

            if not all(k in node_obj for k in _NODE_REQUIRED):
                continue

            node_entity_id = _validate_envelope(
                node_obj["entity"],
                f"{node_path}.entity",
                issues,
                reference_time=reference_time,
                batch_entity_id=batch_entity_id,
            )
            if node_entity_id is None:
                continue

            if node_entity_id in all_entity_ids:
                issues.append(
                    _issue(
                        "duplicate_entity_id",
                        f"Duplicate entity_id '{node_entity_id}'",
                        "preflight",
                        f"{node_path}.entity.entity_id",
                        entity_id=node_entity_id,
                        batch_entity_id=batch_entity_id,
                    )
                )
                continue
            all_entity_ids.add(node_entity_id)
            file_node_ids.add(node_entity_id)

            entity_type = node_obj["entity"].get("entity_type", "")
            _validate_node_payload(
                node_obj["node"],
                entity_type,
                f"{node_path}.node",
                issues,
                batch_entity_id=batch_entity_id,
                entity_id=node_entity_id,
            )

            # Identity Sanity for redundant identity-bearing fields. The GRIFT
            # envelope can carry `name` alongside the typed model payload that
            # also carries `name` (the model's name field is the source of
            # truth; the envelope's name is the spine projection). When both
            # are declared, they must agree exactly. Bundles that omit
            # `entity.name` (or set it empty) are unaffected — the spine
            # projection is materialized from the model's name on import.
            # See spec-grid-import-grift.md req-grid-import-grift-preflight
            # "Identity Sanity".
            envelope_name = node_obj["entity"].get("name")
            payload = node_obj.get("node")
            if (
                envelope_name
                and isinstance(payload, dict)
                and isinstance(payload.get("name"), str)
                and payload["name"]
                and envelope_name.strip() != payload["name"].strip()
            ):
                issues.append(
                    _issue(
                        "envelope_payload_name_mismatch",
                        (
                            f"Envelope name {envelope_name!r} does not match "
                            f"node payload name {payload['name']!r}. The "
                            f"GRIFT envelope's `name` is a projection of the "
                            f"typed model's name field; the two must match "
                            f"exactly when both are declared."
                        ),
                        "validation",
                        f"{node_path}.entity.name",
                        entity_id=node_entity_id,
                        batch_entity_id=batch_entity_id,
                        entity_type=entity_type,
                    )
                )

        # Validate each edge object.
        for edge_idx, edge_obj in enumerate(batch_container["edges"]):
            edge_path = f"{batch_path}.edges[{edge_idx}]"

            if not isinstance(edge_obj, dict):
                issues.append(
                    _issue(
                        "schema_validation_failed",
                        f"Edge at {edge_path} must be an object",
                        "schema",
                        edge_path,
                        batch_entity_id=batch_entity_id,
                    )
                )
                continue

            for key in edge_obj:
                if key not in _EDGE_ALLOWED:
                    issues.append(
                        _issue(
                            "schema_validation_failed",
                            f"Unknown key '{key}' in edge at {edge_path}.{key}",
                            "schema",
                            f"{edge_path}.{key}",
                            batch_entity_id=batch_entity_id,
                        )
                    )

            for req in _EDGE_REQUIRED:
                if req not in edge_obj:
                    issues.append(
                        _issue(
                            "schema_validation_failed",
                            f"Missing required key '{req}' in edge at {edge_path}",
                            "schema",
                            f"{edge_path}.{req}",
                            batch_entity_id=batch_entity_id,
                        )
                    )

            if not all(k in edge_obj for k in _EDGE_REQUIRED):
                continue

            edge_entity_id = _validate_envelope(
                edge_obj["entity"],
                f"{edge_path}.entity",
                issues,
                reference_time=reference_time,
                batch_entity_id=batch_entity_id,
            )
            if edge_entity_id is None:
                continue

            if edge_obj["entity"].get("entity_type") != "edge":
                got = edge_obj["entity"].get("entity_type")
                issues.append(
                    _issue(
                        "entity_type_mismatch",
                        f"edge entity envelope must have entity_type='edge', got '{got}'",
                        "validation",
                        f"{edge_path}.entity.entity_type",
                        entity_id=edge_entity_id,
                        batch_entity_id=batch_entity_id,
                    )
                )

            if edge_entity_id in all_entity_ids:
                issues.append(
                    _issue(
                        "duplicate_entity_id",
                        f"Duplicate entity_id '{edge_entity_id}'",
                        "preflight",
                        f"{edge_path}.entity.entity_id",
                        entity_id=edge_entity_id,
                        batch_entity_id=batch_entity_id,
                    )
                )
                continue
            all_entity_ids.add(edge_entity_id)

            _validate_edge_payload(
                edge_obj["edge"], f"{edge_path}.edge", issues, batch_entity_id=batch_entity_id, entity_id=edge_entity_id
            )

        # Check batch idempotency: already exists locally?
        # req-grid-import-grift-force-reimport: bypass the skip-if-exists guard
        # when this batch_entity_id is in the explicit force_batches set.
        from tap_grid.models import Batch

        already_exists = Batch.all_objects.filter(entity_id=batch_entity_id).exists()

        if already_exists and batch_entity_id not in force_batches:
            batches_to_skip.append(
                GriftSkippedBatch(batch_entity_id=batch_entity_id, path=batch_path, reason="batch_already_imported")
            )
        elif already_exists and batch_entity_id in force_batches:
            # Force re-import: skip the guard and include this batch in
            # batches_to_import. Execution-time code distinguishes force re-imports
            # by checking whether a Batch row already exists.
            batches_to_import.append((batch_idx, batch_container))
        elif Entity.objects.filter(pk=uuid.UUID(batch_entity_id)).exclude(entity_type="batch").exists():
            issues.append(
                _issue(
                    "entity_type_mismatch",
                    f"entity_id '{batch_entity_id}' exists locally but is not a batch",
                    "preflight",
                    f"{batch_path}.batch_entity.entity_id",
                    entity_id=batch_entity_id,
                    batch_entity_id=batch_entity_id,
                )
            )
        else:
            batches_to_import.append((batch_idx, batch_container))

    # --- Dangling edge resolution ---
    # Only check batches we'll actually import.
    for batch_idx, batch_container in batches_to_import:
        batch_path = f"$.batches[{batch_idx}]"
        batch_entity_id = batch_container["batch_entity"]["entity_id"]

        for edge_idx, edge_obj in enumerate(batch_container.get("edges", [])):
            edge_path = f"{batch_path}.edges[{edge_idx}]"
            edge = edge_obj.get("edge", {})
            edge_entity_id = edge_obj.get("entity", {}).get("entity_id")

            if not isinstance(edge, dict):
                continue

            from_id = edge.get("from_entity_id")
            to_id = edge.get("to_entity_id")
            is_dangling = False

            for endpoint_id, field_name in ((from_id, "from_entity_id"), (to_id, "to_entity_id")):
                if not endpoint_id:
                    continue
                # Resolve against: (1) in-file node ids, (2) existing grid entities.
                if endpoint_id not in file_node_ids:
                    try:
                        exists = Entity.objects.filter(pk=uuid.UUID(endpoint_id)).exists()
                    except ValueError, TypeError:
                        exists = False

                    if not exists:
                        is_dangling = True
                        if dangling_edge_mode == "strict":
                            issues.append(
                                _issue(
                                    "dangling_edge",
                                    f"Edge endpoint {field_name}='{endpoint_id}' not found in file or grid",
                                    "preflight",
                                    f"{edge_path}.edge.{field_name}",
                                    entity_id=edge_entity_id,
                                    batch_entity_id=batch_entity_id,
                                    from_entity_id=from_id,
                                    to_entity_id=to_id,
                                    edge_entity_id=edge_entity_id,
                                )
                            )
                        else:
                            if edge_entity_id:
                                dangling_edge_ids.add(edge_entity_id)

            if is_dangling and dangling_edge_mode == "permissive" and edge_entity_id:
                dangling_edge_ids.add(edge_entity_id)

    # --- Identity sanity: entity_type consistency for existing entities ---
    # For each node/edge being imported, if it already exists in the grid its
    # entity_type must match what the GRIFT file declares.  One bulk query covers
    # all batches to import; invalid UUIDs are skipped (already flagged above).
    grift_types: dict[str, tuple[str, str, str | None]] = {}  # normalized_id -> (type, path, batch_eid)
    for batch_idx_s, batch_container_s in batches_to_import:
        batch_path_s = f"$.batches[{batch_idx_s}]"
        batch_eid_s = batch_container_s["batch_entity"]["entity_id"]
        for node_idx_s, node_obj_s in enumerate(batch_container_s.get("nodes", [])):
            raw_eid = node_obj_s.get("entity", {}).get("entity_id")
            raw_type = node_obj_s.get("entity", {}).get("entity_type", "")
            if raw_eid and raw_type:
                try:
                    grift_types[str(uuid.UUID(raw_eid))] = (
                        raw_type,
                        f"{batch_path_s}.nodes[{node_idx_s}].entity.entity_type",
                        batch_eid_s,
                    )
                except ValueError, AttributeError:
                    pass
        for edge_idx_s, edge_obj_s in enumerate(batch_container_s.get("edges", [])):
            raw_eid = edge_obj_s.get("entity", {}).get("entity_id")
            if raw_eid:
                try:
                    grift_types[str(uuid.UUID(raw_eid))] = (
                        "edge",
                        f"{batch_path_s}.edges[{edge_idx_s}].entity.entity_type",
                        batch_eid_s,
                    )
                except ValueError, AttributeError:
                    pass

    if grift_types:
        for entity_uuid, grid_type in Entity.objects.filter(pk__in=[uuid.UUID(eid) for eid in grift_types]).values_list(
            "id", "entity_type"
        ):
            norm = str(entity_uuid)
            if norm not in grift_types:
                continue
            grift_type, sanity_path, batch_eid_s = grift_types[norm]
            if grift_type != grid_type:
                issues.append(
                    _issue(
                        "entity_type_mismatch",
                        f"Entity {norm} exists in grid as '{grid_type}' but GRIFT declares '{grift_type}'",
                        "preflight",
                        sanity_path,
                        entity_id=norm,
                        batch_entity_id=batch_eid_s,
                        entity_type=grift_type,
                    )
                )

    # Decide overall ok: any hard-error issue means preflight failed.
    has_hard_error = any(i.code in _ERROR_CODES for i in issues)
    ok = not has_hard_error

    return _PreflightResult(
        ok=ok,
        batches_to_import=batches_to_import,
        batches_to_skip=batches_to_skip,
        dangling_edge_ids=dangling_edge_ids,
        issues=issues,
    )


# ---------------------------------------------------------------------------
# Batch execution
# ---------------------------------------------------------------------------


class _BatchFailed(Exception):
    """Raised inside _execute_grift_batch to trigger atomic rollback."""


class _SweepStrictAborted(Exception):
    """Raised inside _execute_grift_batch when --sweep-strict + a guardrail miss."""


def _execute_grift_batch(
    batch_container: dict[str, Any],
    *,
    batch_idx: int,
    dangling_edge_ids: set[str],
    actor: Any,
    reference_time: datetime,
    dangling_edge_mode: str,
    force_batches: set[str] | None = None,
    sweep_strict: bool = False,
    purge: bool = False,
) -> tuple[GriftImportedBatch, list[GriftIssue]]:
    """Import one GRIFT batch atomically. Returns (batch_summary, issues)."""
    from tap_grid.models import Batch

    batch_path = f"$.batches[{batch_idx}]"
    issues: list[GriftIssue] = []
    nodes_imported = 0
    edges_imported = 0
    edges_skipped = 0
    swept_entities: list[GriftSweptEntity] = []
    sweep_skipped: list[GriftSweepSkipped] = []
    sweep_strict_aborted = False
    upserted_entities: list[GriftUpsertedEntity] = []

    batch_entity = batch_container["batch_entity"]
    batch_node = batch_container["batch_node"]
    batch_entity_id = batch_entity["entity_id"]
    force_batches = force_batches or set()
    is_force_reimport = batch_entity_id in force_batches and Batch.all_objects.filter(
        entity_id=batch_entity_id
    ).exists()

    # Build importer provenance for description_json.
    importer_data: dict[str, Any] = {
        "importer": "grift",
        "grift_version": GRIFT_VERSION,
        "import_mode": IMPORT_MODE,
        "dangling_edge_mode": dangling_edge_mode,
        "imported_at": reference_time.isoformat(),
        "source_batch_entity_id": batch_entity_id,
    }
    for src_key, dest_key in (
        ("created_at", "source_created_at"),
        ("updated_at", "source_updated_at"),
    ):
        if batch_entity.get(src_key):
            importer_data[dest_key] = batch_entity[src_key]
    for src_key, dest_key in (
        ("started_at", "source_started_at"),
        ("closed_at", "source_closed_at"),
    ):
        if batch_node.get(src_key):
            importer_data[dest_key] = batch_node[src_key]

    # Merge importer metadata into description_json per spec-grid-import-grift
    # req-grid-import-grift-provenance. Four cases:
    #   1. incoming missing/empty/malformed -> emit importer format alone
    #   2. incoming already tap.grift.import.v0 -> overwrite (avoid nested duplicates)
    #   3. incoming has a custom format with dict data -> preserve caller format and
    #      nest importer metadata under reserved key `_tap_grift_import` to avoid
    #      key collisions with caller-owned data
    #   4. incoming has a format but data shape is wrong -> fall back to case 1
    incoming_desc = batch_node.get("description_json") or {}
    merged_desc_json: dict[str, Any]
    if not isinstance(incoming_desc, dict) or not incoming_desc:
        merged_desc_json = {"format": "tap.grift.import.v0", "data": importer_data}
    elif incoming_desc.get("format") == "tap.grift.import.v0":
        merged_desc_json = {"format": "tap.grift.import.v0", "data": importer_data}
    elif isinstance(incoming_desc.get("format"), str) and isinstance(
        incoming_desc.get("data"), dict
    ):
        merged_data = {**incoming_desc["data"], "_tap_grift_import": importer_data}
        merged_desc_json = {"format": incoming_desc["format"], "data": merged_data}
    else:
        merged_desc_json = {"format": "tap.grift.import.v0", "data": importer_data}

    try:
        with transaction.atomic():
            if is_force_reimport:
                # req-grid-import-grift-force-reimport: re-apply the existing
                # batch's content in place. The Batch row and its Entity already
                # exist; don't call create_batch (which would collide). We may
                # refresh batch metadata (name, description) to reflect the
                # revised content, but the identity stays fixed.
                batch = Batch.all_objects.get(entity_id=batch_entity_id)
                new_name = batch_node.get("name") or batch_entity.get("name") or batch.name
                new_description = batch_node.get("description") or batch.description
                if new_name != batch.name or new_description != batch.description:
                    batch.name = new_name
                    batch.description = new_description
                    batch.save(update_fields=["name", "description"])
                # If the batch was previously closed, reopen-then-reclose on
                # success. Status is managed by close_batch at the bottom.
                from tap_grid.models import BatchStatus

                if batch.status != BatchStatus.OPEN:
                    batch.status = BatchStatus.OPEN
                    batch.closed_at = None
                    batch.save(update_fields=["status", "closed_at"])
            else:
                # Normal path: create the batch with the preserved entity_id.
                batch = create_batch(
                    entity_id=batch_entity_id,
                    name=batch_node.get("name") or batch_entity.get("name") or "",
                    source=batch_node.get("source") or "",
                    description=batch_node.get("description") or "",
                    description_json=merged_desc_json,
                    metadata=batch_node.get("metadata") or {},
                    actor=actor,
                )

            ctx = CallerContext(user=actor, batch_id=batch_entity_id)

            # Build operations: determine create vs replace per entity before executing.
            ops: list[WriteOperation] = []
            op_meta: list[dict[str, Any]] = []  # parallel metadata for error reporting
            # Spine-sync intents for existing-entity replaces: the service-layer
            # replace verb leaves Entity spine fields untouched (per its docstring),
            # but on re-import the bundle's envelope is authoritative for spine
            # values. We capture the bundle's envelope-side `name` and `dimensions`
            # for every replace_node target and apply them in a post-pass after
            # the batch succeeds. See req-grid-import-grift-batch (Spine Sync).
            replace_spine_intents: list[dict[str, Any]] = []

            for node_idx, node_obj in enumerate(batch_container.get("nodes", [])):
                node_entity_id = node_obj["entity"]["entity_id"]
                entity_type = node_obj["entity"]["entity_type"]
                envelope_name = node_obj["entity"].get("name")
                envelope_dims = node_obj["entity"].get("dimensions") or {}
                payload = node_obj["node"]
                node_path = f"{batch_path}.nodes[{node_idx}]"

                if Entity.objects.filter(pk=uuid.UUID(node_entity_id)).exists():
                    ops.append(WriteOperation(verb="replace_node", target=node_entity_id, payload=payload))
                    replace_spine_intents.append(
                        {
                            "entity_id": node_entity_id,
                            "envelope_name": envelope_name,
                            "envelope_dims": envelope_dims,
                        }
                    )
                    upserted_entities.append(
                        GriftUpsertedEntity(
                            entity_id=node_entity_id,
                            entity_type=entity_type,
                            name=envelope_name,
                            kind="node",
                        )
                    )
                else:
                    ops.append(
                        WriteOperation(
                            verb="create_node",
                            type_slug=entity_type,
                            payload=payload,
                            entity_id=node_entity_id,
                            dimensions=envelope_dims,
                        )
                    )
                op_meta.append(
                    {"path": node_path, "entity_id": node_entity_id, "entity_type": entity_type, "kind": "node"}
                )

            for edge_idx, edge_obj in enumerate(batch_container.get("edges", [])):
                edge_entity_id = edge_obj["entity"]["entity_id"]
                edge = edge_obj["edge"]
                envelope_dims = edge_obj["entity"].get("dimensions") or {}
                edge_path = f"{batch_path}.edges[{edge_idx}]"

                if edge_entity_id in dangling_edge_ids:
                    edges_skipped += 1
                    issues.append(
                        _issue(
                            "dangling_edge",
                            f"Skipping dangling edge {edge_entity_id} (permissive mode)",
                            "execution",
                            edge_path,
                            entity_id=edge_entity_id,
                            batch_entity_id=batch_entity_id,
                            entity_type="edge",
                            operation="skip",
                            from_entity_id=edge.get("from_entity_id"),
                            to_entity_id=edge.get("to_entity_id"),
                            edge_entity_id=edge_entity_id,
                        )
                    )
                    continue

                properties = edge.get("properties") or {}
                if Entity.objects.filter(pk=uuid.UUID(edge_entity_id)).exists():
                    ops.append(
                        WriteOperation(verb="replace_edge", target=edge_entity_id, payload={"properties": properties})
                    )
                    upserted_entities.append(
                        GriftUpsertedEntity(
                            entity_id=edge_entity_id,
                            entity_type="edge",
                            name=edge_obj["entity"].get("name"),
                            kind="edge",
                        )
                    )
                else:
                    ops.append(
                        WriteOperation(
                            verb="create_edge",
                            from_target=edge["from_entity_id"],
                            to_target=edge["to_entity_id"],
                            edge_type=edge["edge_type"],
                            payload={"properties": properties},
                            entity_id=edge_entity_id,
                            dimensions=envelope_dims,
                        )
                    )
                op_meta.append({"path": edge_path, "entity_id": edge_entity_id, "entity_type": "edge", "kind": "edge"})

            # Execute all node + edge ops in one write_batch call (atomic).
            if ops:
                batch_result = write_batch(ops, caller_context=ctx)
                for op_result, meta in zip(batch_result.results, op_meta):
                    if op_result.success:
                        if meta["kind"] == "node":
                            nodes_imported += 1
                        else:
                            edges_imported += 1
                    else:
                        for err in op_result.errors:
                            issues.append(
                                _issue(
                                    "execution_failed",
                                    f"{err.code}: {err.message}",
                                    "execution",
                                    meta["path"],
                                    entity_id=meta["entity_id"],
                                    batch_entity_id=batch_entity_id,
                                    entity_type=meta["entity_type"],
                                    operation=op_result.operation,
                                )
                            )
                        raise _BatchFailed()

                # req-grid-import-grift-batch (Spine Sync): for every successful
                # replace_node, propagate the bundle's envelope-side spine fields
                # (name, dimensions) to the Entity row when they differ. The
                # service-layer replace verb intentionally leaves spine fields
                # alone, but the GRIFT envelope is the bundle's declared truth on
                # every import — so on re-import a renamed or re-dimensioned
                # entity's spine must move with it. Direct Entity.objects.update
                # is used (not save()) to avoid bumping version on a pure spine
                # sync and to keep this post-pass cheap.
                if replace_spine_intents:
                    _sync_spine_for_replaced_nodes(replace_spine_intents)

            # req-grid-import-grift-batch-scoped-sweep: on force re-import,
            # detect entities the previous ingestion of this batch created
            # that are absent in the revised content, and tombstone (or purge)
            # them via the service-layer delete path. Runs inside the
            # transaction so a strict-mode abort rolls everything back.
            if is_force_reimport:
                swept_entities, sweep_skipped = _run_batch_scoped_sweep(
                    batch_entity_id=batch_entity_id,
                    batch_container=batch_container,
                    caller_ctx=ctx,
                    sweep_strict=sweep_strict,
                    purge=purge,
                )
                # Emit the FORCE_REIMPORT batch event.
                _emit_force_reimport_event(
                    batch=batch,
                    nodes_imported=nodes_imported,
                    edges_imported=edges_imported,
                    edges_skipped=edges_skipped,
                    swept_entities=swept_entities,
                    sweep_skipped=sweep_skipped,
                    purge=purge,
                    sweep_strict=sweep_strict,
                    actor=actor,
                )

            close_batch(batch)

    except _BatchFailed:
        # Atomic block already rolled back; clear upsert tracking since none
        # of those replaces actually persisted.
        upserted_entities = []
    except _SweepStrictAborted as exc:
        # Strict mode: surface an error and keep the skipped list for the report.
        sweep_strict_aborted = True
        # exc.args[0] carries the list of skipped candidates assembled by
        # _run_batch_scoped_sweep before it raised.
        if exc.args and isinstance(exc.args[0], list):
            sweep_skipped = exc.args[0]
        # Any writes made in this atomic block rolled back with the exception.
        nodes_imported = 0
        edges_imported = 0
        edges_skipped = 0
        swept_entities = []
        upserted_entities = []
        issues.append(
            _issue(
                "sweep_strict_aborted",
                f"Strict sweep aborted: {len(sweep_skipped)} candidate(s) failed guardrails.",
                "execution",
                batch_path,
                batch_entity_id=batch_entity_id,
            )
        )
    except Exception as exc:
        issues.append(_issue("execution_failed", str(exc), "execution", batch_path, batch_entity_id=batch_entity_id))

    errors_count = sum(1 for i in issues if i.code in ("execution_failed", "sweep_strict_aborted"))
    warnings_count = sum(1 for i in issues if i.code == "dangling_edge")

    return (
        GriftImportedBatch(
            batch_entity_id=batch_entity_id,
            path=batch_path,
            nodes_imported=nodes_imported,
            edges_imported=edges_imported,
            edges_skipped=edges_skipped,
            errors_count=errors_count,
            warnings_count=warnings_count,
            force_reimported=is_force_reimport,
            swept_entities=swept_entities,
            sweep_skipped=sweep_skipped,
            sweep_strict_aborted=sweep_strict_aborted,
            upserted_entities=upserted_entities,
        ),
        issues,
    )


# ---------------------------------------------------------------------------
# Spine-field sync for replaced nodes (req-grid-import-grift-batch / Spine Sync)
# ---------------------------------------------------------------------------


def _sync_spine_for_replaced_nodes(replace_intents: list[dict[str, Any]]) -> None:
    """Propagate envelope-side spine fields onto existing Entity rows.

    For each intent in ``replace_intents`` (the bundle's envelope `name` and
    `dimensions` for an entity that already existed at import time), update
    the Entity row in-place when the persisted value differs from the
    bundle's declaration. This makes the GRIFT envelope authoritative for
    spine values on every import — the service-layer ``replace_node`` verb
    deliberately leaves spine fields untouched, so without this post-pass a
    renamed or re-dimensioned entity in a re-imported bundle would silently
    drift between model-side ``name`` and spine-side ``Entity.name``.

    Uses ``Entity.objects.filter(...).update(...)`` rather than ``save()`` so
    a pure spine sync does not bump the entity's version counter (the version
    field tracks logical, model-level mutations) and to keep the post-pass
    cheap. ``updated_at`` is bumped explicitly to reflect that something on
    the row did change.
    """
    if not replace_intents:
        return

    now = timezone.now()
    for intent in replace_intents:
        entity_uuid = uuid.UUID(intent["entity_id"])
        envelope_name = intent.get("envelope_name")
        envelope_dims = intent.get("envelope_dims") or {}

        # Read the persisted spine values to decide whether anything needs to
        # change. A no-op update should not bump updated_at.
        try:
            persisted = Entity.objects.values("name", "dimensions").get(pk=entity_uuid)
        except Entity.DoesNotExist:
            continue

        update_fields: dict[str, Any] = {}
        if envelope_name is not None and envelope_name != persisted["name"]:
            update_fields["name"] = envelope_name
        if envelope_dims and envelope_dims != (persisted["dimensions"] or {}):
            update_fields["dimensions"] = envelope_dims

        if update_fields:
            update_fields["updated_at"] = now
            Entity.objects.filter(pk=entity_uuid).update(**update_fields)


# ---------------------------------------------------------------------------
# Batch-scoped sweep (req-grid-import-grift-batch-scoped-sweep / sweep-purge)
# ---------------------------------------------------------------------------


def _run_batch_scoped_sweep(
    *,
    batch_entity_id: str,
    batch_container: dict[str, Any],
    caller_ctx: CallerContext,
    sweep_strict: bool,
    purge: bool,
) -> tuple[list[GriftSweptEntity], list[GriftSweepSkipped]]:
    """Detect and remove entities the prior version of this batch created that
    are absent in the revised content. Returns (swept_entities, sweep_skipped).

    Raises ``_SweepStrictAborted`` with the skipped-candidate list if
    ``sweep_strict`` is set and any candidate fails a guardrail. The
    enclosing transaction rolls back, undoing all upserts applied by the
    revised batch.

    Guardrails:
      A. Ownership — no BatchEvent exists for this entity with a different
         batch_id. If another batch has written to the entity, skip it.
      B. Referential integrity — no edge survives the sweep referencing the
         candidate in either direction. An edge survives the sweep if it
         exists and is not itself being swept, or if the revised batch's new
         edge list points at the candidate.

    If ``purge`` is set, surviving candidates are hard-deleted along with
    their batch-scoped BatchEvent rows and domain-model history. Default is
    tombstone via service-layer delete.
    """
    from django.db.models import Q

    from tap_grid.models import BatchEvent, BatchEventType, Edge, Entity

    # --- Build the new-version id sets (post-apply state). ---
    new_node_ids: set[str] = {
        n["entity"]["entity_id"] for n in batch_container.get("nodes", [])
    }
    new_edge_ids: set[str] = {
        e["entity"]["entity_id"] for e in batch_container.get("edges", [])
    }
    new_edge_endpoints: list[tuple[str, str]] = [
        (e["edge"]["from_entity_id"], e["edge"]["to_entity_id"])
        for e in batch_container.get("edges", [])
    ]

    # --- Candidates: entities this batch CREATEd that are absent from the new sets. ---
    create_events = BatchEvent.objects.filter(
        batch__entity_id=batch_entity_id,
        event_type=BatchEventType.CREATE,
    ).values("entity_id", "entity_type")

    candidate_entity_ids: list[tuple[str, str]] = []  # (entity_id, entity_type)
    swept_node_ids: set[str] = set()
    swept_edge_ids: set[str] = set()
    for ev in create_events:
        eid = str(ev["entity_id"])
        etype = ev["entity_type"]
        if etype == "edge" and eid not in new_edge_ids:
            candidate_entity_ids.append((eid, etype))
            swept_edge_ids.add(eid)
        elif etype != "edge" and eid not in new_node_ids:
            candidate_entity_ids.append((eid, etype))
            swept_node_ids.add(eid)

    if not candidate_entity_ids:
        return [], []

    swept: list[GriftSweptEntity] = []
    skipped: list[GriftSweepSkipped] = []
    cleared: list[tuple[str, str]] = []  # candidates that passed both guardrails

    # --- Evaluate guardrails per candidate. ---
    for entity_id_str, entity_type in candidate_entity_ids:
        # Guardrail A — ownership. Any event for this entity from a different batch?
        external_writes_exist = (
            BatchEvent.objects.filter(entity_id=entity_id_str)
            .exclude(batch__entity_id=batch_entity_id)
            .exists()
        )
        if external_writes_exist:
            skipped.append(
                GriftSweepSkipped(
                    entity_id=entity_id_str,
                    entity_type=entity_type,
                    reason="sweep_skipped_external_write",
                )
            )
            continue

        # Guardrail B — referential integrity (node candidates only).
        # For an edge candidate, Guardrail B is implicit: the edge itself is
        # being swept, so edges-referencing-edges doesn't apply (TAP's edge
        # model rejects edge-as-endpoint). So we only check for nodes.
        if entity_type != "edge":
            candidate_uuid = uuid.UUID(entity_id_str)
            # Existing edges that touch this node AND are not being swept.
            surviving_existing = (
                Edge.all_objects.filter(Q(from_entity_id=candidate_uuid) | Q(to_entity_id=candidate_uuid))
                .filter(entity__deleted_at__isnull=True)
                .exclude(entity_id__in=[uuid.UUID(e) for e in swept_edge_ids])
            )
            if surviving_existing.exists():
                skipped.append(
                    GriftSweepSkipped(
                        entity_id=entity_id_str,
                        entity_type=entity_type,
                        reason="sweep_skipped_referenced",
                    )
                )
                continue

            # New-version edges that point at this candidate.
            touched_by_new = any(
                entity_id_str in (from_id, to_id) for from_id, to_id in new_edge_endpoints
            )
            if touched_by_new:
                skipped.append(
                    GriftSweepSkipped(
                        entity_id=entity_id_str,
                        entity_type=entity_type,
                        reason="sweep_skipped_referenced",
                    )
                )
                continue

        cleared.append((entity_id_str, entity_type))

    # --- Strict-mode abort: any skip cancels the entire force re-import. ---
    if sweep_strict and skipped:
        raise _SweepStrictAborted(skipped)

    # --- Apply deletions. ---
    if purge:
        swept = _apply_sweep_purge(cleared, batch_entity_id)
    else:
        swept = _apply_sweep_tombstone(cleared, caller_ctx)

    return swept, skipped


def _apply_sweep_tombstone(
    cleared: list[tuple[str, str]],
    caller_ctx: CallerContext,
) -> list[GriftSweptEntity]:
    """Tombstone each cleared candidate via the service-layer delete path.

    Routes through ``write_batch`` so tombstone cascade (to connected edges)
    and batch-scoped provenance both fire via the standard pipeline.
    """
    from tap_grid.service_types import WriteOperation
    from tap_grid.services import write_batch

    ops: list[WriteOperation] = []
    for eid, etype in cleared:
        verb = "delete_edge" if etype == "edge" else "delete_node"
        ops.append(WriteOperation(verb=verb, target=eid))
    if ops:
        write_batch(ops, caller_context=caller_ctx)

    return [
        GriftSweptEntity(
            entity_id=eid,
            entity_type=etype,
            action="tombstone",
            reason="orphaned",
        )
        for eid, etype in cleared
    ]


def _apply_sweep_purge(
    cleared: list[tuple[str, str]],
    batch_entity_id: str,
) -> list[GriftSweptEntity]:
    """Hard-delete each cleared candidate along with this batch's BatchEvent
    rows and any domain-model history tied to the candidate.

    Guardrail A guarantees the only history rows/events to delete are this
    batch's own; if that assumption ever fails mid-run, we abort loudly
    rather than touch anything we shouldn't.
    """
    from tap_grid.models import BatchEvent, Edge, Entity
    from tap_grid.registry import get_model_class

    swept: list[GriftSweptEntity] = []

    for entity_id_str, entity_type in cleared:
        candidate_uuid = uuid.UUID(entity_id_str)

        # Verify Guardrail A one last time: no events with a foreign batch_id.
        # If one appears here, we raise; the enclosing transaction rolls back
        # the whole force re-import (including any prior purges in this run).
        foreign_events = (
            BatchEvent.objects.filter(entity_id=candidate_uuid)
            .exclude(batch__entity_id=batch_entity_id)
            .exists()
        )
        if foreign_events:
            raise RuntimeError(
                f"Purge integrity check failed for {entity_id_str}: foreign-batch events found. "
                "Aborting the entire force re-import."
            )

        # Hard-delete this batch's events for the entity.
        BatchEvent.objects.filter(
            entity_id=candidate_uuid,
            batch__entity_id=batch_entity_id,
        ).delete()

        # Hard-delete domain-model history rows for the entity, if the entity
        # type has a registered model class with a HistoricalRecords manager.
        if entity_type != "edge":
            try:
                model_cls = get_model_class(entity_type)
            except KeyError:
                model_cls = None
            if model_cls is not None and hasattr(model_cls, "history"):
                model_cls.history.filter(entity_id=candidate_uuid).delete()

        # For node entities, cascade-hard-delete attached edges (the domain
        # Edge rows, their BaseModel history, and their own Entity spines).
        if entity_type != "edge":
            from django.db.models import Q as _Q

            attached_edges = list(
                Edge.all_objects.filter(
                    _Q(from_entity_id=candidate_uuid) | _Q(to_entity_id=candidate_uuid)
                ).values_list("entity_id", flat=True)
            )
            if attached_edges:
                # Edge history rows are on the Edge model.
                Edge.history.filter(entity_id__in=attached_edges).delete()
                BatchEvent.objects.filter(
                    entity_id__in=attached_edges,
                    batch__entity_id=batch_entity_id,
                ).delete()
                # Deleting the edge's Entity spine cascades the Edge row via
                # the OneToOneField(on_delete=CASCADE) on BaseModel.
                Entity.objects.filter(pk__in=attached_edges).delete()

        # Finally, hard-delete the candidate Entity itself. For edge candidates,
        # this removes the Edge row and its history via cascade; for node
        # candidates, this removes the domain row + anything else referencing
        # the Entity.
        if entity_type == "edge":
            Edge.history.filter(entity_id=candidate_uuid).delete()
        Entity.objects.filter(pk=candidate_uuid).delete()

        swept.append(
            GriftSweptEntity(
                entity_id=entity_id_str,
                entity_type=entity_type,
                action="purge",
                reason="orphaned",
            )
        )

    return swept


def _emit_force_reimport_event(
    *,
    batch: Any,
    nodes_imported: int,
    edges_imported: int,
    edges_skipped: int,
    swept_entities: list[GriftSweptEntity],
    sweep_skipped: list[GriftSweepSkipped],
    purge: bool,
    sweep_strict: bool,
    actor: Any,
) -> None:
    """Emit the FORCE_REIMPORT BatchEvent so the audit trail reads as
    'initial ingest → force re-import(s) → further activity'.
    """
    from tap_grid.models import BatchEvent, BatchEventType

    BatchEvent.objects.create(
        batch=batch,
        event_type=BatchEventType.FORCE_REIMPORT,
        entity_id=batch.entity_id,
        entity_type="batch",
        actor=actor,
        metadata={
            "nodes_imported": nodes_imported,
            "edges_imported": edges_imported,
            "edges_skipped": edges_skipped,
            "entities_swept": len(swept_entities),
            "entities_purged": sum(1 for s in swept_entities if s.action == "purge"),
            "sweep_skipped": len(sweep_skipped),
            "purge": purge,
            "sweep_strict": sweep_strict,
            "swept_entity_ids": [s.entity_id for s in swept_entities],
            "sweep_skipped_reasons": {
                s.entity_id: s.reason for s in sweep_skipped
            },
        },
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def grift_import(
    document: dict[str, Any] | str | bytes,
    *,
    dangling_edge_mode: Literal["strict", "permissive"] = "strict",
    actor: Any = None,
    force_batches: list[str] | set[str] | None = None,
    sweep_strict: bool = False,
    purge: bool = False,
) -> GriftImportResult:
    """Import a GRIFT v0 document into the local TAP grid.

    Validates the full document before any mutation (preflight), then executes
    each batch atomically using upsert semantics (create if new, replace if
    present by entity_id).

    Args:
        document: GRIFT document as a parsed dict, JSON string, or bytes.
        dangling_edge_mode: "strict" fails preflight on any dangling edge;
            "permissive" skips only the offending edges and continues.
        actor: Optional User to record as the import actor.
        force_batches: Optional collection of batch_entity_id strings to
            force re-import (bypass the skip-if-exists guard). Permitted
            if and only if Django's DEBUG setting is True.
            See req-grid-import-grift-force-reimport.
        sweep_strict: If True, a force re-import aborts before any writes
            if any sweep candidate fails a guardrail. Only meaningful with
            force_batches. See req-grid-import-grift-batch-scoped-sweep.
        purge: If True, force re-import hard-deletes swept entities (and
            their batch-scoped history) instead of tombstoning. Permitted
            if and only if DEBUG=True. Only meaningful with force_batches.
            See req-grid-import-grift-sweep-purge.

    Returns:
        GriftImportResult describing every phase of the import.
    """
    from django.conf import settings

    reference_time = timezone.now()

    # Normalise force_batches to a set of strings.
    force_batches_set: set[str] = set(force_batches or [])

    # --purge only makes sense with force_batches; check this first so the
    # error surfaces consistently whether or not DEBUG is set.
    if purge and not force_batches_set:
        return GriftImportResult(
            success=False,
            grift_version="",
            import_mode=IMPORT_MODE,
            dangling_edge_mode=dangling_edge_mode,
            reference_time=reference_time.isoformat(),
            counts=GriftCounts(errors=1),
            imported_batches=[],
            skipped_batches=[],
            errors=[
                _issue(
                    "purge_requires_force_reimport",
                    "--purge requires --force-batches; no batches were named for force re-import.",
                    "preflight",
                    "$",
                )
            ],
            warnings=[],
        )

    # req-grid-import-grift-force-reimport env gate: permitted iff DEBUG=True.
    # There is no alternate flag, override, or settings key that enables it
    # in any other configuration. Refuse with a dedicated error code so the
    # operator sees exactly why it was rejected.
    if force_batches_set and not getattr(settings, "DEBUG", False):
        return GriftImportResult(
            success=False,
            grift_version="",
            import_mode=IMPORT_MODE,
            dangling_edge_mode=dangling_edge_mode,
            reference_time=reference_time.isoformat(),
            counts=GriftCounts(errors=1),
            imported_batches=[],
            skipped_batches=[],
            errors=[
                _issue(
                    "force_reimport_refused_production",
                    "Force re-import is permitted if and only if DEBUG=True. "
                    "Refusing the invocation.",
                    "preflight",
                    "$",
                )
            ],
            warnings=[],
        )
    # req-grid-import-grift-sweep-purge env gate: same invariant, applied
    # independently so --purge refusals are distinguishable.
    if purge and not getattr(settings, "DEBUG", False):
        return GriftImportResult(
            success=False,
            grift_version="",
            import_mode=IMPORT_MODE,
            dangling_edge_mode=dangling_edge_mode,
            reference_time=reference_time.isoformat(),
            counts=GriftCounts(errors=1),
            imported_batches=[],
            skipped_batches=[],
            errors=[
                _issue(
                    "sweep_purge_refused_production",
                    "--purge is permitted if and only if DEBUG=True. "
                    "Refusing the invocation.",
                    "preflight",
                    "$",
                )
            ],
            warnings=[],
        )

    # Parse JSON input.
    if isinstance(document, (str, bytes)):
        try:
            document = json.loads(document)
        except json.JSONDecodeError as exc:
            return GriftImportResult(
                success=False,
                grift_version="",
                import_mode=IMPORT_MODE,
                dangling_edge_mode=dangling_edge_mode,
                reference_time=reference_time.isoformat(),
                counts=GriftCounts(errors=1),
                imported_batches=[],
                skipped_batches=[],
                errors=[_issue("invalid_json", f"Invalid JSON: {exc}", "parse", "$")],
                warnings=[],
            )

    # Extract grift_version before full validation (best effort).
    grift_version = ""
    if isinstance(document, dict):
        meta = document.get("metadata", {})
        if isinstance(meta, dict):
            grift_version = str(meta.get("grift_version", ""))

    preflight = _run_preflight(
        document,
        reference_time=reference_time,
        dangling_edge_mode=dangling_edge_mode,
        force_batches=force_batches_set,
    )

    # If any named force_batches didn't resolve to an existing batch in the
    # file, surface that explicitly — silent no-op would be confusing.
    if force_batches_set:
        file_batch_ids = {
            (batch.get("batch_entity") or {}).get("entity_id")
            for batch in (document.get("batches") if isinstance(document, dict) else []) or []
        }
        file_batch_ids.discard(None)
        missing = force_batches_set - file_batch_ids
        for mb in sorted(missing):
            preflight.issues.append(
                _issue(
                    "force_reimport_batch_not_found",
                    f"Requested force re-import of batch '{mb}' which is not present in the document.",
                    "preflight",
                    "$.batches",
                    batch_entity_id=mb,
                )
            )
            preflight.ok = False

    # Separate preflight issues into errors and warnings.
    # In permissive mode, dangling_edge issues are warnings (they just get skipped).
    def _is_error(issue: GriftIssue) -> bool:
        if issue.code == "dangling_edge" and dangling_edge_mode == "permissive":
            return False
        return issue.code in _ERROR_CODES

    errors: list[GriftIssue] = [i for i in preflight.issues if _is_error(i)]
    warnings: list[GriftIssue] = [i for i in preflight.issues if not _is_error(i)]

    if not preflight.ok:
        return GriftImportResult(
            success=False,
            grift_version=grift_version,
            import_mode=IMPORT_MODE,
            dangling_edge_mode=dangling_edge_mode,
            reference_time=reference_time.isoformat(),
            counts=GriftCounts(
                batches_skipped=len(preflight.batches_to_skip), errors=len(errors), warnings=len(warnings)
            ),
            imported_batches=[],
            skipped_batches=preflight.batches_to_skip,
            errors=errors,
            warnings=warnings,
        )

    # Execute each batch.
    imported_batches: list[GriftImportedBatch] = []
    exec_issues: list[GriftIssue] = []

    for batch_idx, batch_container in preflight.batches_to_import:
        summary, batch_issues = _execute_grift_batch(
            batch_container,
            batch_idx=batch_idx,
            dangling_edge_ids=preflight.dangling_edge_ids,
            actor=actor,
            reference_time=reference_time,
            dangling_edge_mode=dangling_edge_mode,
            force_batches=force_batches_set,
            sweep_strict=sweep_strict,
            purge=purge,
        )
        imported_batches.append(summary)
        exec_issues.extend(batch_issues)

    exec_errors = [i for i in exec_issues if i.code in ("execution_failed", "sweep_strict_aborted")]
    exec_warnings = [i for i in exec_issues if i.code not in ("execution_failed", "sweep_strict_aborted")]

    all_errors = errors + exec_errors
    all_warnings = warnings + exec_warnings

    # Batches that executed successfully. A force re-import that aborted via
    # --sweep-strict is counted as a failure (nothing landed) but still has
    # an entry in imported_batches for reporting.
    successfully_imported = [
        b for b in imported_batches
        if not b.sweep_strict_aborted and b.errors_count == 0
    ]

    counts = GriftCounts(
        batches_imported=len(successfully_imported),
        batches_skipped=len(preflight.batches_to_skip),
        batches_force_reimported=sum(
            1 for b in successfully_imported if b.force_reimported
        ),
        nodes_imported=sum(b.nodes_imported for b in imported_batches),
        edges_imported=sum(b.edges_imported for b in imported_batches),
        edges_skipped=sum(b.edges_skipped for b in imported_batches),
        entities_swept=sum(len(b.swept_entities) for b in imported_batches),
        entities_purged=sum(
            sum(1 for s in b.swept_entities if s.action == "purge")
            for b in imported_batches
        ),
        sweep_skipped=sum(len(b.sweep_skipped) for b in imported_batches),
        entities_upserted=sum(len(b.upserted_entities) for b in imported_batches),
        errors=len(all_errors),
        warnings=len(all_warnings),
    )

    return GriftImportResult(
        success=len(all_errors) == 0,
        grift_version=grift_version,
        import_mode=IMPORT_MODE,
        dangling_edge_mode=dangling_edge_mode,
        reference_time=reference_time.isoformat(),
        counts=counts,
        imported_batches=imported_batches,
        skipped_batches=preflight.batches_to_skip,
        errors=all_errors,
        warnings=all_warnings,
    )
