"""Real-backend health endpoint (``/healthz``).

A hand-rolled, dependency-free liveness/readiness probe that exercises the
*real* backends rather than merely confirming the process is listening. Each
dependency is probed independently and reported separately:

- **db** — a trivial ``SELECT 1`` over the default connection.
- **cache** — a real ``cache.set`` then ``cache.get`` round-trip whose value
  must match. This is the probe that catches the ``tap_cache``
  latent-provisioning fault (a missing DatabaseCache table 500s here loudly
  instead of at the first allauth login).
- **queue** — a light, best-effort reachability check of the DB-backed Steady
  Queue backend. Non-critical: an indeterminate result reports ``"unknown"``
  rather than failing the endpoint.

The response is JSON ``{"status": ..., "checks": {...}}``. HTTP 200 when every
*critical* probe (db, cache) is healthy; HTTP 503 otherwise. ``queue`` is
informational and never flips the overall status.

Mounted in ``tap/urls.py`` at the stable core path ``/healthz`` (the
conventional Kubernetes-style spelling), ahead of the tap_web catch-all. See
``docs/aar/2026-06-26-tap-cache-latent-provisioning.md`` and
``specs/spec-dev-validation.md`` (assembled-instance health surface).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from django.core.cache import cache
from django.db import DEFAULT_DB_ALIAS, connection, connections
from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache

logger = logging.getLogger(__name__)

# Probes whose failure makes the whole instance unhealthy (→ HTTP 503).
_CRITICAL_PROBES = ("db", "cache")


def _check_db() -> dict[str, str]:
    """Probe the default database with a trivial ``SELECT 1``."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:  # noqa: BLE001 — health probe reports, never raises.
        logger.warning("[6692] health: db probe failed: %s", exc)
        return {"status": "unhealthy", "detail": str(exc)}
    return {"status": "healthy"}


def _check_cache() -> dict[str, str]:
    """Round-trip a token through the real cache backend.

    A missing DatabaseCache table (the demo-day fault) surfaces here as an
    ``unhealthy`` cache probe instead of a 500 on the first real cache access.
    """
    probe_key = f"healthz-probe-{uuid.uuid4()}"
    token = uuid.uuid4().hex
    try:
        cache.set(probe_key, token, timeout=30)
        observed = cache.get(probe_key)
        cache.delete(probe_key)
    except Exception as exc:  # noqa: BLE001 — health probe reports, never raises.
        logger.warning("[af65] health: cache probe failed: %s", exc)
        return {"status": "unhealthy", "detail": str(exc)}
    if observed != token:
        logger.warning("[a7fd] health: cache round-trip mismatch (set != get)")
        return {"status": "unhealthy", "detail": "cache set/get round-trip mismatch"}
    return {"status": "healthy"}


def _check_queue() -> dict[str, str]:
    """Best-effort reachability of the DB-backed Steady Queue backend.

    Non-critical and deliberately light: confirms the queue's backing tables
    are present on the default database. Anything indeterminate (or any error)
    reports ``"unknown"`` rather than failing the endpoint — we do not overreach
    into worker-liveness probing here.
    """
    try:
        table_names = set(connections[DEFAULT_DB_ALIAS].introspection.table_names())
        if "steady_queue_job" in table_names:
            return {"status": "healthy"}
        return {"status": "unknown", "detail": "steady_queue tables not found"}
    except Exception as exc:  # noqa: BLE001 — non-critical, never fails the probe.
        logger.info("[7d0b] health: queue probe indeterminate: %s", exc)
        return {"status": "unknown", "detail": str(exc)}


@never_cache
def health_view(request: HttpRequest) -> JsonResponse:
    """Return the instance health as JSON with a 200/503 status code.

    Args:
        request: The incoming request (unused; the endpoint takes no input).

    Returns:
        ``JsonResponse`` with ``{"status": "healthy"|"unhealthy", "checks":
        {...}}``. Status is 200 when all critical probes (db, cache) are
        healthy, else 503.
    """
    checks: dict[str, dict[str, str]] = {
        "db": _check_db(),
        "cache": _check_cache(),
        "queue": _check_queue(),
    }
    healthy = all(checks[name]["status"] == "healthy" for name in _CRITICAL_PROBES)
    payload: dict[str, Any] = {
        "status": "healthy" if healthy else "unhealthy",
        "checks": checks,
    }
    return JsonResponse(payload, status=200 if healthy else 503)
