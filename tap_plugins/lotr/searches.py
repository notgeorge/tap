"""LOTR module search runners.

Registered in LotrConfig.ready() under scope "tap_plugins.lotr.searches".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tap_grid.models import Search


def list_characters_with_bio(
    search: "Search", inputs: dict[str, Any], *, db_alias: str
) -> dict[str, Any]:
    """Return all LOTR characters enriched with their title and bio fields."""
    from tap_plugins.lotr.models import Character

    characters = (
        Character.objects.using(db_alias).select_related("entity").order_by("entity__display_name")
    )
    nodes = [
        {
            "entity_id": str(c.entity_id),
            "entity_type": "character",
            "display_name": c.entity.display_name,
            "dimensions": c.entity.dimensions,
            "title": c.title,
            "bio": c.bio,
        }
        for c in characters
    ]
    return {"nodes": nodes, "edges": []}
