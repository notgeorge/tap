"""Search runners for LOTR character queries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tap_grid.gryphon.executor import execute_gryphon

if TYPE_CHECKING:
    from tap_grid.models import Search

_LIST_CHARACTERS_QUERY = "MATCH (c:character) RETURN c.entity_id, c.entity_type, c.name, c.data.bio"


def list_characters_with_bio(
    _search: Search, inputs: dict[str, Any], *, db_alias: str, **kwargs: Any
) -> dict[str, Any]:
    """Return all LOTR characters enriched with their bio field (via Gryphon type scan)."""
    from tap_grid.models import Search as SearchModel

    proxy = SearchModel(
        name="list-characters-with-bio",
        search_type="gryphon",
        root="node",
        definition={"query": _LIST_CHARACTERS_QUERY},
    )
    return execute_gryphon(proxy, inputs, db_alias=db_alias, **kwargs)
