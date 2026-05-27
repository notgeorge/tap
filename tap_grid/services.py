"""
TAP Core Services — canonical mutation API for entities and edges.

Public write API:
  write_batch()        — atomic multi-op batch with dry-run support
  create_node()        — create a typed domain object by slug
  patch_node()         — partial update (PATCH semantics)
  replace_node()       — full replacement (PUT semantics)
  delete_node()        — delete a node and its Entity spine
  create_edge()        — create an Edge between two entities (also the compat wrapper)
  patch_edge()         — partial update of edge properties
  replace_edge()       — full replacement of edge properties
  delete_edge()        — delete an edge (also the compat wrapper)

Backward-compatible low-level helpers (kept for existing callers):
  create_entity(), update_entity(), delete_entity(),
  update_edge_properties()
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

import jsonschema
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models as django_models
from django.db import transaction
from django.utils import timezone

from tap_grid.caller_context import (
    CallerContext,
    drain_deferred_hotlink_checks,
    get_caller_context,
    reset_deferred_hotlink_checks,
    set_caller_context,
    start_deferred_hotlink_checks,
)
from tap_grid.constraints import validate_edge as _validate_edge_constraint
from tap_grid.exceptions import (
    InvalidEdgeError,
    ServiceAuthzError,
    ServiceConflictError,
    ServiceConstraintError,
    ServiceNotFoundError,
    ServiceUnsupportedOperationError,
    ServiceValidationError,
    ServiceVersionConflictError,
)
from tap_grid.models import Edge, Entity
from tap_grid.service_types import (
    BatchWriteResult,
    EdgeTypeDescription,
    NodeTypeDescription,
    ServiceCapabilities,
    ServiceError,
    WriteOperation,
    WriteResult,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal sentinel for dry-run rollback
# ---------------------------------------------------------------------------


class _DryRunRollback(Exception):
    """Raised inside an atomic() block to force a rollback for dry-run mode."""


class _BailOut(Exception):
    """Raised when a pipeline operation fails, rolling back the entire batch."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _coerce_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    """Coerce a string UUID to uuid.UUID. Returns None if value is None."""
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _verb_to_schema_key(verb: str) -> str:
    """Map a write verb to its SERVICE_CRUD_SCHEMA key."""
    if verb in ("create_node", "create_edge"):
        return "create"
    if verb in ("patch_node", "patch_edge"):
        return "patch"
    if verb in ("replace_node", "replace_edge"):
        return "replace"
    raise ValueError(f"No schema key for verb '{verb}'")


def _deep_merge(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge update into base. update wins on conflict for scalars."""
    result = dict(base)
    for k, v in update.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _apply_patch(instance: Any, payload: dict[str, Any]) -> None:
    """Apply patch payload to an instance. JSONFields deep-merge; scalars replace."""
    for field_name, value in payload.items():
        try:
            model_field = instance._meta.get_field(field_name)
            is_json = isinstance(model_field, django_models.JSONField)
        except Exception:
            is_json = False

        if is_json:
            existing = getattr(instance, field_name) or {}
            setattr(instance, field_name, _deep_merge(existing, value))
        else:
            setattr(instance, field_name, value)


def _apply_replace(instance: Any, payload: dict[str, Any], model_cls: type) -> None:
    """Apply replace payload to an instance.

    Sets every field listed in SERVICE_CRUD_SCHEMA["replace"]["properties"] to
    the payload value. Missing optional fields are reset to model defaults.
    """
    schema_props = model_cls.SERVICE_CRUD_SCHEMA.get("replace", {}).get("properties", {})
    for field_name in schema_props:
        if field_name in payload:
            setattr(instance, field_name, payload[field_name])
        else:
            # Reset to model field default for optional fields absent from payload.
            try:
                model_field = instance._meta.get_field(field_name)
                default = model_field.default
                if default is not django_models.fields.NOT_PROVIDED:
                    value = default() if callable(default) else default
                else:
                    value = "" if isinstance(model_field, (django_models.CharField, django_models.TextField)) else None
                setattr(instance, field_name, value)
            except Exception:
                pass


def _django_errors_to_service_errors(exc: DjangoValidationError) -> list[ServiceError]:
    """Convert a Django ValidationError into a list of ServiceError instances."""
    errors: list[ServiceError] = []
    try:
        for field_name, messages in exc.message_dict.items():
            for msg in messages:
                errors.append(
                    ServiceError(
                        code="validation_error", message=str(msg), field=field_name if field_name != "__all__" else None
                    )
                )
    except AttributeError:
        for msg in exc.messages:
            errors.append(ServiceError(code="validation_error", message=str(msg)))
    return errors


def _load_entity_or_raise(entity_id: uuid.UUID) -> Entity:
    """Load an Entity by PK or raise ServiceNotFoundError."""
    try:
        return Entity.objects.get(pk=entity_id)
    except Entity.DoesNotExist as exc:
        raise ServiceNotFoundError(f"Entity {entity_id} not found.") from exc


def _build_object_summary(instance: Any) -> dict[str, Any]:
    """Build a minimal object summary for standard/verbose result modes."""
    entity = getattr(instance, "entity", None)
    return {
        "entity_id": str(instance.entity_id) if hasattr(instance, "entity_id") else None,
        "entity_type": entity.entity_type if entity else None,
        "name": entity.name if entity else None,
    }


def _record_provenance(verb: str, entity: Entity, batch_id: str, user: Any) -> None:
    """Record a BatchEvent for the completed operation (best-effort)."""
    from tap_grid.batch import record_batch_event

    event_map = {
        "create_node": "create",
        "patch_node": "update",
        "replace_node": "update",
        "delete_node": "delete",
        "create_edge": "link",
        "patch_edge": "update",
        "replace_edge": "update",
        "delete_edge": "unlink",
    }
    event_type = event_map.get(verb, "update")
    record_batch_event(
        entity=entity,
        event_type=event_type,
        model_name=type(entity).__name__ if verb not in ("delete_node", "delete_edge") else "",
        actor=user,
        batch_id=batch_id,
    )


def _ensure_batch(batch_id: str, user: Any) -> None:
    """Auto-create a Batch entity for batch_id if one does not already exist.

    Called before the main transaction so the Batch row is visible to
    record_batch_event() which looks it up by entity_id=batch_id.
    """
    from tap_grid.models import Batch

    if Batch.objects.filter(entity_id=batch_id).exists():
        return

    # Create the backing Entity with the pre-determined batch_id as its PK.
    entity = Entity.objects.create(
        id=uuid.UUID(batch_id),
        entity_type="batch",
        name=f"Batch {batch_id[:8]}",
    )
    Batch.objects.create(
        entity=entity,
        actor=user,
    )


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------


