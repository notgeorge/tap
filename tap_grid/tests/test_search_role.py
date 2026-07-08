"""The least-privilege read-only search role (req-grid-search-readonly-role.sec, req-boot-search-role).

The suite runs ``search_readonly`` as the app role (tap/test_settings.py), so these tests
provision and exercise the real ``tap_gryphon_ro`` role authentically via ``SET ROLE`` — which
drops superuser and subjects the session to the role's grants — proving the provisioning is
correct without flipping the whole corpus onto the restricted role. A denied read integrates
with the broad 42501 Flaw (:mod:`tap_grid.db_permission_guard`): the database backstop and its
detection alert are validated together.
"""

from __future__ import annotations

import logging

import pytest
from django.conf import settings
from django.db import ProgrammingError, connections

from tap_grid.registry import get_model_class, list_entity_types
from tap_grid.search_role import _SPINE_TABLES, SEARCH_ROLE_NAME, provision_search_role, search_role_grant_tables

pytestmark = pytest.mark.django_db(transaction=True, databases=["default"])


def _provision() -> list[str]:
    conn = connections["default"]
    return provision_search_role(
        conn,
        password=settings.SEARCH_READONLY_PASSWORD,
        database=conn.settings_dict["NAME"],
        gucs=settings.SEARCH_ROLE_GUCS,
    )


class TestGrantSetDerivation:
    """The grant set is registry-derived — the validation-loop / completeness check."""

    def test_grant_set_covers_spine(self):
        tables = search_role_grant_tables()
        for spine in _SPINE_TABLES:
            assert spine in tables, f"spine table {spine} missing from the grant set"

    def test_grant_set_covers_every_registered_type(self):
        tables = set(search_role_grant_tables())
        for entity_type in list_entity_types():
            db_table = get_model_class(entity_type)._meta.db_table
            assert db_table in tables, f"registered type {entity_type} ({db_table}) not granted"

    def test_grant_set_excludes_the_user_table(self):
        # The non-grid table the seed vuln reached. It must never be in the grant set.
        assert "tap_user" not in search_role_grant_tables()


class TestProvisionedRoleEnforcement:
    """The provisioned role reads grid tables and is denied non-grid tables at the DB level."""

    def test_role_reads_a_grid_table(self):
        _provision()
        conn = connections["default"]
        try:
            with conn.cursor() as cur:
                cur.execute(f'SET ROLE "{SEARCH_ROLE_NAME}"')
                cur.execute("SELECT 1 FROM tap_entity LIMIT 1")  # granted spine table
                cur.fetchone()
        finally:
            with conn.cursor() as cur:
                cur.execute("RESET ROLE")
            conn.close()

    def test_role_is_denied_the_user_table_and_flaw_fires(self, caplog):
        _provision()
        conn = connections["default"]
        try:
            with caplog.at_level(logging.ERROR):
                with pytest.raises(ProgrammingError):
                    with conn.cursor() as cur:
                        cur.execute(f'SET ROLE "{SEARCH_ROLE_NAME}"')
                        cur.execute("SELECT 1 FROM tap_user LIMIT 1")  # non-grid → 42501
        finally:
            with conn.cursor() as cur:
                cur.execute("RESET ROLE")
            conn.close()

        flaws = [
            r for r in caplog.records if getattr(r, "message_data", {}).get("invariant_id") == "db_permission_denied"
        ]
        assert flaws, "a denied read by the least-privilege role must trip the 42501 Flaw"
        assert flaws[-1].message_data["flaw_tags"] == ["security"]

    def test_provision_is_idempotent(self):
        first = _provision()
        second = _provision()
        assert first == second

    def test_resource_gucs_are_role_pinned(self):
        """The resource bounds — including superuser-only temp_file_limit — are pinned on the role.

        temp_file_limit is a SUSET (superuser-only) parameter, so the non-superuser role cannot
        set it via connection options; it MUST be pinned on the role via ALTER ROLE … SET, applied
        at the role's login. This asserts the pin landed in pg_db_role_setting (the authentic proof
        that connection-time enforcement is superfluous for this GUC — the role carries it itself).
        """
        _provision()
        conn = connections["default"]
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT s.setconfig FROM pg_db_role_setting s "
                    "JOIN pg_roles r ON r.oid = s.setrole WHERE r.rolname = %s",
                    [SEARCH_ROLE_NAME],
                )
                row = cur.fetchone()
        finally:
            conn.close()
        assert row is not None, "role has no pinned settings — ALTER ROLE … SET did not land"
        pinned = dict(entry.split("=", 1) for entry in row[0])
        for guc_name, guc_value in settings.SEARCH_ROLE_GUCS.items():
            assert pinned.get(guc_name) == str(guc_value), (
                f"{guc_name} not pinned on the role (got {pinned.get(guc_name)!r}, " f"want {guc_value!r})"
            )
