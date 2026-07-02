"""GRIFT batch assembly for the samsite compliance collector.

Wraps the per-run node/edge envelopes in the one GRIFT document the collector
submits via ``CollectorBase.submit_grift``. Mirrors the boto3 collector's
batch shape (one batch per run, per-run uuid7 batch id, deterministic node/
edge ids inside).
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Any

_GRIFT_VERSION = "0"
COLLECTION_FORMAT = "tap.samsite.compliance-v0"


def assemble_batch(
    *,
    source: str,
    manifest_version: str,
    site_base_url: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Wrap node/edge envelopes in one GRIFT document for one run."""
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    now_iso = moment.isoformat().replace("+00:00", "Z")
    label = f"Samsite compliance collection {now_iso}"

    by_entity_type = Counter(env["entity"]["entity_type"] for env in nodes)
    description_data = {
        "schema_version": "v0",
        "manifest_version": manifest_version,
        "site_base_url": site_base_url,
        "counts": {
            "nodes": len(nodes),
            "edges": len(edges),
            "by_entity_type": dict(sorted(by_entity_type.items())),
        },
    }

    batch = {
        "batch_entity": {
            "entity_id": str(uuid.uuid4()),
            "entity_type": "batch",
            "name": label,
            "dimensions": {},
        },
        "batch_node": {
            "source": source,
            "name": label,
            "description": "Samsite signed /.well-known/ compliance artifacts.",
            "description_json": {
                "format": COLLECTION_FORMAT,
                "data": description_data,
            },
        },
        "nodes": nodes,
        "edges": edges,
    }
    return {
        "metadata": {"grift_version": _GRIFT_VERSION},
        "_reserved": {},
        "batches": [batch],
    }
