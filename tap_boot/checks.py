"""tap_boot startup system checks.

These run through Django's system check framework, so they fail loud at
startup (during ``migrate`` and any explicit ``manage.py check --database
<alias>``) rather than at the first request that trips over the missing
provisioning. The check here guards the latent-provisioning fault that took
down a demo: the ``DatabaseCache`` table (``settings.CACHES`` default
``LOCATION``) is created by ``manage.py createcachetable`` — outside
migrations — so a fresh instance can stand up "successfully" yet 500 on the
first cache access (e.g. allauth login rate-limiting).

Registration happens in :meth:`tap_boot.apps.TapBootConfig.ready` by importing
this module. Importing only *registers* the check function; the DB access
happens later, when the check actually runs — so this does not violate TAP's
"no DB access in ``AppConfig.ready()``" rule.

The check is tagged :data:`django.core.checks.Tags.database`, which means it is
skipped on ordinary management commands and only runs when a database is in
play (``migrate`` / ``check --database``). See
``specs/spec-dev-validation.md`` and the AAR
``docs/aar/2026-06-26-tap-cache-latent-provisioning.md``.
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

    When the default cache backend is :data:`DATABASE_CACHE_BACKEND`, the table
    named by its ``LOCATION`` must exist; the first cache access otherwise fails
    with ``relation "<table>" does not exist``. This is a database-tagged check,
    so Django passes ``databases`` (in ``kwargs``) listing the aliases the check
    is allowed to touch; the check no-ops when the default alias is not among
    them (e.g. a non-DB command).

    Args:
        app_configs: App configs Django passes to system checks (unused here).
        **kwargs: System-check keyword args; ``databases`` (a list of permitted
            DB aliases) is read from here — ``None``/empty means no database is
            available and the check is skipped.

    Returns:
        A list with a single :class:`~django.core.checks.Error` when the
        configured cache table is missing, else an empty list.
    """
    default_cache = settings.CACHES.get("default", {})
    if default_cache.get("BACKEND") != DATABASE_CACHE_BACKEND:
        return []

    # Database-tagged checks receive the permitted aliases; without the default
    # alias we cannot (and must not) introspect, so skip rather than guess.
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
                "into docker/entrypoint.sh (next to migrate); if you hit this on a "
                "fresh instance, that provisioning step did not run."
            ),
            id="tap_boot.E001",
        )
    ]