def _execute_write_pipeline(
    op: WriteOperation,
    *,
    batch_id: str,
    user: Any,
    result_mode: Literal["minimal", "standard", "verbose"],
    internal_only_bypass: bool = False,
) -> WriteResult:
    """Execute the write pipeline for a single WriteOperation.

    Returns a WriteResult. Never raises — errors are captured inside the result.

    When `internal_only_bypass=True`, the pipeline does not reject INTERNAL_ONLY
    model types. This flag is for trusted-internal callers (registration
    helpers, lifecycle managers); it is not part of the public write API. See
    `_create_node_internal` / `_patch_node_internal` in this module.
    """
    payload: dict[str, Any] = {k: v for k, v in (op.payload or {}).items() if v is not None}

    try:
        # Step 2: Security/authz stub (reserved; logs identity at DEBUG).
        logger.debug("[35dc] write_pipeline verb=%s user=%s batch=%s", op.verb, user, batch_id)

        # Step 3: Object load and resolution.
        from tap_grid.registry import get_model_class

        is_create = op.verb in ("create_node", "create_edge")
        is_delete = op.verb in ("delete_node", "delete_edge")

        # OCC pre-check: reject `entity_expected_version` on create verbs.
        # No prior version exists to expect, so this is always a caller mistake.
        # (req-grid-service-batch-occ-4 / req-grid-service-write-occ-2.)
        if is_create and op.entity_expected_version is not None:
            return WriteResult(
                success=False,
                batch_id=batch_id,
                operation=op.verb,
                errors=[
                    ServiceError(
                        code="entity_expected_version_not_allowed_on_create",
                        message=(
                            f"{op.verb} does not accept entity_expected_version; "
                            "no prior version exists on a create."
                        ),
                    )
                ],
            )

        model_cls: type
        instance: Any
        from_entity: Entity | None = None
        to_entity: Entity | None = None
        target_uuid = _coerce_uuid(op.target)

        if op.verb == "create_node":
            if not op.type_slug:
                raise ServiceValidationError("type_slug is required for create_node.")
            try:
                model_cls = get_model_class(op.type_slug)
            except KeyError as exc:
                raise ServiceNotFoundError(f"Unknown entity type: '{op.type_slug}'.") from exc
            if getattr(model_cls, "INTERNAL_ONLY", False) and not internal_only_bypass:
                raise ServiceUnsupportedOperationError(
                    f"'{op.type_slug}' is an internal-only type and cannot be created through the generic service layer."
                )
            instance = model_cls()

        elif op.verb == "create_edge":
            from_uuid = _coerce_uuid(op.from_target)
            to_uuid = _coerce_uuid(op.to_target)
            if from_uuid is None or to_uuid is None:
                raise ServiceValidationError("from_target and to_target are required for create_edge.")
            if not op.edge_type:
                raise ServiceValidationError("edge_type is required for create_edge.")
            from_entity = _load_entity_or_raise(from_uuid)
            to_entity = _load_entity_or_raise(to_uuid)
            # Step 7: Graph invariant — no edges between edges.
            if from_entity.entity_type == "edge":
                raise ServiceConstraintError("Edges cannot have other edges as endpoints (from_entity is an edge).")
            if to_entity.entity_type == "edge":
                raise ServiceConstraintError("Edges cannot have other edges as endpoints (to_entity is an edge).")
            model_cls = Edge
            instance = Edge(from_entity=from_entity, to_entity=to_entity, edge_type=op.edge_type)

        else:
            # patch / replace / delete verbs — load existing instance by target entity_id.
            if target_uuid is None:
                raise ServiceValidationError(f"target is required for {op.verb}.")

            # OCC guard (req-grid-service-batch-occ): when the caller declared
            # entity_expected_version, take a row-level SELECT FOR UPDATE on
            # the Entity row up front. The lock holds until the surrounding
            # transaction commits or rolls back; the subsequent typed-model
            # save + spine sync (or the explicit delete update) is the single
            # version bump per the spec's single-bump invariant. Missing
            # entity is reported as `entity_version_conflict` (not
            # `not_found`) when OCC is engaged, per the spec's not-found-vs-
            # conflict matrix.
            if op.entity_expected_version is not None:
                locked_row = (
                    Entity.objects.select_for_update().filter(pk=target_uuid).only("entity_type", "version").first()
                )
                if locked_row is None:
                    raise ServiceVersionConflictError(
                        entity_expected_version=op.entity_expected_version,
                        actual_entity_version=None,
                        entity_id=str(target_uuid),
                    )
                if locked_row.version != op.entity_expected_version:
                    raise ServiceVersionConflictError(
                        entity_expected_version=op.entity_expected_version,
                        actual_entity_version=locked_row.version,
                        entity_id=str(target_uuid),
                    )
                target_entity = locked_row
            else:
                target_entity = _load_entity_or_raise(target_uuid)

            try:
                model_cls = get_model_class(target_entity.entity_type)
            except KeyError as exc:
                raise ServiceNotFoundError(f"Unknown entity type: '{target_entity.entity_type}'.") from exc
            if getattr(model_cls, "INTERNAL_ONLY", False) and not internal_only_bypass:
                raise ServiceUnsupportedOperationError(
                    f"'{target_entity.entity_type}' is an internal-only type and cannot be modified through the generic service layer."
                )
            instance = model_cls.all_objects.select_related("entity").get(entity_id=target_uuid)

            # Write prohibition — tombstoned entities cannot be mutated.
            if not is_delete and instance.entity.deleted_at is not None:
                raise ServiceConflictError(
                    f"Entity {target_uuid} is tombstoned and cannot be modified.",
                    "entity_tombstoned",
                )

        # Thread caller-supplied dimensions onto the instance so the non-prespecified-id
        # path (BaseModel.save() / Edge.save()) can merge them with type defaults.
        # The prespecified-id branch below applies the same merge explicitly before save().
        if is_create and op.dimensions:
            instance._initial_dimensions = dict(op.dimensions)

        # Step 8 (early): edge_type immutability — checked before schema validation so the
        # error code is "constraint_violation" rather than "validation_error".
        if op.verb in ("patch_edge", "replace_edge") and "edge_type" in payload:
            raise ServiceConstraintError("edge_type is immutable and cannot be changed after creation.")

        # Steps 4 & 5: Schema validation (additionalProperties:False handles strict rejection).
        if not is_delete:
            verb_key = _verb_to_schema_key(op.verb)
            schema = model_cls.SERVICE_CRUD_SCHEMA.get(verb_key, {})
            try:
                jsonschema.validate(instance=payload, schema=schema)
            except jsonschema.ValidationError as exc:
                raise ServiceValidationError(exc.message) from exc

        if op.verb == "create_edge":
            try:
                _validate_edge_constraint(from_entity.entity_type, to_entity.entity_type, op.edge_type)  # type: ignore[union-attr]
            except InvalidEdgeError as exc:
                raise ServiceConstraintError(str(exc)) from exc

        # Apply field changes to the instance.
        if op.verb in ("create_node",):
            for field_name, value in payload.items():
                setattr(instance, field_name, value)
        elif op.verb == "create_edge":
            if "properties" in payload:
                instance.properties = payload["properties"]
        elif op.verb in ("patch_node", "patch_edge"):
            _apply_patch(instance, payload)
        elif op.verb in ("replace_node", "replace_edge"):
            _apply_replace(instance, payload, model_cls)

        # Step 6: Model validation (full_validate + Django full_clean).
        if not is_delete:
            try:
                instance.full_validate()
            except DjangoValidationError as exc:
                errors = _django_errors_to_service_errors(exc)
                return WriteResult(success=False, batch_id=batch_id, operation=op.verb, errors=errors)

            try:
                instance.full_clean(exclude=["entity", "batch_id", "flip_map"])
            except DjangoValidationError as exc:
                errors = _django_errors_to_service_errors(exc)
                return WriteResult(success=False, batch_id=batch_id, operation=op.verb, errors=errors)

        # Steps 10 & 11: Persistence and provenance recording.
        # For deletes: record provenance BEFORE tombstoning so the entity row
        # is still valid when record_batch_event() reads it.
        # For creates/updates: record provenance AFTER save so entity_id is set.

        # Pre-create Entity with the caller-specified entity_id for create verbs
        # (e.g. GRIFT upsert where identity must be preserved across grids).
        # This must happen after field-setting so get_name() returns the right value,
        # and before save() so save() takes the explicit-entity path.
        spine_just_created = False
        if is_create and op.entity_id is not None and instance.entity_id is None:
            prespecified_id = _coerce_uuid(op.entity_id)
            if op.verb == "create_edge":
                from tap_grid.constraints import get_edge_default_dimensions

                base_dims = dict(get_edge_default_dimensions(op.edge_type))  # type: ignore[arg-type]
            else:
                base_dims = dict(getattr(model_cls, "DEFAULT_DIMENSIONS", {}))
            caller_dims: dict[str, str] = getattr(instance, "_initial_dimensions", {}) or {}
            merged_dims = {**base_dims, **caller_dims}
            instance.entity = Entity.objects.create(
                id=prespecified_id,
                entity_type=model_cls.ENTITY_TYPE,
                name=instance.get_name(),
                dimensions=merged_dims,
            )
            # Signal BaseModel.save() to skip its spine_updates branch on the
            # subsequent save: this Entity row was created moments ago at
            # version=1 with the correct name/dimensions/updated_at, and the
            # forthcoming save is the SAME logical create operation — not a
            # follow-up mutation. Without this signal, save() would land
            # spine_updates that bump version to 2, producing a single
            # create op that mysteriously lands at version=2 while the
            # auto-create branch (entity_id None) correctly lands at 1.
            # See req-grid-service-batch (single-bump invariant).
            spine_just_created = True

        if is_delete:
            entity_id_out = target_uuid
            if hasattr(instance, "entity"):
                try:
                    _record_provenance(op.verb, instance.entity, batch_id, user)
                except Exception:
                    logger.exception("[4f93] Provenance recording failed for batch %s", batch_id)
            # Tombstone: set deleted_at on the entity and cascade to its edges.
            now = timezone.now()
            from django.db.models import F, Q

            Entity.objects.filter(pk=instance.entity_id).update(
                deleted_at=now,
                updated_at=now,
                version=F("version") + 1,
            )
            # Cascade tombstone to edges at both endpoints.
            edge_entity_ids = Edge.objects.filter(
                Q(from_entity_id=instance.entity_id) | Q(to_entity_id=instance.entity_id)
            ).values_list("entity_id", flat=True)
            Entity.objects.filter(pk__in=list(edge_entity_ids)).update(
                deleted_at=now,
                updated_at=now,
                version=F("version") + 1,
            )
        else:
            instance.save(skip_validation=True, _spine_just_created=spine_just_created)
            entity_id_out = instance.entity_id
            # Record provenance for non-delete writes too so the BatchEvent log
            # is a complete history of batch-scoped activity. Without this,
            # batch-scoped sweeps (req-grid-import-grift-batch-scoped-sweep)
            # can't identify which entities a batch originally created.
            if hasattr(instance, "entity") and instance.entity is not None:
                try:
                    _record_provenance(op.verb, instance.entity, batch_id, user)
                except Exception:
                    logger.exception("[3c88] Provenance recording failed for batch %s", batch_id)

        # Step 12: Response shaping.
        summary = None
        if result_mode in ("standard", "verbose") and not is_delete:
            summary = _build_object_summary(instance)

        return WriteResult(
            success=True,
            batch_id=batch_id,
            operation=op.verb,
            entity_id=entity_id_out,
            object_summary=summary,
        )

    except ServiceVersionConflictError as exc:
        # OCC conflict — surfaces with the structured detail payload so
        # callers can implement retry-or-surface logic without parsing the
        # message string. See req-grid-service-batch-occ-3.
        return WriteResult(
            success=False,
            batch_id=batch_id,
            operation=op.verb,
            errors=[
                ServiceError(
                    code="entity_version_conflict",
                    message=str(exc),
                    detail=exc.to_detail(),
                )
            ],
        )
    except (
        ServiceValidationError,
        ServiceConstraintError,
        ServiceNotFoundError,
        ServiceAuthzError,
        ServiceConflictError,
        ServiceUnsupportedOperationError,
    ) as exc:
        code_map = {
            ServiceValidationError: "validation_error",
            ServiceConstraintError: "constraint_violation",
            ServiceNotFoundError: "not_found",
            ServiceAuthzError: "authz_failure",
            ServiceConflictError: "conflict",
            ServiceUnsupportedOperationError: "unsupported_operation",
        }
        return WriteResult(
            success=False,
            batch_id=batch_id,
            operation=op.verb,
            errors=[ServiceError(code=code_map[type(exc)], message=str(exc))],  # type: ignore[arg-type]
        )
    except Exception as exc:
        logger.exception("[95fb] Unhandled error in write pipeline for verb=%s", op.verb)
        return WriteResult(
            success=False,
            batch_id=batch_id,
            operation=op.verb,
            errors=[ServiceError(code="internal_error", message=str(exc))],
        )


