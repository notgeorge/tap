"""Module search runners for the core examples plugin.

Registered in CoreExamplesConfig.ready(). These runners are intentionally
simple — their purpose is integration testing and serving as reference
implementations for plugin authors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tap_grid.models import Search


def list_concepts(search: Search, inputs: dict[str, Any], *, db_alias: str) -> dict[str, Any]:
    """Return all concept entities as a flat node list.

    Registered as: plugins.core_examples.searches:list-concepts
    """
    from tap_grid.models import Entity

    entities = Entity.objects.using(db_alias).filter(entity_type="concept").order_by("id")
    nodes = [
        {
            "entity_id": str(e.id),
            "entity_type": e.entity_type,
            "name": e.name,
            "dimensions": e.dimensions,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "updated_at": e.updated_at.isoformat() if e.updated_at else None,
        }
        for e in entities
    ]
    return {"nodes": nodes, "edges": []}
