"""Broad detection backstop: a statement denied by PostgreSQL for insufficient privilege.

SQLSTATE 42501 (``insufficient_privilege``) is raised whenever a database role is denied
a read or write it is not granted. This is the **broad** analog of
:mod:`tap_grid.search_readonly_guard` (which is scoped to the ``search_readonly`` alias and
the read-only-write SQLSTATE 25006): this guard fires for a 42501 on *any* connection,
alias, or role (``req-grid-db-permission-flaw.sec``).

A 42501 is the highest-value signal in the Gryphon defense-in-depth set. The field-path
allowlist (``req-grid-traversal-lang-relation-guard.sec``) and the table-scope guard
(``req-grid-traversal-exec-table-guard.sec``) stop an out-of-scope read in application
code; the least-privilege search role (``req-grid-search-readonly-role.sec``) is the
database backstop beneath them. If a 42501 ever fires, it means an in-code guard *leaked*
and the database caught what the application did not — a should-never-happen event worth a
human's (eventually an on-call AI's) attention.

Wired on ``connection_created`` (``tap_grid/apps.py``) **unconditionally** — on every
connection, not just one alias — so it forward-proofs the day the ``tap`` role loses
god-mode or a least-privilege role is introduced: any new privilege violation trips the
same Flaw with no per-role wiring. It adds a bare ``try/except`` to the execute path; the
happy path pays only that, and the SQLSTATE inspection runs only when a statement has
already failed.

Honest caveat (``req-sec-honest-risk``): this catches only Django-ORM connections. A direct
psycopg / psql / external-tool path bypasses it — that is pgaudit / DB-log territory, a
later backstop.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# SQLSTATE 42501 = insufficient_privilege. PostgreSQL raises this for any statement a role
# is not granted (SELECT on an ungranted table, a denied write, etc.). Django wraps the
# psycopg error (which carries `.sqlstate`) as a ProgrammingError (whose own `.sqlstate` is
# None), so the cause/context chain must be walked — the same shape as the 25006 guard.
_INSUFFICIENT_PRIVILEGE_SQLSTATE = "42501"


def _is_permission_denied(exc: BaseException) -> bool:
    """True iff ``exc`` — or any error in its cause/context chain — is a PG 42501.

    Walks ``__cause__``/``__context__`` (cycle-guarded) because Django re-wraps the psycopg
    error (which carries ``sqlstate``) as a ``ProgrammingError`` (which does not).
    """
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if getattr(cur, "sqlstate", None) == _INSUFFICIENT_PRIVILEGE_SQLSTATE:
            return True
        cur = cur.__cause__ or cur.__context__
    return False


def _db_permission_guard(
    execute: Any,
    sql: str,
    params: Any,
    many: bool,  # noqa: FBT001
    context: Any,
) -> Any:
    """execute_wrapper that raises a security Flaw on a 42501 permission denial.

    Runs the statement; if it fails with SQLSTATE 42501, emits the Flaw (the alert) and
    re-raises the original error so the denial stands and the caller's existing error
    handling is unchanged.
    """
    try:
        return execute(sql, params, many, context)
    except Exception as exc:
        if _is_permission_denied(exc):
            # Import here to keep tap_grid import-time free of tap.flaws and to avoid any
            # import cycle; the cost is paid only on the failure path.
            from tap.flaws import report_db_permission_denied

            alias = getattr(getattr(context, "connection", None), "alias", None)
            statement_head = sql.strip().split(None, 1)[0].upper() if sql.strip() else "<empty>"
            report_db_permission_denied(
                message=(
                    "statement denied by PostgreSQL for insufficient privilege "
                    f"(SQLSTATE {_INSUFFICIENT_PRIVILEGE_SQLSTATE}) on connection {alias!r}"
                ),
                logger=logger,
                sqlstate=_INSUFFICIENT_PRIVILEGE_SQLSTATE,
                statement_head=statement_head,
                db_alias=alias,
            )
        raise


def install_db_permission_guard(connection: Any, **_kwargs: Any) -> None:
    """Attach the 42501 permission-denial detection wrapper to every DB connection.

    Idempotent, and — unlike the read-only write guard — **not** scoped to any alias: a
    permission denial on any connection is a should-never-happen event worth surfacing.
    Wired to ``connection_created`` so every connection (request, task, command, shell)
    carries the guard without a per-callsite registration step.
    """
    if _db_permission_guard not in connection.execute_wrappers:
        connection.execute_wrappers.append(_db_permission_guard)
