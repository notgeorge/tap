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
from typing import Any, Literal

import jsonschema
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models as django_models
from django.db import transaction

from tap_grid.caller_context import CallerContext, get_caller_context, set_caller_context
from tap_grid.constraints import validate_edge as _validate_edge_constraint
from tap_grid.exceptions import (
    InvalidEdgeError,
    ServiceConstraintError,
    ServiceNotFoundError,
    ServiceValidationError,
)
from tap_grid.models import Edge, Entity
from tap_grid.service_types import BatchWriteResult, ServiceError, WriteOperation, WriteResult

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
    """Map a write verb to its SERVICE_SCHEMAS key."""
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

    Sets every field listed in SERVICE_SCHEMAS["replace"]["properties"] to
    the payload value. Missing optional fields are reset to model defaults.
    """
    schema_props = model_cls.SERVICE_SCHEMAS.get("replace", {}).get("properties", {})
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
                errors.append(ServiceError(code="validation_error", message=str(msg), field=field_name if field_name != "__all__" else None))
    except AttributeError:
        for msg in exc.messages:
            errors.append(ServiceError(code="validation_error", message=str(msg)))
    return errors


def _load_entity_or_raise(entity_id: uuid.UUID) -> Entity:
    """Load an Entity by PK or raise ServiceNotFoundError."""
    try:
        return Entity.objects.get(pk=entity_id)
    except Entity.DoesNotExist:
        raise ServiceNotFoundError(f"Entity {entity_id} not found.")


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
    from tap_flip.batch.service import record_batch_event

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
    from tap_flip.models import Batch

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
) -> WriteResult:
    """Execute the write pipeline for a single WriteOperation.

    Returns a WriteResult. Never raises — errors are captured inside the result.
    """
    payload: dict[str, Any] = {k: v for k, v in (op.payload or {}).items() if v is not None}

    try:
        # Step 2: Security/authz stub (reserved; logs identity at DEBUG).
        logger.debug("write_pipeline verb=%s user=%s batch=%s", op.verb, user, batch_id)

        # Step 3: Object load and resolution.
        from tap_grid.registry import get_model_class

        is_edge_verb = op.verb in ("create_edge", "patch_edge", "replace_edge", "delete_edge")
        is_create = op.verb in ("create_node", "create_edge")
        is_delete = op.verb in ("delete_node", "delete_edge")

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
            except KeyError:
                raise ServiceNotFoundError(f"Unknown entity type: '{op.type_slug}'.")
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
            target_entity = _load_entity_or_raise(target_uuid)
            try:
                model_cls = get_model_class(target_entity.entity_type)
            except KeyError:
                raise ServiceNotFoundError(f"Unknown entity type: '{target_entity.entity_type}'.")
            instance = model_cls.objects.select_related("entity").get(entity_id=target_uuid)

        # Step 8 (early): edge_type immutability — checked before schema validation so the
        # error code is "constraint_violation" rather than "validation_error".
        if op.verb in ("patch_edge", "replace_edge") and "edge_type" in payload:
            raise ServiceConstraintError("edge_type is immutable and cannot be changed after creation.")

        # Steps 4 & 5: Schema validation (additionalProperties:False handles strict rejection).
        if not is_delete:
            verb_key = _verb_to_schema_key(op.verb)
            schema = model_cls.SERVICE_SCHEMAS.get(verb_key, {})
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
                return WriteResult(success=False, batch_id=batch_id, errors=errors)

            try:
                instance.full_clean(exclude=["entity", "batch_id", "flip_map"])
            except DjangoValidationError as exc:
                errors = _django_errors_to_service_errors(exc)
                return WriteResult(success=False, batch_id=batch_id, errors=errors)

        # Steps 10 & 11: Persistence and provenance recording.
        # For deletes: record provenance BEFORE the Entity row is removed so
        # the entity object is still valid when record_batch_event() reads it.
        # For creates/updates: record provenance AFTER save so entity_id is set.
        snapshot_entity: Entity | None = None
        if is_delete:
            entity_id_out = target_uuid
            # Record provenance before deletion while the entity row still exists.
            if hasattr(instance, "entity"):
                try:
                    _record_provenance(op.verb, instance.entity, batch_id, user)
                except Exception:
                    logger.exception("Provenance recording failed for batch %s", batch_id)
            instance.entity.delete()
        else:
            instance.save(skip_validation=True)
            entity_id_out = instance.entity_id
            snapshot_entity = instance.entity

        # Step 12: Response shaping.
        summary = None
        if result_mode in ("standard", "verbose") and not is_delete:
            summary = _build_object_summary(instance)

        return WriteResult(
            success=True,
            batch_id=batch_id,
            entity_id=entity_id_out,
            object_summary=summary,
        )

    except (ServiceValidationError, ServiceConstraintError, ServiceNotFoundError) as exc:
        code_map = {
            ServiceValidationError: "validation_error",
            ServiceConstraintError: "constraint_violation",
            ServiceNotFoundError: "not_found",
        }
        return WriteResult(
            success=False,
            batch_id=batch_id,
            errors=[ServiceError(code=code_map[type(exc)], message=str(exc))],  # type: ignore[arg-type]
        )
    except Exception as exc:
        logger.exception("Unhandled error in write pipeline for verb=%s", op.verb)
        return WriteResult(
            success=False,
            batch_id=batch_id,
            errors=[ServiceError(code="internal_error", message=str(exc))],
        )


# ---------------------------------------------------------------------------
# Public write API
# ---------------------------------------------------------------------------


def write_batch(
    operations: list[WriteOperation],
    *,
    caller_context: CallerContext | None = None,
    dry_run: bool = False,
    result_mode: Literal["minimal", "standard", "verbose"] = "standard",
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

    Returns:
        BatchWriteResult with per-operation results and overall success flag.
    """
    user = caller_context.user if caller_context else None

    # Resolve or create a batch_id.
    if caller_context and caller_context.batch_id:
        effective_batch_id = caller_context.batch_id
    else:
        effective_batch_id = str(uuid.uuid7())

    # Pre-create the Batch entity so record_batch_event() can find it.
    # This happens outside the main transaction so the row is visible
    # even if the main transaction rolls back (the Batch persists as an
    # audit record of the attempt).
    try:
        _ensure_batch(effective_batch_id, user)
    except Exception:
        logger.exception("Failed to ensure Batch entity for batch_id=%s", effective_batch_id)

    # Thread CallerContext so BaseModel.save() stamps batch_id on all writes.
    prior_ctx = get_caller_context()
    set_caller_context(CallerContext(user=user, batch_id=effective_batch_id))

    results: list[WriteResult] = []
    batch_errors: list[ServiceError] = []

    try:
        with transaction.atomic():
            for op in operations:
                result = _execute_write_pipeline(
                    op,
                    batch_id=effective_batch_id,
                    user=user,
                    result_mode=result_mode,
                )
                results.append(result)
                if not result.success:
                    raise _BailOut()

            if dry_run:
                raise _DryRunRollback()

    except _DryRunRollback:
        pass  # Expected; DB changes rolled back; results already collected.
    except _BailOut:
        pass  # First failure captured in results; atomic() rolled back.
    except Exception as exc:
        logger.exception("Unexpected error in write_batch")
        batch_errors.append(ServiceError(code="internal_error", message=str(exc)))
    finally:
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
        payload: Field values validated against SERVICE_SCHEMAS["create"].
        caller_context: Optional actor identity and batch scope.
        dry_run: If True, validate but do not persist.
        result_mode: Controls WriteResult detail level.

    Returns:
        WriteResult with entity_id populated on success.
    """
    op = WriteOperation(verb="create_node", type_slug=type_slug, payload=payload)
    batch_result = write_batch([op], caller_context=caller_context, dry_run=dry_run, result_mode=result_mode)
    return batch_result.results[0] if batch_result.results else WriteResult(success=False, batch_id=batch_result.batch_id, errors=batch_result.errors)


def patch_node(
    target: str | uuid.UUID,
    payload: dict[str, Any],
    *,
    caller_context: CallerContext | None = None,
    dry_run: bool = False,
    result_mode: Literal["minimal", "standard", "verbose"] = "standard",
) -> WriteResult:
    """Partially update a domain object (PATCH semantics).

    Omitted fields are unchanged. JSONField values are deep-merged.

    Args:
        target: Entity UUID of the object to patch.
        payload: Field values validated against SERVICE_SCHEMAS["patch"].
        caller_context: Optional actor identity and batch scope.
        dry_run: If True, validate but do not persist.
        result_mode: Controls WriteResult detail level.

    Returns:
        WriteResult with entity_id populated on success.
    """
    op = WriteOperation(verb="patch_node", target=target, payload=payload)
    batch_result = write_batch([op], caller_context=caller_context, dry_run=dry_run, result_mode=result_mode)
    return batch_result.results[0] if batch_result.results else WriteResult(success=False, batch_id=batch_result.batch_id, errors=batch_result.errors)


def replace_node(
    target: str | uuid.UUID,
    payload: dict[str, Any],
    *,
    caller_context: CallerContext | None = None,
    dry_run: bool = False,
    result_mode: Literal["minimal", "standard", "verbose"] = "standard",
) -> WriteResult:
    """Fully replace the user-writable fields of a domain object (PUT semantics).

    All fields declared in SERVICE_SCHEMAS["replace"]["properties"] are
    replaced. Fields on the Entity spine are not affected.

    Args:
        target: Entity UUID of the object to replace.
        payload: Field values validated against SERVICE_SCHEMAS["replace"].
        caller_context: Optional actor identity and batch scope.
        dry_run: If True, validate but do not persist.
        result_mode: Controls WriteResult detail level.

    Returns:
        WriteResult with entity_id populated on success.
    """
    op = WriteOperation(verb="replace_node", target=target, payload=payload)
    batch_result = write_batch([op], caller_context=caller_context, dry_run=dry_run, result_mode=result_mode)
    return batch_result.results[0] if batch_result.results else WriteResult(success=False, batch_id=batch_result.batch_id, errors=batch_result.errors)


def delete_node(
    target: str | uuid.UUID,
    *,
    caller_context: CallerContext | None = None,
    dry_run: bool = False,
    result_mode: Literal["minimal", "standard", "verbose"] = "standard",
) -> WriteResult:
    """Delete a domain object and its Entity spine.

    Cascades to edges per Django's cascade rules.

    Args:
        target: Entity UUID of the object to delete.
        caller_context: Optional actor identity and batch scope.
        dry_run: If True, validate but do not persist.
        result_mode: Controls WriteResult detail level.

    Returns:
        WriteResult with entity_id=None on success.
    """
    op = WriteOperation(verb="delete_node", target=target)
    batch_result = write_batch([op], caller_context=caller_context, dry_run=dry_run, result_mode=result_mode)
    return batch_result.results[0] if batch_result.results else WriteResult(success=False, batch_id=batch_result.batch_id, errors=batch_result.errors)


def patch_edge(
    target: str | uuid.UUID,
    payload: dict[str, Any],
    *,
    caller_context: CallerContext | None = None,
    dry_run: bool = False,
    result_mode: Literal["minimal", "standard", "verbose"] = "standard",
) -> WriteResult:
    """Partially update an Edge's properties (PATCH semantics).

    edge_type is immutable and cannot be included in the payload.

    Args:
        target: Entity UUID of the Edge to patch.
        payload: Field values validated against Edge.SERVICE_SCHEMAS["patch"].
        caller_context: Optional actor identity and batch scope.
        dry_run: If True, validate but do not persist.
        result_mode: Controls WriteResult detail level.

    Returns:
        WriteResult with entity_id populated on success.
    """
    op = WriteOperation(verb="patch_edge", target=target, payload=payload)
    batch_result = write_batch([op], caller_context=caller_context, dry_run=dry_run, result_mode=result_mode)
    return batch_result.results[0] if batch_result.results else WriteResult(success=False, batch_id=batch_result.batch_id, errors=batch_result.errors)


def replace_edge(
    target: str | uuid.UUID,
    payload: dict[str, Any],
    *,
    caller_context: CallerContext | None = None,
    dry_run: bool = False,
    result_mode: Literal["minimal", "standard", "verbose"] = "standard",
) -> WriteResult:
    """Fully replace an Edge's properties (PUT semantics).

    edge_type is immutable and cannot be included in the payload.

    Args:
        target: Entity UUID of the Edge to replace.
        payload: Field values validated against Edge.SERVICE_SCHEMAS["replace"].
        caller_context: Optional actor identity and batch scope.
        dry_run: If True, validate but do not persist.
        result_mode: Controls WriteResult detail level.

    Returns:
        WriteResult with entity_id populated on success.
    """
    op = WriteOperation(verb="replace_edge", target=target, payload=payload)
    batch_result = write_batch([op], caller_context=caller_context, dry_run=dry_run, result_mode=result_mode)
    return batch_result.results[0] if batch_result.results else WriteResult(success=False, batch_id=batch_result.batch_id, errors=batch_result.errors)


def delete_edge_by_entity(
    target: str | uuid.UUID,
    *,
    caller_context: CallerContext | None = None,
    dry_run: bool = False,
    result_mode: Literal["minimal", "standard", "verbose"] = "standard",
) -> WriteResult:
    """Delete an Edge identified by its Entity UUID.

    Args:
        target: Entity UUID of the Edge to delete.
        caller_context: Optional actor identity and batch scope.
        dry_run: If True, validate but do not persist.
        result_mode: Controls WriteResult detail level.

    Returns:
        WriteResult with entity_id=None on success.
    """
    op = WriteOperation(verb="delete_edge", target=target)
    batch_result = write_batch([op], caller_context=caller_context, dry_run=dry_run, result_mode=result_mode)
    return batch_result.results[0] if batch_result.results else WriteResult(success=False, batch_id=batch_result.batch_id, errors=batch_result.errors)


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
    for field, value in kwargs.items():
        setattr(entity, field, value)
    entity.save(update_fields=list(kwargs.keys()) + ["updated_at"])
    return entity


def delete_entity(entity: Entity, *, caller_context: "CallerContext | None" = None) -> None:
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
