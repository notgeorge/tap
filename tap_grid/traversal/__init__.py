"""TAP traversal language — public API.

Parse and execute TAP traversal text (Cypher-like MATCH/WHERE/RETURN queries).

Usage::

    from tap_grid.traversal import parse_traversal, execute_traversal

    ast = parse_traversal("MATCH (hub)-[e]-(neighbor) WHERE hub.entity_id = $entity_id")
    result = execute_traversal(search, inputs={"entity_id": "<uuid>"}, db_alias="search_readonly")
"""

from tap_grid.traversal.executor import execute_traversal
from tap_grid.traversal.parser import parse_traversal

__all__ = ["execute_traversal", "parse_traversal"]
