"""CanaryCollector — a deterministic, offline cold-boot canary.

The development-validation gate (`spec-dev-validation.md`
`req-dev-validation-real-backend`) needs to drive **one real collector cycle
through the real DB-backed task backend** and positively assert grid mutation.
Every domain collector (aws/github/ksi/samsite) needs live network or credentials,
which would make the gate flaky on an upstream being down — the opposite of a gate.

This canary emits a fixed, self-contained GRIFT batch (two `grid_fixtures__leaf`
nodes + one `PG_LINKS__grid_fixtures` edge between them) from inline constants,
with **no network, no credentials, and no filesystem read**. It lands the same
`PRODUCED_BATCH`-with-`imported` signal any real collector would, so the gate's
grid-mutation assertion is deterministic and offline.

It lives in `grid_fixtures` — the neutral graph-fixture plugin whose node/edge
vocabulary it emits — so it is fully self-contained (no cross-plugin import) and,
like the rest of grid_fixtures, ships only into dev/test profiles, never a lean
customer profile. All entity ids are `uuid5`-derived, so re-running against an
existing grid is an idempotent no-op (a valid SUCCESSFUL gate outcome) rather than
a duplicate.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from tap_cares.collectors import CollectorBase

logger = logging.getLogger(__name__)

# Fixed namespace so every emitted entity id is stable across runs (minted once,
# never regenerated — determinism is the whole point).
_CANARY_NS = uuid.UUID("019f243a-ce11-7481-930e-4428dec0fda7")

_LEAF_TYPE = "grid_fixtures__leaf"
_EDGE_TYPE = "PG_LINKS__grid_fixtures"
_DIMENSIONS = {"tap.playground": "gridkin"}


def _uid(token: str) -> str:
    return str(uuid.uuid5(_CANARY_NS, token))


def _leaf(token: str, name: str, *, is_open: bool) -> dict[str, Any]:
    """One `grid_fixtures__leaf` node envelope (every field written explicitly)."""
    return {
        "entity": {
            "entity_id": _uid(token),
            "entity_type": _LEAF_TYPE,
            "name": name,
            "dimensions": _DIMENSIONS,
        },
        "node": {
            "name": name,
            "description": "cold-boot gate canary node",
            "kind": "cold_boot_canary",
            "severity_score": 0,
            "is_open": is_open,
            "observed_at": None,
            "tags": {},
        },
    }


class CanaryCollector(CollectorBase):
    """Emit a fixed two-node/one-edge GRIFT batch with no network I/O."""

    def run(self) -> None:
        alpha = _leaf("canary:leaf:alpha", "cold-boot-canary-alpha", is_open=True)
        omega = _leaf("canary:leaf:omega", "cold-boot-canary-omega", is_open=False)
        document = {
            "metadata": {"grift_version": "0"},
            "_reserved": {},
            "batches": [
                {
                    "batch_entity": {
                        "entity_id": _uid("canary:batch"),
                        "entity_type": "batch",
                        "name": "Cold-boot canary batch",
                        "dimensions": {},
                    },
                    "batch_node": {
                        "name": "Cold-boot canary batch",
                        "description": "Deterministic offline canary for the dev-validation cold-boot gate.",
                        "source": "plugin:grid_fixtures",
                    },
                    "nodes": [alpha, omega],
                    "edges": [
                        {
                            "entity": {
                                "entity_id": _uid("canary:edge"),
                                "entity_type": "edge",
                                "name": "canary link",
                                "dimensions": _DIMENSIONS,
                            },
                            "edge": {
                                "from_entity_id": alpha["entity"]["entity_id"],
                                "to_entity_id": omega["entity"]["entity_id"],
                                "edge_type": _EDGE_TYPE,
                                "properties": {},
                            },
                        }
                    ],
                }
            ],
        }
        self.submit_grift(document)
        self.summary = "Cold-boot canary: 2 leaf nodes + 1 link emitted offline."
        logger.info("[2d5f] cold-boot canary emitted its fixed offline batch")