# ---------------------------------------------------------------------------
# Public write API
# ---------------------------------------------------------------------------


def _drain_hotlink_checks_into_results(results: list[WriteResult]) -> bool:
    """Pre-commit consistency phase: drain the deferred-hotlink queue.

    Implements req-grid-service-batch-precommit-consistency for the hotlink
    consumer (req-grid-hotlink-deferred). The deferred queue holds the model
    instances whose hotlinks were skipped during per-op validation. The drain
    re-runs validate_hotlinks() on each instance — by now every node and edge
    in this batch has been saved, so the validator sees the batch's intended
    end-state graph.

    The drain collects every failure across the full queue (no first-failure
    bail), attributes each failure to the WriteResult whose entity_id matches
    the failing instance (flipping it to success=False and appending the
    error), and returns True iff any failure was recorded.

    Note: drain_deferred_hotlink_checks() resets the queue to an empty list,
    so re-entrant calls to validate_hotlinks() from within this drain do not
    feed back into the queue we are draining.

    Args:
        results: The per-op WriteResult list, used to attribute failures by
            entity_id.

    Returns:
        True if at least one hotlink failure was collected; False otherwise.
    """
    from tap_grid.hotlink import validate_hotlinks

    queue = drain_deferred_hotlink_checks()
    if not queue:
        return False

    # Build entity_id → WriteResult index for attribution. If multiple ops
    # touched the same entity, the LAST op wins per
    # req-grid-service-batch-precommit-consistency-4.
    result_by_eid: dict[str, WriteResult] = {}
    for r in results:
        if r.entity_id is not None:
            result_by_eid[str(r.entity_id)] = r

    any_failure = False
    for instance in queue:
        try:
            validate_hotlinks(instance)
        except DjangoValidationError as exc:
            any_failure = True
            errors: list[ServiceError] = []
            try:
                for field_name, messages in exc.message_dict.items():
                    for msg in messages:
                        errors.append(
                            ServiceError(
                                code="hotlink_validation_failed",
                                message=str(msg),
                                field=field_name if field_name != "__all__" else None,
                            )
                        )
            except AttributeError:
                for msg in exc.messages:
                    errors.append(ServiceError(code="hotlink_validation_failed", message=str(msg)))

            target = result_by_eid.get(str(instance.entity_id)) if instance.entity_id else None
            if target is not None:
                target.success = False
                target.errors.extend(errors)
            else:
                # No matching result (shouldn't happen — every saved instance
                # came from a per-op pipeline that produced a WriteResult).
                # Attach to the last result as a safety net so the failure is
                # not silently dropped.
                if results:
                    results[-1].success = False
                    results[-1].errors.extend(errors)

    return any_failure


