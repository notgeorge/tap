"""TAP Web registries.

panel_type_registry holds registered panel type classes. Plugin authors
register panel types here so they are discoverable at runtime.
"""

from tap_grid.registry import ScopedRegistry

panel_type_registry: ScopedRegistry[type] = ScopedRegistry(
    "panel_types",
    title="Panel Types",
    description="Registered panel type classes. Plugin authors register panel types here.",
)
