"""TAP Web registries.

panel_type_registry holds registered panel type classes.
editor_registry holds registered EditorDescriptor instances.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tap_grid.registry import ScopedRegistry

if TYPE_CHECKING:
    from tap_web.editor import EditorDescriptor

panel_type_registry: ScopedRegistry[type] = ScopedRegistry(
    "panel_types",
    title="Panel Types",
    description="Registered panel type classes. Plugin authors register panel types here.",
)

# Simple dict keyed by entity_type slug.  One descriptor per type.
_editor_registry: dict[str, "EditorDescriptor"] = {}


def register_editor(descriptor: "EditorDescriptor") -> None:
    """Register a typed editor descriptor for an entity type.

    Args:
        descriptor: An EditorDescriptor instance. ``descriptor.entity_type``
            is used as the registry key.
    """
    _editor_registry[descriptor.entity_type] = descriptor


def get_editor(entity_type: str) -> "EditorDescriptor | None":
    """Return the registered EditorDescriptor for entity_type, or None.

    Args:
        entity_type: Entity type slug (e.g. ``"character"``).
    """
    return _editor_registry.get(entity_type)
