"""Tests for the grid-tables probe (req-tap-health-probes-8).

The probe evaluates the fail-closed grid-integrity invariant continuously: every
model classified as TAP-managed has its table in the database. It shares one
implementation of "classified but absent" with search-role provisioning — the
point being that the same fact is never derived twice.
"""

from __future__ import annotations

from unittest import mock

import pytest

from tap_grid.health import probe_grid_tables
from tap_health.results import ProbeStatus

pytestmark = pytest.mark.django_db


@pytest.mark.spec("req-tap-health-probes-8")
def test_real_migrated_tables_are_not_reported_absent():
    """The helper, against the real database, with a controlled declared set.

    Deliberately NOT asserting that the *global* classified set is fully present:
    the test suite defines throwaway `BaseModel` subclasses (fixture models for
    validation tests) which are classified like any other domain model but have no
    migration, so in a full-suite process the global set legitimately contains
    tableless models. That is a test-process artifact — a real instance has no such
    classes — and it is the same case search-role provisioning already skips. So
    this pins the helper's behaviour on models that really are migrated.
    """
    from django.db import connection

    from tap_grid.grid_tables import classified_but_absent
    from tap_grid.models import Entity, EntityType

    real_tables = [Entity._meta.db_table, EntityType._meta.db_table]
    with connection.cursor() as cursor:
        assert classified_but_absent(cursor, declared=real_tables) == []


@pytest.mark.spec("req-tap-health-probes-8")
def test_healthy_when_nothing_is_absent():
    with mock.patch("tap_grid.grid_tables.classified_but_absent", return_value=[]):
        result = probe_grid_tables()
    assert result.status is ProbeStatus.HEALTHY
    assert result.context["classified_tables"] > 0


@pytest.mark.spec("req-tap-health-probes-8")
def test_absent_classified_table_is_unhealthy():
    # The plugin-loading race's fingerprint: a registered type whose migration
    # never ran. The probe must name the table, not just fail.
    with mock.patch("tap_grid.grid_tables.classified_but_absent", return_value=["tap_never_migrated"]):
        result = probe_grid_tables()
    assert result.status is ProbeStatus.UNHEALTHY
    assert result.code == "grid.tables_absent"
    assert result.context["absent_tables"] == ["tap_never_migrated"]
    assert "tap_never_migrated" in (result.detail or "")


@pytest.mark.spec("req-tap-health-probes-8")
def test_probe_reports_rather_than_raising():
    with mock.patch("tap_grid.grid_tables.classified_but_absent", side_effect=RuntimeError("cursor exploded")):
        result = probe_grid_tables()
    assert result.status is ProbeStatus.UNHEALTHY
    assert result.code == "grid.tables_check_failed"


@pytest.mark.spec("req-tap-health-probes-8")
def test_probe_reads_without_a_caller_context():
    """The probe resolves no actor, so it must not need `grid.read` in a context.

    It passes today either way (the read guard allows a context-free read), so the
    explicit `unguarded_read()` bypass is what keeps it passing if health is ever
    served from inside a request, where a context IS bound.
    """
    from tap_grid.caller_context import CallerContext, set_caller_context

    set_caller_context(CallerContext(user=None))
    try:
        result = probe_grid_tables()  # real SQL — the guard must not block it
    finally:
        set_caller_context(None)
    # The claim is that the READ completed under a bound context, not what the table
    # set contained (a full-suite process carries tableless fixture models). A guard
    # rejection would surface as the probe's caught-exception code.
    assert result.code != "grid.tables_check_failed"


@pytest.mark.spec("req-grid-table-classification.sec-6")
def test_shares_one_derivation_with_search_role_provisioning():
    """`classified_but_absent` has exactly one implementation, used by both.

    Provisioning skips absent tables before granting; this probe reports them. If
    either grew its own pg_tables query they could disagree about which tables
    exist — the derive-the-same-fact-twice class this probe exists to catch.
    """
    import inspect

    from tap_grid import search_role

    source = inspect.getsource(search_role.provision_search_role)
    assert "classified_but_absent" in source
    assert "FROM pg_tables" not in source