def write_batch(
    operations: list[WriteOperation],
    *,
    caller_context: CallerContext | None = None,
    dry_run: bool = False,
    result_mode: Literal["minimal", "standard", "verbose"] = "standard",
    _internal_only_bypass: bool = False,
) -> BatchWriteResult:
    """Execute multiple write operations atomically.

    All operations share one batch_id. If any operation fails, all are rolled
    back. Dry-run mode runs the full pipeline (including DB writes) then rolls
    back, returning validation results without persisting.

    Args:
        operations: Ordered list of WriteOperation instances.
        caller_context: Optional actor identity and existing batch scope.
        dry_run: If True, validate everything but roll back all writes.
        result_mode: Controls how much detail is included in each WriteResult.
        _internal_only_bypass: Trusted-internal callers only. When True, the
            pipeline does not reject INTERNAL_ONLY model types. Not part of the
            public API; the leading underscore signals the boundary. See
            `_create_node_internal` / `_patch_node_internal`.

    Returns:
        BatchWriteResult with per-operation results and overall success flag.
    """
    user = caller_context.user if caller_context else None

    # Resolve or create a batch_id.
    if caller_context and caller_context.batch_id:
        effective_batch_id = caller_context.batch_id
    else:
        effective_batch_id = str(uuid.uuid7())

    # Thread CallerContext so BaseModel.save() stamps batch_id on all writes.
    prior_ctx = get_caller_context()
    set_caller_context(CallerContext(user=user, batch_id=effective_batch_id))

    # Activate deferred-hotlink mode for this batch scope (req-grid-hotlink-
    # deferred). Per-op pipelines that call full_validate() → validate_hotlinks()
    # will enqueue the instance instead of validating inline; the pre-commit
    # consistency phase below drains the queue once every node and edge in the
    # batch has been saved.
    defer_token = start_deferred_hotlink_checks()

    results: list[WriteResult] = []
    batch_errors: list[ServiceError] = []

    try:
        with transaction.atomic():
            # Ensure the Batch entity exists inside the transaction so it
            # participates in rollback (e.g. dry_run, validation savepoints).
            try:
                _ensure_batch(effective_batch_id, user)
            except Exception:
                logger.exception("[fc60] Failed to ensure Batch entity for batch_id=%s", effective_batch_id)

            for op in operations:
                result = _execute_write_pipeline(
                    op,
                    batch_id=effective_batch_id,
                    user=user,
                    result_mode=result_mode,
                    internal_only_bypass=_internal_only_bypass,
                )
                results.append(result)
                if not result.success:
                    raise _BailOut()

            # Pre-commit consistency phase (req-grid-service-batch-precommit-
            # consistency). Drain the deferred hotlink queue; any failure flips
            # the matching per-op result and short-circuits via _BailOut so the
            # surrounding transaction.atomic() rolls back.
            if _drain_hotlink_checks_into_results(results):
                raise _BailOut()

            if dry_run:
                raise _DryRunRollback()

    except _DryRunRollback:
        pass  # Expected; DB changes rolled back; results already collected.
    except _BailOut:
        pass  # First failure captured in results; atomic() rolled back.
    except Exception as exc:
        logger.exception("[0b64] Unexpected error in write_batch")
        batch_errors.append(ServiceError(code="internal_error", message=str(exc)))
    finally:
        reset_deferred_hotlink_checks(defer_token)
        set_caller_context(prior_ctx)

    overall_success = not batch_errors and all(r.success for r in results)
    return BatchWriteResult(
        success=overall_success,
        batch_id=effective_batch_id,
        dry_run=dry_run,
        results=results,
        errors=batch_errors,
    )


def create_node(
    type_slug: str,
    payload: dict[str, Any],
    *,
    caller_context: CallerContext | None = None,
    dry_run: bool = False,
    result_mode: Literal["minimal", "standard", "verbose"] = "standard",
) -> WriteResult:
    """Create a new domain object of the given type.

    Args:
        type_slug: Registered entity type slug (e.g. "character").
        payload: Field values validated against SERVICE_CRUD_SCHEMA["create"].
        caller_context: Optional actor identity and batch scope.
        dry_run: If True, validate but do not persist.
        result_mode: Controls WriteResult detail level.

    Returns:
        WriteResult with entity_id populated on success.
    """
    op = WriteOperation(verb="create_node", type_slug=type_slug, payload=payload)
    batch_result = write_batch([op], caller_context=caller_context, dry_run=dry_run, result_mode=result_mode)
    return (
        batch_result.results[0]
        if batch_result.results
        else WriteResult(success=False, batch_id=batch_result.batch_id, errors=batch_result.errors)
    )


def patch_node(
    target: str | uuid.UUID,
    payload: dict[str, Any],
    *,
    caller_context: CallerContext | None = None,
    entity_expected_version: int | None = None,
    dry_run: bool = False,
    result_mode: Literal["minimal", "standard", "verbose"] = "standard",
) -> WriteResult:
    """Partially update a domain object (PATCH semantics).

    Omitted fields are unchanged. JSONField values are deep-merged.

    Args:
        target: Entity UUID of the object to patch.
        payload: Field values validated against SERVICE_CRUD_SCHEMA["patch"].
        caller_context: Optional actor identity and batch scope.
        entity_expected_version: Optional OCC declaration (req-grid-service-batch-occ).
            When set, the pipeline takes a SELECT FOR UPDATE on the target
            Entity row and verifies its `version` matches before mutation.
            Mismatch → `entity_version_conflict` with detail payload.
        dry_run: If True, validate but do not persist.
        result_mode: Controls WriteResult detail level.

    Returns:
        WriteResult with entity_id populated on success.
    """
    op = WriteOperation(
        verb="patch_node",
        target=target,
        payload=payload,
        entity_expected_version=entity_expected_version,
    )
    batch_result = write_batch([op], caller_context=caller_context, dry_run=dry_run, result_mode=result_mode)
    return (
        batch_result.results[0]
        if batch_result.results
        else WriteResult(success=False, batch_id=batch_result.batch_id, errors=batch_result.errors)
    )


def replace_node(
    target: str | uuid.UUID,
    payload: dict[str, Any],
    *,
    caller_context: CallerContext | None = None,
    entity_expected_version: int | None = None,
    dry_run: bool = False,
    result_mode: Literal["minimal", "standard", "verbose"] = "standard",
) -> WriteResult:
    """Fully replace the user-writable fields of a domain object (PUT semantics).

    All fields declared in SERVICE_CRUD_SCHEMA["replace"]["properties"] are
    replaced. Fields on the Entity spine are not affected.

    Args:
        target: Entity UUID of the object to replace.
        payload: Field values validated against SERVICE_CRUD_SCHEMA["replace"].
        caller_context: Optional actor identity and batch scope.
        entity_expected_version: Optional OCC declaration (req-grid-service-batch-occ).
            When set, the pipeline verifies `Entity.version` before mutation;
            mismatch → `entity_version_conflict`.
        dry_run: If True, validate but do not persist.
        result_mode: Controls WriteResult detail level.

    Returns:
        WriteResult with entity_id populated on success.
    """
    op = WriteOperation(
        verb="replace_node",
        target=target,
        payload=payload,
        entity_expected_version=entity_expected_version,
    )
    batch_result = write_batch([op], caller_context=caller_context, dry_run=dry_run, result_mode=result_mode)
    return (
        batch_result.results[0]
        if batch_result.results
        else WriteResult(success=False, batch_id=batch_result.batch_id, errors=batch_result.errors)
    )


def delete_node(
    target: str | uuid.UUID,
    *,
    caller_context: CallerContext | None = None,
    entity_expected_version: int | None = None,
    dry_run: bool = False,
    result_mode: Literal["minimal", "standard", "verbose"] = "standard",
) -> WriteResult:
    """Delete a domain object and its Entity spine.

    Cascades to edges per Django's cascade rules.

    Args:
        target: Entity UUID of the object to delete.
        caller_context: Optional actor identity and batch scope.
        entity_expected_version: Optional OCC declaration (req-grid-service-delete-occ).
            When set, the pipeline verifies `Entity.version` before tombstoning;
            mismatch → `entity_version_conflict`.
        dry_run: If True, validate but do not persist.
        result_mode: Controls WriteResult detail level.

    Returns:
        WriteResult with entity_id=None on success.
    """
    op = WriteOperation(
        verb="delete_node",
        target=target,
        entity_expected_version=entity_expected_version,
    )
    batch_result = write_batch([op], caller_context=caller_context, dry_run=dry_run, result_mode=result_mode)
    return (
        batch_result.results[0]
        if batch_result.results
        else WriteResult(success=False, batch_id=batch_result.batch_id, errors=batch_result.errors)
    )


def patch_edge(
    target: str | uuid.UUID,
    payload: dict[str, Any],
    *,
    caller_context: CallerContext | None = None,
    entity_expected_version: int | None = None,
    dry_run: bool = False,
    result_mode: Literal["minimal", "standard", "verbose"] = "standard",
) -> WriteResult:
    """Partially update an Edge's properties (PATCH semantics).

    edge_type is immutable and cannot be included in the payload.

    Args:
        target: Entity UUID of the Edge to patch.
        payload: Field values validated against Edge.SERVICE_CRUD_SCHEMA["patch"].
        caller_context: Optional actor identity and batch scope.
        entity_expected_version: Optional OCC declaration (req-grid-service-write-occ).
            When set, the pipeline verifies `Entity.version` before mutation;
            mismatch → `entity_version_conflict`.
        dry_run: If True, validate but do not persist.
        result_mode: Controls WriteResult detail level.

    Returns:
        WriteResult with entity_id populated on success.
    """
    op = WriteOperation(
        verb="patch_edge",
        target=target,
        payload=payload,
        entity_expected_version=entity_expected_version,
    )
    batch_result = write_batch([op], caller_context=caller_context, dry_run=dry_run, result_mode=result_mode)
    return (
        batch_result.results[0]
        if batch_result.results
        else WriteResult(success=False, batch_id=batch_result.batch_id, errors=batch_result.errors)
    )


