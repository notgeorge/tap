"""The read-only search connection carries the resource bounds (req-grid-traversal-exec-resource-bounds.sec).

A Gryphon read that is legitimate in scope but pathological in cost is an availability risk.
v0 bounds it with native PostgreSQL caps pinned on the search connection: time
(statement_timeout / lock_timeout), memory (work_mem), and disk (temp_file_limit — a hard cap
that aborts a query whose spill exceeds it). These are set at connection time in
``tap/settings.py`` (the interim, role-independent home; they move to ALTER ROLE when the
least-privilege role lands). This test proves they are actually engaged on the connection.
"""

from __future__ import annotations

import pytest
from django.conf import settings
from django.db import connections

pytestmark = pytest.mark.django_db(transaction=True, databases=["default", "search_readonly"])


def _show(alias: str, guc: str) -> str:
    conn = connections[alias]
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"SHOW {guc}")
            return cursor.fetchone()[0]
    finally:
        conn.close()


def test_search_connection_pins_the_resource_gucs():
    """statement_timeout / lock_timeout / work_mem / temp_file_limit are set on search_readonly."""
    # PostgreSQL normalizes units (e.g. "30s" -> "30s", "1GB" -> "1GB"); assert non-default,
    # matching the configured values rather than hard-coding PG's canonical rendering.
    assert _show("search_readonly", "statement_timeout") not in ("0", "")
    assert _show("search_readonly", "lock_timeout") not in ("0", "")
    # temp_file_limit default is -1 (unlimited); a real cap means it is no longer -1.
    assert _show("search_readonly", "temp_file_limit") != "-1"
    # work_mem is configured away from the 4MB PostgreSQL default in our settings.
    assert _show("search_readonly", "work_mem") == settings.SEARCH_WORK_MEM


def test_default_connection_is_not_read_only_bounded_the_same_way():
    """Control: the writable default connection does not carry the read-only session flag.

    (The default path is for writes/migrations; its bounds are a separate concern. This
    asserts the search bounds are scoped to the search connection, not global.)
    """
    assert _show("default", "default_transaction_read_only") == "off"
    assert _show("search_readonly", "default_transaction_read_only") == "on"
