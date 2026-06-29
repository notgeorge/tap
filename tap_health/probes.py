"""Core (platform) health probes: db, cache, queue.

req-tap-health-probes (spec-tap-health-v0.md). Registered from
`TapHealthConfig.ready()`. Each probe exercises a real backend and returns a
`ProbeResult`; it never raises (the service isolates exceptions anyway, but
probes report cleanly with a stable `code`).

These are below the service boundary — a `SELECT 1`, a cache round-trip, a
table-name introspection — so they resolve no actor and stay runnable when
auth/DB is broken (req-tap-health-probe-actor).
"""

from __future__ import annotations

import logging
import uuid

from django.core.cache import cache
from django.db import DEFAULT_DB_ALIAS, connection, connections

from tap_health.results import ProbeResult

logger = logging.getLogger(__name__)


def probe_db() -> ProbeResult:
    """Trivial `SELECT 1` over the default connection."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:  # noqa: BLE001 — report, never raise.
        logger.warning("[8c9e] health: db probe failed: %s", exc)
        return ProbeResult.unhealthy("db.query_failed", detail=str(exc))
    return ProbeResult.healthy()


def probe_cache() -> ProbeResult:
    """Real `cache.set` → `cache.get` round-trip; the value must match.

    A missing DatabaseCache table surfaces here as `unhealthy` with the
    `relation "..." does not exist` detail instead of a 500 on first cache use.
    """
    probe_key = f"healthz-probe-{uuid.uuid4()}"
    token = uuid.uuid4().hex
    try:
        cache.set(probe_key, token, timeout=30)
        observed = cache.get(probe_key)
        cache.delete(probe_key)
    except Exception as exc:  # noqa: BLE001 — report, never raise.
        logger.warning("[f3b4] health: cache probe failed: %s", exc)
        return ProbeResult.unhealthy("cache.unavailable", detail=str(exc))
    if observed != token:
        logger.warning("[bd40] health: cache round-trip mismatch (set != get)")
        return ProbeResult.unhealthy("cache.roundtrip_mismatch", detail="cache set/get round-trip mismatch")
    return ProbeResult.healthy()


def probe_queue() -> ProbeResult:
    """Best-effort reachability of the DB-backed Steady Queue backend.

    Non-critical: an indeterminate result is `unknown`, never `unhealthy`. It
    does not probe worker liveness.
    """
    try:
        table_names = set(connections[DEFAULT_DB_ALIAS].introspection.table_names())
    except Exception as exc:  # noqa: BLE001 — non-critical; report unknown.
        logger.info("[bb90] health: queue probe indeterminate: %s", exc)
        return ProbeResult.unknown("queue.indeterminate", detail=str(exc))
    if "steady_queue_job" in table_names:
        return ProbeResult.healthy()
    return ProbeResult.unknown("queue.tables_missing", detail="steady_queue tables not found")


__all__ = ["probe_db", "probe_cache", "probe_queue"]
