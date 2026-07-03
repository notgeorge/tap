"""MAJOR KLUDGE (v0 demo) — blanket authorization-boundary membership.

Every ``aws_account`` node on the grid is auto-scoped into the samsite FedRAMP
authorization boundary via a ``SCOPED_TO_BOUNDARY`` edge (account → boundary),
synthesized by the samsite compliance collector *after* the boto3 collector has
populated the account(s).

Why this exists
---------------
The boundary's real contract (``fedramp_20x_ksi`` ``Boundary`` model) is that
*curated* components link to it via ``SCOPED_TO_BOUNDARY`` and "what's in the
boundary" is a fan-in query over those edges. A correct boundary is a **subset**
— not every account in an org, and within an account not every resource is in
scope. This module deliberately ignores all of that and scopes in *every*
account, because for the single-account, everything-is-samsite demo it's right
enough and it's the fastest path to a real, queryable membership relationship.

Why here and not elsewhere
--------------------------
- NOT in the GRIFT seed: the account is collector-owned and does not exist at
  seed time, so a hardcoded edge to it dangles on a clean boot (the bug this
  replaces).
- NOT in ``fedramp_20x_ksi``: making the generic FedRAMP boundary auto-include
  ``aws_account`` would bake an aws_core-specific assumption into a plugin that
  must not know AWS exists (hermetic-plugins rule).
- HERE, in samsite: samsite is the integration plugin that legitimately depends
  on both aws_core (the account type) and fedramp_20x_ksi (the boundary type +
  edge), and already owns the boundary *instance*. The edges are minted after
  the accounts exist, so nothing dangles.

FUTURE SEAM (replace this whole module)
---------------------------------------
Replace blanket all-accounts membership with a curated declaration of which
account(s) / resources are actually in scope, the moment there is more than one
account or any out-of-scope resource. The ``kludge`` marker on every synthesized
edge's ``properties`` makes the demo-only edges machine-identifiable for that
migration.

Spec: ``req-samsite-collector-boundary-membership`` in
``plugins/samsite/specs/spec-samsite-compliance-collector-v0.md``.
"""

from __future__ import annotations

import uuid
from typing import Any

# The samsite boundary instance, seeded by plugins/samsite/grift/landing.grift.json.
# samsite owns this node, so hardcoding its id here is in-plugin, not cross-plugin.
SAMSITE_BOUNDARY_ENTITY_ID = "019e4afc-3e9f-76c9-8771-73ea77b8ff13"

# Deterministic namespace for samsite-synthesized edge ids — re-runs upsert the
# same edge id rather than accumulating duplicates.
_NAMESPACE_SAMSITE = uuid.uuid5(uuid.NAMESPACE_DNS, "tap.samsite.compliance_collector")

_SCOPED_TO_BOUNDARY = "SCOPED_TO_BOUNDARY__fedramp_20x_ksi"

# Machine-readable marker stamped on every kludge edge (see FUTURE SEAM above).
KLUDGE_MARKER = "all-aws-accounts-auto-in-boundary-v0"


def _boundary_edge_id(account_entity_id: str) -> str:
    """Deterministic edge id for one account's boundary-membership edge."""
    return str(
        uuid.uuid5(
            _NAMESPACE_SAMSITE,
            f"{_SCOPED_TO_BOUNDARY}:{account_entity_id}->{SAMSITE_BOUNDARY_ENTITY_ID}",
        )
    )


def fetch_aws_account_entity_ids() -> list[str]:
    """Return every ``aws_account`` node's entity id, via Gryphon.

    Empty on a fresh boot where the boto3 collector has not run yet — the
    caller then synthesizes no edges, which is the correct no-op.
    """
    # Local import keeps tap_grid out of the import-time graph for collector
    # unit tests that don't touch the grid.
    from tap_grid.gryphon import execute_gryphon_raw

    envelope = execute_gryphon_raw("MATCH (a:aws_core__aws_account) RETURN a", inputs={})
    ids: list[str] = []
    for node in envelope.get("nodes", []) or []:
        # execute_gryphon_raw returns the flat canonical node envelope, where
        # entity_id is a top-level key (not nested under an "entity" key as in
        # the GRIFT node-envelope shape).
        entity_id = node.get("entity_id")
        if entity_id:
            ids.append(str(entity_id))
    return ids


def synthesize_boundary_membership_edges(account_entity_ids: list[str]) -> list[dict[str, Any]]:
    """Build one ``SCOPED_TO_BOUNDARY`` edge envelope per account → the boundary."""
    edges: list[dict[str, Any]] = []
    for account_entity_id in account_entity_ids:
        edges.append(
            {
                "entity": {
                    "entity_id": _boundary_edge_id(account_entity_id),
                    "entity_type": "edge",
                    "name": "aws_account SCOPED_TO_BOUNDARY Samsite Authorization Boundary (KLUDGE: all-accounts)",
                    "dimensions": {"compliance": "boundary"},
                },
                "edge": {
                    "from_entity_id": account_entity_id,
                    "to_entity_id": SAMSITE_BOUNDARY_ENTITY_ID,
                    "edge_type": _SCOPED_TO_BOUNDARY,
                    "properties": {"kludge": KLUDGE_MARKER},
                },
            }
        )
    return edges