def replace_edge(
    target: str | uuid.UUID,
    payload: dict[str, Any],
    *,
    caller_context: CallerContext | None = None,
    entity_expected_version: int | None = None,
    dry_run: bool = False,
    result_mode: Literal["minimal", "standard", "verbose"] = "standard",
) -> WriteResult:
    """Fully replace an Edge's properties (PUT semantics).

    edge_type is immutable and cannot be included in the payload.

    Args:
        target: Entity UUID of the Edge to replace.
        payload: Field values validated against Edge.SERVICE_CRUD_SCHEMA["replace"].
        caller_context: Optional actor identity and batch scope.
        entity_expected_version: Optional OCC declaration (req-grid-service-write-occ).
            When set, the pipeline verifies `Entity.version` before mutation;
            mismatch → `entity_version_conflict`.
        dry_run: If True, validate but do not persist.
        result_mode: Controls WriteResult detail level.

    Returns:
        WriteResult with entity_id populated on success.
    """
    op = WriteOperation(
        verb="replace_edge",
        target=target,
        payload=payload,
        entity_expected_version=entity_expected_version,
    )
    batch_result = write_batch([op], caller_context=caller_context, dry_run=dry_run, result_mode=result_mode)
    return (
        batch_result.results[0]
        if batch_result.results
        else WriteResult(success=False, batch_id=batch_result.batch_id, errors=batch_result.errors)
    )


def delete_edge_by_entity(
    target: str | uuid.UUID,
    *,
    caller_context: CallerContext | None = None,
    entity_expected_version: int | None = None,
    dry_run: bool = False,
    result_mode: Literal["minimal", "standard", "verbose"] = "standard",
) -> WriteResult:
    """Delete an Edge identified by its Entity UUID.

    Args:
        target: Entity UUID of the Edge to delete.
        caller_context: Optional actor identity and batch scope.
        entity_expected_version: Optional OCC declaration (req-grid-service-delete-occ).
            When set, the pipeline verifies `Entity.version` before tombstoning;
            mismatch → `entity_version_conflict`.
        dry_run: If True, validate but do not persist.
        result_mode: Controls WriteResult detail level.

    Returns:
        WriteResult with entity_id=None on success.
    """
    op = WriteOperation(
        verb="delete_edge",
        target=target,
        entity_expected_version=entity_expected_version,
    )
    batch_result = write_batch([op], caller_context=caller_context, dry_run=dry_run, result_mode=result_mode)
    return (
        batch_result.results[0]
        if batch_result.results
        else WriteResult(success=False, batch_id=batch_result.batch_id, errors=batch_result.errors)
    )


# ---------------------------------------------------------------------------
# Service-layer purge — DEBUG-only hard-delete
#
# req-grid-service-purge in spec-grid-service-delete.md. Narrow escape hatch
# for hard-deleting a single entity along with its touching edges and history
# rows. Default delete semantics remain tombstone; this is the explicit
# exception when an operator needs the entity gone rather than hidden.
# ---------------------------------------------------------------------------


@dataclass
class PurgeResult:
    """Outcome of a single purge_node call.

    `purged_edges` lists Entity UUIDs of Edge rows hard-deleted as part of the
    cascade. `purged_entity_id` is the Entity UUID that was the purge target.
    """

    success: bool
    purged_entity_id: str | None
    purged_entity_type: str | None
    purged_edges: list[str] = field(default_factory=list)
    error: str | None = None


def _assert_debug_for_purge(verb_name: str = "purge_node") -> None:
    """Enforce the DEBUG-only invariant on purge verbs.

    Mirrors req-grid-import-grift-sweep-purge so the "purges are DEBUG-only"
    rule reads consistently across the GRIFT sweep purge and the service-layer
    purge verbs (purge_node, purge_edge). There is no alternate flag, env var,
    or settings key that enables purge in any other configuration.
    """
    from django.conf import settings

    if not getattr(settings, "DEBUG", False):
        raise ServiceConflictError(
            f"{verb_name} is permitted only when DEBUG=True (purge_refused_production); " "see req-grid-service-purge."
        )


def purge_node(
    entity_id: str | uuid.UUID,
    *,
    caller_context: CallerContext | None = None,
    entity_expected_version: int | None = None,
    reason: str,
) -> PurgeResult:
    """Hard-delete an entity, its touching edges, and history rows.

    DEBUG-only. Removes the typed BaseModel row + Entity-spine row + every
    Edge row touching the entity at either end + the history rows for both
    the typed model and the edges + the BatchEvent rows referencing any of
    them. Neighbor entities at the far end of touching edges are NOT purged
    — cascade is edges-only.

    See req-grid-service-purge for the full contract. This function and
    `_apply_sweep_purge` in the GRIFT importer share the same DEBUG gate and
    the same hard-delete semantics; a future refactor will route the GRIFT
    sweep through this primitive.

    Args:
        entity_id: Entity UUID of the node to purge.
        caller_context: Optional actor identity, captured in the log line.
        entity_expected_version: Optional OCC declaration (req-grid-service-delete-occ).
            When set, the purge takes a SELECT FOR UPDATE on the Entity row
            and verifies `Entity.version` matches before the hard delete.
            Mismatch (or missing entity with OCC engaged) → ServiceVersionConflictError.
            The DEBUG gate still applies independently.
        reason: Required free-form description of why the purge is happening.
            Captured in the application log alongside the entity_id and actor.

    Returns:
        PurgeResult describing what was removed.

    Raises:
        ServiceConflictError: If `settings.DEBUG` is False.
        ServiceValidationError: If entity_id cannot be coerced, or `reason` is empty.
        ServiceNotFoundError: If no Entity with that UUID exists (only when
            entity_expected_version is None; with OCC engaged, missing-entity
            surfaces as ServiceVersionConflictError instead).
        ServiceVersionConflictError: When entity_expected_version is set and
            does not match the local `Entity.version` (or the entity is
            missing).
    """
    _assert_debug_for_purge()

    if not reason or not reason.strip():
        raise ServiceValidationError("purge_node requires a non-empty `reason`.")

    try:
        target_uuid = _coerce_uuid(entity_id)
    except (ValueError, TypeError) as exc:
        raise ServiceValidationError(f"entity_id is not a valid UUID: {entity_id!r}") from exc
    if target_uuid is None:
        raise ServiceValidationError("entity_id must be provided.")

    actor = caller_context.user if caller_context is not None else None

    from django.db.models import Q

    from tap_grid.models import BatchEvent
    from tap_grid.registry import get_model_class

    with transaction.atomic():
        # OCC guard (req-grid-service-delete-occ). When entity_expected_version
        # is declared, take SELECT FOR UPDATE on the Entity row up front and
        # verify the version; this is the only entity-row read for the
        # function and the lock holds for the rest of the transaction so the
        # subsequent cascade reads + hard deletes run on a stable view.
        if entity_expected_version is not None:
            entity = Entity.objects.select_for_update().filter(pk=target_uuid).first()
            if entity is None:
                raise ServiceVersionConflictError(
                    entity_expected_version=entity_expected_version,
                    actual_entity_version=None,
                    entity_id=str(target_uuid),
                )
            if entity.version != entity_expected_version:
                raise ServiceVersionConflictError(
                    entity_expected_version=entity_expected_version,
                    actual_entity_version=entity.version,
                    entity_id=str(target_uuid),
                )
        else:
            entity = Entity.objects.filter(pk=target_uuid).first()
            if entity is None:
                raise ServiceNotFoundError(f"No Entity with entity_id={target_uuid}.")
        entity_type = entity.entity_type

        if entity_type == "edge":
            # Edges have their own delete path (delete_edge_by_entity); purge is
            # scoped to node-style entities so we don't conflate purging a node
            # (which cascades to its edges) with purging an edge directly.
            raise ServiceConflictError(
                f"purge_node targets node entities; entity {target_uuid} is an edge. "
                "Purging an edge directly is not supported in v0."
            )

        # Find touching edges before we delete the spine. Both directions, including
        # tombstoned edges (Edge.all_objects), so the purge actually clears them.
        touching_edge_ids = list(
            Edge.all_objects.filter(Q(from_entity_id=target_uuid) | Q(to_entity_id=target_uuid)).values_list(
                "entity_id", flat=True
            )
        )

        try:
            model_cls = get_model_class(entity_type)
        except KeyError:
            model_cls = None

        # Order matters here: we MUST delete the Entity rows (which cascade to
        # the typed BaseModel rows via OneToOneField(on_delete=CASCADE)) BEFORE
        # sweeping history. django-simple-history's post_delete signal fires on
        # the cascade and would create a fresh "delete" history row that would
        # then survive a pre-cascade history sweep. Deleting history after the
        # cascade catches every row, including the signal-generated ones.

        # 1) Touching edges: delete Entity rows first (cascades the typed Edge).
        if touching_edge_ids:
            Entity.objects.filter(pk__in=touching_edge_ids).delete()

        # 2) The target Entity itself. Cascades the typed BaseModel row.
        Entity.objects.filter(pk=target_uuid).delete()

        # 3) Now sweep history rows for the typed model and the touching edges.
        #    django-simple-history doesn't cascade-delete history with the live
        #    row; explicit deletion is required.
        if model_cls is not None and hasattr(model_cls, "history"):
            model_cls.history.filter(entity_id=target_uuid).delete()
        if touching_edge_ids:
            Edge.history.filter(entity_id__in=touching_edge_ids).delete()

        # 4) BatchEvent rows referencing the purged entity or edges so no
        #    orphan event rows survive.
        BatchEvent.objects.filter(entity_id=target_uuid).delete()
        if touching_edge_ids:
            BatchEvent.objects.filter(entity_id__in=touching_edge_ids).delete()

    logger.info(
        "[3240] purge_node: entity_id=%s entity_type=%s touching_edges=%d actor=%s reason=%r",
        target_uuid,
        entity_type,
        len(touching_edge_ids),
        actor,
        reason,
    )

    return PurgeResult(
        success=True,
        purged_entity_id=str(target_uuid),
        purged_entity_type=entity_type,
        purged_edges=[str(eid) for eid in touching_edge_ids],
    )


