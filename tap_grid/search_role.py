"""Provisioning for the least-privilege read-only search role (``tap_gryphon_ro``).

``req-grid-search-readonly-role.sec`` + ``req-boot-search-role``. The ``search_readonly``
connection authenticates as this role so a Gryphon read is constrained at the *database*
level to the grid: ``SELECT`` on exactly the registry-derived grid model tables plus the
spine, and nothing else. It is the defense-in-depth backstop beneath the in-code field-path
allowlist (``req-grid-traversal-lang-relation-guard.sec``): if an in-code guard ever leaked,
a read reaching a non-grid table (e.g. ``tap_user``) is denied by PostgreSQL with SQLSTATE
42501, which trips the broad permission-denied Flaw (:mod:`tap_grid.db_permission_guard`).

The grant set is **derived from the registry**, not hand-maintained, so it cannot drift from
the model layer and a newly-added grid table is covered automatically (and a non-grid table
is never granted — the fail-safe direction).

Utility statements (``CREATE ROLE`` / ``ALTER ROLE … SET``) do not accept bind parameters, so
identifiers and literals are validated against strict charsets and safe-quoted rather than
parameterized. The provisioning connection is the table-owning application role (it holds the
grant + CREATEROLE authority); the read-only role never gains privilege-granting authority.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from django.db import InternalError, transaction

logger = logging.getLogger(__name__)

SEARCH_ROLE_NAME = "tap_gryphon_ro"

# `tap_gryphon_ro` lives in PostgreSQL's CLUSTER-GLOBAL role catalog (pg_authid), shared by every
# database in the server. Concurrent reconcilers of the same role tuple — parallel xdist test
# workers (each on its own test database but ONE shared cluster) or concurrent app-instance boots
# (hot-swap / blue-green against a shared cluster) — collide as "tuple concurrently updated". The
# conflict is benign and self-clearing, so provisioning retries (see req-grid-db-role-concurrency.sec).
_ROLE_PROVISION_MAX_ATTEMPTS = 5
_CONCURRENT_UPDATE_MARKER = "tuple concurrently updated"

# Spine tables the executor always reads, independent of the registry: the Entity spine, the
# EntityType catalog, the Edge table, and the Dimension table.
_SPINE_TABLES = ("tap_entity", "tap_entity_type", "tap_edge", "tap_dimension")

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# GUC values are simple tokens (e.g. "30s", "64MB", "1GB", "on"); reject anything else.
_GUC_VALUE_RE = re.compile(r"^[A-Za-z0-9]+$")


def _validate_identifier(name: str) -> str:
    """Return ``name`` if it is a safe SQL identifier, else raise ValueError."""
    if not _IDENT_RE.match(name):
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return name


def _quote_literal(value: str) -> str:
    """Single-quote a SQL string literal, escaping embedded quotes."""
    return "'" + value.replace("'", "''") + "'"


def _validate_guc_value(value: str) -> str:
    if not _GUC_VALUE_RE.match(value):
        raise ValueError(f"unsafe GUC value: {value!r}")
    return value


def search_role_grant_tables() -> list[str]:
    """Tables the read-only search role may ``SELECT``: spine + every registered grid table.

    Derived from the type registry so the set tracks the model layer automatically. Every
    returned name is a validated identifier (registry/model-derived, but validated defensively
    because it is interpolated into DDL).
    """
    from tap_grid.registry import get_model_class, list_entity_types

    tables: set[str] = set(_SPINE_TABLES)
    for entity_type in list_entity_types():
        try:
            tables.add(get_model_class(entity_type)._meta.db_table)
        except KeyError:
            continue
    return sorted(_validate_identifier(t) for t in tables)


def provision_search_role(
    connection: Any,
    *,
    password: str,
    database: str,
    gucs: dict[str, str],
    tables: list[str] | None = None,
) -> list[str]:
    """Idempotently provision ``tap_gryphon_ro`` using ``connection`` (the owning role).

    Creates/updates the role, resets its table privileges and grants ``SELECT`` on exactly the
    allowlist (spine + registry grid tables), grants ``CONNECT``/``USAGE``, and pins the
    resource-bound GUCs on the role. Re-running reconciles the grants to the current registry
    set. Returns the granted table list (for logging / the validation loop).

    Args:
        connection: A Django DB connection whose role owns the tables and can CREATE ROLE.
        password: The login password to set on the role.
        database: The database name to grant CONNECT on.
        gucs: ``{guc_name: value}`` to pin via ``ALTER ROLE … SET`` (values are validated).
        tables: Grant-set override (defaults to :func:`search_role_grant_tables`).
    """
    role = _validate_identifier(SEARCH_ROLE_NAME)
    db = _validate_identifier(database)
    grant_tables = tables if tables is not None else search_role_grant_tables()
    grant_tables = [_validate_identifier(t) for t in grant_tables]
    pw = _quote_literal(password)

    def _reconcile() -> None:
        # `transaction.atomic` opens a SAVEPOINT when the caller is already in a transaction
        # (e.g. a test), so a retry after a concurrent-update rollback does not poison the
        # caller's surrounding transaction; in autocommit (boot) it is a plain atomic reconcile.
        with transaction.atomic(using=connection.alias), connection.cursor() as cur:
            # 1. Ensure the role exists with LOGIN + password (idempotent).
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [SEARCH_ROLE_NAME])
            if cur.fetchone() is None:
                cur.execute(f'CREATE ROLE "{role}" LOGIN PASSWORD {pw}')
            else:
                cur.execute(f'ALTER ROLE "{role}" LOGIN PASSWORD {pw}')

            # 2. Reset table privileges, then grant SELECT on exactly the allowlist. REVOKE ALL
            #    first so a table dropped from the registry loses access on the next reconcile.
            cur.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{role}"')
            cur.execute(f'GRANT CONNECT ON DATABASE "{db}" TO "{role}"')
            cur.execute(f'GRANT USAGE ON SCHEMA public TO "{role}"')
            for table in grant_tables:
                cur.execute(f'GRANT SELECT ON "{table}" TO "{role}"')

            # 3. Pin the resource-bound GUCs on the role (req-grid-search-readonly-role.sec-6).
            for guc_name, guc_value in gucs.items():
                gname = _validate_identifier(guc_name)
                gval = _validate_guc_value(str(guc_value))
                cur.execute(f'ALTER ROLE "{role}" SET {gname} = {_quote_literal(gval)}')

    # Retry on the benign cluster-global concurrency conflict (req-grid-db-role-concurrency.sec).
    # An advisory lock cannot serialize this: advisory locks are per-DATABASE, but the contended
    # role is cluster-global — so retry is the correct tool.
    for attempt in range(1, _ROLE_PROVISION_MAX_ATTEMPTS + 1):
        try:
            _reconcile()
            break
        except InternalError as exc:
            if _CONCURRENT_UPDATE_MARKER not in str(exc) or attempt == _ROLE_PROVISION_MAX_ATTEMPTS:
                raise
            logger.warning(
                "[8db6] search-role provisioning hit a concurrent cluster-global role update "
                "(attempt %d/%d) — retrying (req-grid-db-role-concurrency.sec)",
                attempt,
                _ROLE_PROVISION_MAX_ATTEMPTS,
            )
            time.sleep(0.02 * attempt)

    logger.info(
        "[5ac3] provisioned search role %s with SELECT on %d tables",
        SEARCH_ROLE_NAME,
        len(grant_tables),
    )
    return grant_tables
