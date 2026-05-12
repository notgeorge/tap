"""CollectorConfig — per-run configuration passed to a collector class.

req-tap-cares-collector-config (spec-tap-cares-collector.md).

v0 shape is intentionally minimal: just the two JSON-safe IDs the Django Tasks
task receives. Future per-instance Collector configuration is deferred. Frozen
so a collector module cannot mutate its config mid-run.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CollectorConfig:
    collector_entity_id: UUID
    collection_job_entity_id: UUID
