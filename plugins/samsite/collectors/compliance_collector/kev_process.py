"""The CISA KEV fetch process: the deploy workflow → KEV catalog edge.

The static end of this story — the CISA ``web_host`` and the KEV catalog
``web_document``, joined by ``HOSTED_BY`` — is seeded by
``grift/kev-fetch.grift.json``. This module owns the dynamic end: the
``FETCHES`` edge from the deploy ``github_workflow`` (the signer of every
``/.well-known/`` artifact) to that seeded KEV catalog.

The edge can't be seeded statically because the deploy workflow's entity id
derives from a GitHub-assigned numeric workflow id, unknowable at authoring
time. So, exactly like the Sigstore ``SIGNED_BY_IDENTITY`` edge, the collector
resolves the workflow via Gryphon and emits the edge only when it resolves —
graceful (omitted) otherwise. The KEV catalog target is resolved (not minted)
here too: the seed owns that node, so the collector never creates it; if the
seed has not run, ``FETCHES`` is omitted rather than dangling.

Spec: plugins/samsite/specs/spec-samsite-compliance-collector-v0.md
(req-samsite-collector-kev-fetch).
"""

from __future__ import annotations

from typing import Any, Final

from .identity import edge_entity_id

#: The KEV catalog's URL — the natural key shared with the grift seed. The seed
#: mints the web_document at ``node_entity_id("web_document", KEV_CATALOG_URL)``;
#: this module resolves the same node by url, so the two converge.
KEV_CATALOG_URL: Final[str] = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"

_FETCHES_DIMENSIONS: Final[dict[str, str]] = {"tap.computing": "network", "tap.web": "native"}


def resolve_kev_catalog_entity_id() -> str | None:
    """Return the seeded KEV catalog ``web_document`` entity id, or ``None``.

    A content match on ``url`` via Gryphon (mirrors ``sigstore_link``'s workflow
    resolver). Zero or multiple matches return ``None``, so the caller omits the
    ``FETCHES`` edge rather than guess or dangle.
    """
    from tap_grid.models import Search
    from tap_grid.search import execute_search

    search = Search(
        search_type="gryphon",
        root="node",
        name="samsite-compliance-kev-catalog-resolver",
        input_schema={
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
        definition={
            "query": [
                "MATCH (d:web_document)",
                "WHERE d.data.url = $url",
                "RETURN d",
            ]
        },
        default_limit=10,
        max_limit=50,
    )
    result = execute_search(search, inputs={"url": KEV_CATALOG_URL}, layer="extended")
    nodes = list((result.get("results", result) or {}).get("nodes", []) or [])
    if len(nodes) == 1:
        return str(nodes[0]["entity_id"])
    return None


def fetches_edge_envelope(deploy_workflow_entity_id: str, kev_catalog_entity_id: str) -> dict[str, Any]:
    """Build the ``FETCHES`` edge envelope: deploy workflow → KEV catalog."""
    edge_id = str(edge_entity_id("FETCHES", deploy_workflow_entity_id, kev_catalog_entity_id))
    return {
        "entity": {
            "entity_id": edge_id,
            "entity_type": "edge",
            "name": "Deploy workflow FETCHES CISA KEV Catalog",
            "dimensions": dict(_FETCHES_DIMENSIONS),
        },
        "edge": {
            "from_entity_id": deploy_workflow_entity_id,
            "to_entity_id": kev_catalog_entity_id,
            "edge_type": "FETCHES",
            "properties": {},
        },
    }