def purge_edge(
    entity_id: str | uuid.UUID,
    *,
    caller_context: CallerContext | None = None,
    entity_expected_version: int | None = None,
    reason: str,
) -> PurgeResult:
    """Hard-delete one Edge entity and its history/event rows.

    DEBUG-only. Removes the typed Edge row, its Entity-spine row, its
    HistoricalEdge rows, and BatchEvent rows referencing the edge. Endpoint
    nodes survive; this is the edge sibling of purge_node and does NOT
    cascade to either endpoint.

    See req-grid-service-purge-edge for the full contract.

    Args:
        entity_id: Entity UUID of the Edge to purge.
        caller_context: Optional actor identity, captured in the log line.
        entity_expected_version: Optional OCC declaration (req-grid-service-delete-occ).
            When set, the purge takes a SELECT FOR UPDATE on the Entity row
            and verifies `Entity.version` matches before the hard delete.
            Mismatch (or missing entity with OCC engaged) → ServiceVersionConflictError.
            The DEBUG gate still applies independently.
        reason: Required free-form description of why the purge is happening.
            Captured in the application log alongside the entity_id and actor.

    Returns:
        PurgeResult describing the purged edge. ``purged_edges`` is empty
        (an edge purge has no cascade — the edge itself is the target).

    Raises:
        ServiceConflictError: If ``settings.DEBUG`` is False, or if the
            target Entity is not of type "edge" (purge_edge_wrong_type).
        ServiceValidationError: If entity_id cannot be coerced, or `reason` is empty.
        ServiceNotFoundError: If no Entity with that UUID exists (only when
            entity_expected_version is None; with OCC engaged, missing-entity
            surfaces as ServiceVersionConflictError instead).
        ServiceVersionConflictError: When entity_expected_version is set and
            does not match the local `Entity.version` (or the entity is
            missing).
    """
    _assert_debug_for_purge("purge_edge")

    if not reason or not reason.strip():
        raise ServiceValidationError("purge_edge requires a non-empty `reason`.")

    try:
        target_uuid = _coerce_uuid(entity_id)
    except (ValueError, TypeError) as exc:
        raise ServiceValidationError(f"entity_id is not a valid UUID: {entity_id!r}") from exc
    if target_uuid is None:
        raise ServiceValidationError("entity_id must be provided.")

    actor = caller_context.user if caller_context is not None else None

    from tap_grid.models import BatchEvent

    with transaction.atomic():
        # OCC guard (req-grid-service-delete-occ). When declared, take
        # SELECT FOR UPDATE on the Entity row up front and verify version
        # before any reads or writes; the lock holds for the rest of the
        # transaction.
        if entity_expected_version is not None:
            entity = Entity.objects.select_for_update().filter(pk=target_uuid).first()
            if entity is None:
                raise ServiceVersionConflictError(
                    entity_expected_version=entity_expected_version,
                    actual_entity_version=None,
                    entity_id=str(target_uuid),
                )
            if entity.version != entity_expected_version:
                raise ServiceVersionConflictError(
                    entity_expected_version=entity_expected_version,
                    actual_entity_version=entity.version,
                    entity_id=str(target_uuid),
                )
        else:
            entity = Entity.objects.filter(pk=target_uuid).first()
            if entity is None:
                raise ServiceNotFoundError(f"No Entity with entity_id={target_uuid}.")

        if entity.entity_type != "edge":
            raise ServiceConflictError(
                f"purge_edge targets edge entities; entity {target_uuid} has "
                f"entity_type={entity.entity_type!r} (purge_edge_wrong_type). "
                "Use purge_node for node entities."
            )

        # Capture endpoints before the cascade for the log line. Use all_objects so
        # a tombstoned edge still surfaces its endpoints.
        edge_row = Edge.all_objects.filter(entity_id=target_uuid).first()
        from_id = edge_row.from_entity_id if edge_row else None
        to_id = edge_row.to_entity_id if edge_row else None

        # Delete order mirrors purge_node:
        #   1) Entity row (cascades the typed Edge row via OneToOneField CASCADE)
        #   2) Edge history rows (django-simple-history does not cascade
        #      history with the live row)
        #   3) BatchEvent rows referencing the purged edge
        Entity.objects.filter(pk=target_uuid).delete()
        Edge.history.filter(entity_id=target_uuid).delete()
        BatchEvent.objects.filter(entity_id=target_uuid).delete()

    logger.info(
        "[4a1b] purge_edge: entity_id=%s from=%s to=%s actor=%s reason=%r",
        target_uuid,
        from_id,
        to_id,
        actor,
        reason,
    )

    return PurgeResult(
        success=True,
        purged_entity_id=str(target_uuid),
        purged_entity_type="edge",
        purged_edges=[],
    )


# ---------------------------------------------------------------------------
# Trusted-internal write API
#
# These entry points run the full write pipeline (validation, name sync,
# version, history, provenance, FLIP) minus the INTERNAL_ONLY gate. They are
# the canonical path for subsystem registration helpers (e.g.
# `tap_cares.registry._ensure_collector_node`) and lifecycle managers (e.g.
# `tap_cares.services.run_collection` creating CollectionJob rows) that need
# to write INTERNAL_ONLY model types.
#
# The leading underscore signals the boundary: these functions are not part of
# the public service-layer API and must not be re-exported through
# `tap_grid.__init__`. In-process malicious code can still call them; this is a
# tripwire for accidental misuse, not a wall (see
# `tap_grid/specs/spec-grid-entity.md` `req-grid-entity-internal`).
# ---------------------------------------------------------------------------


