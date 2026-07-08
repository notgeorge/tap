"""Proof of the broad insufficient-privilege detection backstop (req-grid-db-permission-flaw.sec).

PostgreSQL raises SQLSTATE 42501 (``insufficient_privilege``) whenever a role is denied a
statement it is not granted. That denial is the *integrity* half — it stops the read/write.
On its own it is silent. This guard adds the *detection* half: a broad `security` Flaw fires
on a 42501 on *any* connection before the error propagates, so a leak past the in-code guards
that the database catches becomes a loud, response-triggering alert.

Two levels of proof: an authentic denial (``SET ROLE`` to a no-privilege role, then read a
table it is not granted) exercises the real execute-wrapper path end to end; a mechanism test
pins the SQLSTATE chain-walk without needing a role.
"""

from __future__ import annotations

import logging

import pytest
from django.db import ProgrammingError, connections

from tap_grid.db_permission_guard import _is_permission_denied

_NOPERM_ROLE = "tap_test_noperm_42501"


class _FakePgError(Exception):
    """Stand-in psycopg error carrying a SQLSTATE, for the mechanism test."""

    def __init__(self, sqlstate: str) -> None:
        super().__init__(f"pg error {sqlstate}")
        self.sqlstate = sqlstate


def test_is_permission_denied_walks_the_cause_chain():
    """42501 is detected whether it is the raised error or a wrapped cause/context."""
    assert _is_permission_denied(_FakePgError("42501")) is True
    # Django wraps the psycopg error as a ProgrammingError with no sqlstate of its own.
    wrapped = ProgrammingError("permission denied")
    wrapped.__cause__ = _FakePgError("42501")
    assert _is_permission_denied(wrapped) is True
    # A different SQLSTATE (25006 read-only-write) is not this guard's concern.
    assert _is_permission_denied(_FakePgError("25006")) is False
    assert _is_permission_denied(ProgrammingError("some other error")) is False


@pytest.mark.django_db(transaction=True, databases=["default"])
class TestAuthenticDenial:
    """An actual 42501 from a real role, through the real execute-wrapper."""

    @staticmethod
    def _read_as_noperm_role() -> None:
        conn = connections["default"]
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"DROP ROLE IF EXISTS {_NOPERM_ROLE}")
                cursor.execute(f"CREATE ROLE {_NOPERM_ROLE} NOLOGIN")
                cursor.execute(f"SET ROLE {_NOPERM_ROLE}")
                # The no-privilege role is not granted SELECT on the user table (nor is
                # PUBLIC), so PostgreSQL denies this read with SQLSTATE 42501.
                cursor.execute("SELECT 1 FROM tap_user LIMIT 1")
        finally:
            # Reset + drop on a fresh connection state; RESET ROLE returns to the test
            # superuser so the DROP is permitted.
            with conn.cursor() as cursor:
                cursor.execute("RESET ROLE")
                cursor.execute(f"DROP ROLE IF EXISTS {_NOPERM_ROLE}")
            conn.close()

    def test_denied_read_is_rejected(self):
        with pytest.raises(ProgrammingError):
            self._read_as_noperm_role()

    def test_denied_read_emits_security_flaw(self, caplog):
        with caplog.at_level(logging.ERROR):
            with pytest.raises(ProgrammingError):
                self._read_as_noperm_role()

        flaws = [
            r
            for r in caplog.records
            if getattr(r, "message_code", None) == "FLAW"
            and getattr(r, "message_data", {}).get("invariant_id") == "db_permission_denied"
        ]
        assert flaws, "expected a db_permission_denied FLAW from the 42501 guard"
        md = flaws[-1].message_data
        assert md["flaw_tags"] == ["security"]
        assert md["handling"] == "abort_operation"

    def test_normal_read_emits_no_flaw(self, caplog):
        with caplog.at_level(logging.ERROR):
            conn = connections["default"]
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()

        flaws = [
            r
            for r in caplog.records
            if getattr(r, "message_code", None) == "FLAW"
            and getattr(r, "message_data", {}).get("invariant_id") == "db_permission_denied"
        ]
        assert not flaws, "a granted read must not emit a permission-denied FLAW"
