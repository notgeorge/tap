"""Write operation data types for the TAP service layer.

These dataclasses form the public contract for write_batch() and the
single-verb convenience functions. They carry no Django or ORM imports
so callers can import them without triggering the Django app registry.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class WriteOperation:
    """A single write intent submitted to write_batch().

    Attributes:
        verb: One of create_node | patch_node | replace_node | delete_node |
              create_edge | patch_edge | replace_edge | delete_edge.
        type_slug: Entity type slug, required for create_node.
        target: Entity UUID (str or uuid.UUID) for patch / replace / delete verbs.
        payload: JSON-safe field values validated against SERVICE_SCHEMAS.
        from_target: Source entity UUID for create_edge.
        to_target: Destination entity UUID for create_edge.
        edge_type: Edge type string for create_edge.
    """

    verb: str
    type_slug: str | None = None
    target: str | uuid.UUID | None = None
    payload: dict[str, Any] | None = None
    from_target: str | uuid.UUID | None = None
    to_target: str | uuid.UUID | None = None
    edge_type: str | None = None


@dataclass
class ServiceError:
    """Structured error from the write pipeline.

    Attributes:
        code: Machine-readable error category.
        message: Human-readable description.
        field: Model field name if the error is field-specific.
        detail: Optional structured context for admin or bot inspection.
    """

    code: Literal[
        "validation_error",
        "constraint_violation",
        "not_found",
        "conflict",
        "unsupported_operation",
        "internal_error",
    ]
    message: str
    field: str | None = None
    detail: dict[str, Any] | None = None


@dataclass
class WriteResult:
    """Result envelope for a single write operation.

    Attributes:
        success: True if the operation was applied (or would be, for dry_run).
        batch_id: The batch UUID string this operation participated in.
        entity_id: The UUID of the created or mutated entity (None on delete).
        object_summary: Populated for standard/verbose modes; None for minimal.
        warnings: Non-fatal advisory messages.
        errors: Populated only when success=False.
    """

    success: bool
    batch_id: str
    entity_id: uuid.UUID | None = None
    object_summary: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[ServiceError] = field(default_factory=list)


@dataclass
class BatchWriteResult:
    """Result envelope for write_batch().

    Attributes:
        success: True if all operations succeeded (or passed dry-run validation).
        batch_id: The batch UUID string shared by all operations.
        dry_run: True if no changes were committed to the database.
        results: Per-operation WriteResult list, in submission order.
        errors: Batch-level errors not tied to a specific operation.
    """

    success: bool
    batch_id: str
    dry_run: bool
    results: list[WriteResult] = field(default_factory=list)
    errors: list[ServiceError] = field(default_factory=list)