def _create_node_internal(
    type_slug: str,
    payload: dict[str, Any],
    *,
    caller_context: CallerContext | None = None,
    entity_id: str | uuid.UUID | None = None,
    dimensions: dict[str, str] | None = None,
    result_mode: Literal["minimal", "standard", "verbose"] = "standard",
) -> WriteResult:
    """Trusted-internal create for INTERNAL_ONLY (or any) node type.

    Runs the full write pipeline minus the INTERNAL_ONLY gate. Accepts an
    optional `entity_id` so callers can produce deterministic identity
    (e.g. UUIDv5 from `scope:key` in the dual-existence pattern).

    Args:
        type_slug: Registered entity type slug.
        payload: Field values validated against SERVICE_CRUD_SCHEMA["create"].
        caller_context: Optional actor identity and batch scope.
        entity_id: Optional pre-specified entity_id (UUID or str).
        dimensions: Optional caller dimensions; merged over DEFAULT_DIMENSIONS.
        result_mode: Controls WriteResult detail level.

    Returns:
        WriteResult with entity_id populated on success.
    """
    op = WriteOperation(
        verb="create_node",
        type_slug=type_slug,
        payload=payload,
        entity_id=entity_id,
        dimensions=dimensions,
    )
    batch_result = write_batch(
        [op],
        caller_context=caller_context,
        result_mode=result_mode,
        _internal_only_bypass=True,
    )
    return (
        batch_result.results[0]
        if batch_result.results
        else WriteResult(success=False, batch_id=batch_result.batch_id, errors=batch_result.errors)
    )


def _patch_node_internal(
    target: str | uuid.UUID,
    payload: dict[str, Any],
    *,
    caller_context: CallerContext | None = None,
    result_mode: Literal["minimal", "standard", "verbose"] = "standard",
) -> WriteResult:
    """Trusted-internal patch for INTERNAL_ONLY (or any) node type.

    Runs the full write pipeline minus the INTERNAL_ONLY gate. Same semantics
    as `patch_node` for non-INTERNAL_ONLY types.

    Args:
        target: Entity UUID of the object to patch.
        payload: Field values validated against SERVICE_CRUD_SCHEMA["patch"].
        caller_context: Optional actor identity and batch scope.
        result_mode: Controls WriteResult detail level.

    Returns:
        WriteResult with entity_id populated on success.
    """
    op = WriteOperation(verb="patch_node", target=target, payload=payload)
    batch_result = write_batch(
        [op],
        caller_context=caller_context,
        result_mode=result_mode,
        _internal_only_bypass=True,
    )
    return (
        batch_result.results[0]
        if batch_result.results
        else WriteResult(success=False, batch_id=batch_result.batch_id, errors=batch_result.errors)
    )


def _create_node_internal_for_test(
    type_slug: str,
    payload: dict[str, Any],
    *,
    caller_context: CallerContext | None = None,
    entity_id: str | uuid.UUID | None = None,
    dimensions: dict[str, str] | None = None,
    result_mode: Literal["minimal", "standard", "verbose"] = "standard",
) -> WriteResult:
    """Test-only trusted-internal create.

    Same semantics as `_create_node_internal` but raises `RuntimeError` if not
    running under Django test/DEBUG settings. This keeps production policy
    clean while letting tests construct INTERNAL_ONLY entities directly when
    they need to exercise model-level behavior (validation, dimension defaults,
    display projection, etc.) without going through a subsystem helper.
    """
    _assert_test_or_debug("_create_node_internal_for_test")
    return _create_node_internal(
        type_slug,
        payload,
        caller_context=caller_context,
        entity_id=entity_id,
        dimensions=dimensions,
        result_mode=result_mode,
    )


def _patch_node_internal_for_test(
    target: str | uuid.UUID,
    payload: dict[str, Any],
    *,
    caller_context: CallerContext | None = None,
    result_mode: Literal["minimal", "standard", "verbose"] = "standard",
) -> WriteResult:
    """Test-only trusted-internal patch. See `_create_node_internal_for_test`."""
    _assert_test_or_debug("_patch_node_internal_for_test")
    return _patch_node_internal(
        target,
        payload,
        caller_context=caller_context,
        result_mode=result_mode,
    )


def _assert_test_or_debug(fn_name: str) -> None:
    """Refuse to run when not in DEBUG / test settings.

    Test detection: pytest sets `PYTEST_CURRENT_TEST` while a test is running.
    DEBUG: Django's settings.DEBUG.
    """
    import os

    from django.conf import settings

    if not getattr(settings, "DEBUG", False) and "PYTEST_CURRENT_TEST" not in os.environ:
        raise RuntimeError(
            f"{fn_name} is for tests only; it refuses to run outside DEBUG / pytest. "
            "Production code should use the subsystem-owned trusted-internal helper instead."
        )


# ---------------------------------------------------------------------------
# Public read API
# ---------------------------------------------------------------------------


def resolve_entity(target: str | uuid.UUID) -> Entity:
    """Return the Entity row for the given entity UUID.

    Args:
        target: Entity UUID (str or uuid.UUID).

    Returns:
        The Entity instance.

    Raises:
        ServiceNotFoundError: If no entity with that UUID exists.
        ServiceValidationError: If target cannot be coerced to a UUID.
    """
    entity_id = _coerce_uuid(target)
    if entity_id is None:
        raise ServiceValidationError("target must be a valid UUID.")
    return _load_entity_or_raise(entity_id)


def get_node(target: str | uuid.UUID) -> Any:
    """Return the typed domain node instance for the given entity UUID.

    Args:
        target: Entity UUID (str or uuid.UUID).

    Returns:
        The concrete typed model instance (e.g. Character, Location).

    Raises:
        ServiceNotFoundError: If no entity with that UUID exists, or the type is unknown.
        ServiceConstraintError: If the entity is an edge, not a node.
        ServiceValidationError: If target cannot be coerced to a UUID.
    """
    from tap_grid.registry import get_model_class

    entity_id = _coerce_uuid(target)
    if entity_id is None:
        raise ServiceValidationError("target must be a valid UUID.")
    entity = _load_entity_or_raise(entity_id)
    if entity.entity_type == "edge":
        raise ServiceConstraintError(f"Entity {entity_id} is an edge, not a node.")
    try:
        model_cls = get_model_class(entity.entity_type)
    except KeyError as exc:
        raise ServiceNotFoundError(f"Unknown entity type: '{entity.entity_type}'.") from exc
    try:
        return model_cls.objects.select_related("entity").get(entity_id=entity_id)
    except model_cls.DoesNotExist as exc:
        raise ServiceNotFoundError(f"Node {entity_id} not found.") from exc


def get_edge(target: str | uuid.UUID) -> Edge:
    """Return the Edge instance for the given entity UUID.

    Args:
        target: Entity UUID (str or uuid.UUID).

    Returns:
        The Edge instance.

    Raises:
        ServiceNotFoundError: If no edge with that UUID exists.
        ServiceValidationError: If target cannot be coerced to a UUID.
    """
    entity_id = _coerce_uuid(target)
    if entity_id is None:
        raise ServiceValidationError("target must be a valid UUID.")
    try:
        return Edge.objects.select_related("entity").get(entity_id=entity_id)
    except Edge.DoesNotExist as exc:
        raise ServiceNotFoundError(f"Edge {entity_id} not found.") from exc


def get_object(target: str | uuid.UUID) -> Any:
    """Return the typed domain instance for the given entity UUID (node or edge).

    Dispatches to get_edge() for edge entities and get_node() for all others.

    Args:
        target: Entity UUID (str or uuid.UUID).

    Returns:
        The typed model instance.

    Raises:
        ServiceNotFoundError: If no entity with that UUID exists.
        ServiceValidationError: If target cannot be coerced to a UUID.
    """
    entity_id = _coerce_uuid(target)
    if entity_id is None:
        raise ServiceValidationError("target must be a valid UUID.")
    entity = _load_entity_or_raise(entity_id)
    if entity.entity_type == "edge":
        return get_edge(entity_id)
    return get_node(entity_id)


# ---------------------------------------------------------------------------
# Public discovery API
# ---------------------------------------------------------------------------


def list_node_types() -> list[str]:
    """Return all registered node type slugs, sorted."""
    from tap_grid.registry import list_entity_types

    return list_entity_types()


