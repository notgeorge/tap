"""TAP gryphon language — public API.

Parse and execute gryphon text (Cypher-like MATCH/WHERE/RETURN queries).

Usage::

    from tap_grid.gryphon import parse_gryphon, execute_gryphon

    ast = parse_gryphon("MATCH (hub)-[e]-(neighbor) WHERE hub.entity_id = $entity_id")
    result = execute_gryphon(search, inputs={"entity_id": "<uuid>"}, db_alias="search_readonly")
"""

from tap_grid.gryphon.executor import execute_gryphon
from tap_grid.gryphon.parser import parse_gryphon

__all__ = ["execute_gryphon", "parse_gryphon"]
