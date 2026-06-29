"""tap_health startup system check — the boot-time provisioning guard.

req-tap-health-bootcheck (spec-tap-health-v0.md). Moved here from
`tap_boot/checks.py` (req-tap-health-service-2): it is a health/provisioning
check by nature, so the health app owns it. It stays a `Tags.database` check
firing at `migrate` / `check --database`; only its home and id namespace
(`tap_boot.E001` → `tap_health.E001`) moved.

Guards the latent-provisioning fault that took down a demo: the `DatabaseCache`
table (`settings.CACHES` default `LOCATION`) is created by
`manage.py createcachetable` — outside migrations — so a fresh instance can
stand up "successfully" yet 500 on the first cache access. Registered in
`TapHealthConfig.ready` by importing this module; the DB access happens later,
when the check runs, so it does not breach the no-DB-in-`ready()` rule.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.checks import Error, Tags, register
from django.db import DEFAULT_DB_ALIAS, connections

DATABASE_CACHE_BACKEND = "django.core.cache.backends.db.DatabaseCache"


@register(Tags.database)
def check_database_cache_table(app_configs: Any, **kwargs: Any) -> list[Error]:
    """Assert the DatabaseCache table exists when DatabaseCache is configured.

    Returns a single `tap_health.E001` Error when the configured cache table is
    missing; otherwise an empty list. No-ops when the default cache backend is
    not DatabaseCache, or when no permitted DB alias is available.
    """
    default_cache = settings.CACHES.get("default", {})
    if default_cache.get("BACKEND") != DATABASE_CACHE_BACKEND:
        return []

    databases = kwargs.get("databases")
    if not databases or DEFAULT_DB_ALIAS not in databases:
        return []

    table = default_cache.get("LOCATION")
    connection = connections[DEFAULT_DB_ALIAS]
    if table in connection.introspection.table_names():
        return []

    return [
        Error(
            f'The default cache backend is DatabaseCache but its table "{table}" '
            f"does not exist on the {DEFAULT_DB_ALIAS!r} database.",
            hint=(
                "Run `manage.py createcachetable` to provision it. This is wired "
                "into docker/entrypoint.sh (before migrate, so this check passes "
                "during migrate's check phase); if you hit this on a fresh "
                "instance, that provisioning step did not run."
            ),
            id="tap_health.E001",
        )
    ]