def describe_node_type(type_slug: str) -> NodeTypeDescription:
    """Return a discovery description for a registered node type.

    Args:
        type_slug: Entity type slug (e.g. "character").

    Returns:
        NodeTypeDescription with schemas, hotlinks, and constraint edge types.

    Raises:
        ServiceNotFoundError: If the type slug is not registered.
    """
    from tap_grid.constraints import WILDCARD, get_constraints
    from tap_grid.registry import get_model_class

    try:
        model_cls = get_model_class(type_slug)
    except KeyError as exc:
        raise ServiceNotFoundError(f"Unknown entity type: '{type_slug}'.") from exc

    schemas: dict[str, Any] = dict(getattr(model_cls, "SERVICE_CRUD_SCHEMA", {}))
    hotlinks: list[dict[str, Any]] = list(getattr(model_cls, "HOTLINKS", []))

    constraints = get_constraints(type_slug)
    outbound: list[str] = []
    inbound: list[str] = []
    if constraints:
        if constraints.outbound:
            outbound = sorted(k for k in constraints.outbound if constraints.outbound[k] is not WILDCARD or True)
        if constraints.inbound:
            inbound = sorted(k for k in constraints.inbound if constraints.inbound[k] is not WILDCARD or True)

    return NodeTypeDescription(
        type_slug=type_slug,
        schemas=schemas,
        hotlinks=hotlinks,
        outbound_edge_types=outbound,
        inbound_edge_types=inbound,
    )


def list_edge_types() -> list[str]:
    """Return all registered edge type slugs, sorted."""
    from tap_grid.constraints import list_registered_edge_types

    return list_registered_edge_types()


def describe_edge_type(edge_type: str) -> EdgeTypeDescription:
    """Return a discovery description for a registered edge type.

    Args:
        edge_type: Edge type slug (e.g. "LOCATED_IN").

    Returns:
        EdgeTypeDescription with allowed sources/targets and optional property schema.

    Raises:
        ServiceNotFoundError: If the edge type is not registered.
    """
    from tap_grid.constraints import WILDCARD, get_edge_property_schema, get_edge_type_constraints

    constraints = get_edge_type_constraints(edge_type)
    if constraints is None:
        raise ServiceNotFoundError(f"Unknown edge type: '{edge_type}'.")

    def _format_constraint(val: Any) -> list[str] | str:
        if val is WILDCARD:
            return "wildcard"
        if val is None or not val:
            return "none"
        assert isinstance(val, set)
        return sorted(val)

    return EdgeTypeDescription(
        edge_type=edge_type,
        allowed_sources=_format_constraint(constraints.sources),
        allowed_targets=_format_constraint(constraints.targets),
        property_schema=get_edge_property_schema(edge_type),
    )


def describe_service_capabilities() -> ServiceCapabilities:
    """Return a top-level discovery description of the TAP service layer."""
    return ServiceCapabilities(
        node_types=list_node_types(),
        edge_types=list_edge_types(),
        write_verbs=[
            "create_node",
            "patch_node",
            "replace_node",
            "delete_node",
            "create_edge",
            "patch_edge",
            "replace_edge",
            "delete_edge",
        ],
        read_functions=[
            "get_object",
            "get_node",
            "get_edge",
            "resolve_entity",
            "list_node_types",
            "describe_node_type",
            "list_edge_types",
            "describe_edge_type",
        ],
    )


# ---------------------------------------------------------------------------
# Legacy backward-compatible helpers (kept for existing callers)
# ---------------------------------------------------------------------------


def create_entity(
    entity_type: str,
    name: str = "",
    *,
    caller_context: CallerContext | None = None,
    **kwargs: Any,
) -> Entity:
    """Create a new Entity.

    .. deprecated::
        Bare Entity creation bypasses the typed write pipeline. Prefer
        ``create_node(type_slug, payload)`` for all typed domain objects.
        This function is kept for backward compatibility and will be removed
        once all callers are migrated.
    """
    return Entity.objects.create(
        entity_type=entity_type,
        name=name,
        **kwargs,
    )


def update_entity(entity: Entity, *, caller_context: CallerContext | None = None, **kwargs: Any) -> Entity:
    """Update an existing Entity's fields.

    .. deprecated::
        Prefer the typed write pipeline (``patch_node``) for domain objects.
    """
    for field_name, value in kwargs.items():
        setattr(entity, field_name, value)
    entity.save(update_fields=list(kwargs.keys()) + ["updated_at"])
    return entity


def delete_entity(entity: Entity, *, caller_context: CallerContext | None = None) -> None:
    """Delete an Entity. Cascades to edges and domain objects."""
    entity.delete()


def create_edge(
    from_entity: Entity,
    to_entity: Entity,
    edge_type: str,
    properties: dict[str, Any] | None = None,
    name: str = "",
    *,
    caller_context: CallerContext | None = None,
) -> Edge:
    """Create an Edge between two entities.

    The backing Entity for the Edge is auto-created by Edge.save().
    An optional name overrides the auto-generated label on that Entity.

    Raises InvalidEdgeError if either endpoint is itself an edge, or if the
    edge violates topology constraints.
    Raises EdgePropertyValidationError (via Edge.save()) if properties fail
    the registered schema for this edge type.

    Provenance: emits a ``link``-type BatchEvent on success, mirroring the
    pipeline's `_record_provenance` for ``create_edge`` ops. Recording is
    best-effort and requires an active batch context (either an explicit
    ``caller_context.batch_id`` or one already in the ContextVar). Calls
    outside any batch context proceed without an event.

    Future: this function predates the typed write pipeline and currently
    bypasses ``_execute_write_pipeline``. A future refactor should route
    through ``write_batch`` for full pipeline parity (FLIP propagation,
    OCC support, unified validation) — the legacy direct-create path is
    kept for the 100+ existing callers; migration is a separate concern.
    """
    # Edges cannot connect to other edges (req-grid-edge-nono)
    if from_entity.entity_type == "edge":
        raise InvalidEdgeError("Edges cannot have other edges as endpoints (from_entity is an edge).")
    if to_entity.entity_type == "edge":
        raise InvalidEdgeError("Edges cannot have other edges as endpoints (to_entity is an edge).")

    _validate_edge_constraint(from_entity.entity_type, to_entity.entity_type, edge_type)

    edge = Edge.objects.create(
        from_entity=from_entity,
        to_entity=to_entity,
        edge_type=edge_type,
        properties=properties or {},
    )

    if name:
        edge.entity.name = name
        edge.entity.save(update_fields=["name", "updated_at"])

    # Provenance: record a BatchEvent so this bare-helper path produces the
    # same audit trail the pipeline-routed `WriteOperation(verb="create_edge")`
    # produces via `_record_provenance`. No-ops cleanly if no batch context is
    # active (record_batch_event resolves batch_id from CallerContext.batch_id
    # or returns None). Wrapped in a try/except so a provenance failure never
    # breaks the edge create itself.
    from tap_grid.batch import record_batch_event

    try:
        record_batch_event(
            entity=edge.entity,
            event_type="link",
            model_name="Edge",
            actor=caller_context.user if caller_context is not None else None,
            batch_id=caller_context.batch_id if caller_context is not None else None,
        )
    except Exception:
        logger.exception("[e1c4] Best-effort BatchEvent emission failed for create_edge entity_id=%s", edge.entity_id)

    return edge


def update_edge_properties(edge: Edge, properties: dict[str, Any]) -> Edge:
    """Update an Edge's properties payload.

    Validates the new properties against the registered schema for the edge
    type (via Edge.save()) before persisting. Raises EdgePropertyValidationError
    if the payload is invalid.

    Args:
        edge: The Edge instance to update.
        properties: The new properties dict to assign.

    Returns:
        The updated Edge instance.
    """
    edge.properties = properties
    edge.save(update_fields=["properties"])
    return edge


def delete_edge(edge: Edge, *, caller_context: CallerContext | None = None) -> None:
    """Delete an Edge and its backing Entity."""
    # Deleting the backing Entity cascades to the Edge via OneToOne,
    # but we go through the Entity to keep the pattern consistent.
    edge.entity.delete()
