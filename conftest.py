"""Root-level pytest configuration and fixtures.

Auth enforcement is on by default at the service boundary (req-tap-auth-policy):
every service-layer read/write requires a named, authorized actor — `User=None`
is rejected. So the test suite must run as a real authorized actor. We use the
`tap_test` built-in program actor (a member of `tap_admin`, holding every
capability), bound into the `CallerContext` for the duration of each DB test.

Two pieces make this cheap and robust:

- `django_db_setup` is extended to run the auth bootstrap (`sync_auth`) once per
  session, so `tap_test` + capabilities + groups exist as committed baseline data
  that every non-transactional test sees for free.
- `default_caller_context` (autouse) binds a `tap_test` `CallerContext` for each
  DB test. For the rare transactional test (which flushes the baseline), it
  re-runs the idempotent `sync_auth` to recreate the actor. Non-DB unit tests get
  a `None`-actor context — they do not cross the service boundary.

Tests that deliberately verify no-actor / unauthorized behaviour set the context
themselves (e.g. `set_caller_context(None)` or a deliberately unprivileged actor).
"""

import uuid

import pytest

from tap_grid.caller_context import CallerContext, set_caller_context

_TAP_TEST_KEY = "tap_test"


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):  # noqa: PT004
    """Seed the auth bootstrap once per session.

    Runs after pytest-django creates+migrates the test DB. The committed
    capabilities/groups/built-in actors become the baseline every test inherits.
    """
    with django_db_blocker.unblock():
        from tap_auth.sync import sync_auth

        sync_auth()


def _db_fixture_name(request) -> str | None:
    """Return the db fixture this test uses ('db'/'transactional_db'), or None.

    Returning the specific name lets the autouse context fixture `getfixturevalue`
    it — which both enables DB access and orders this fixture *after* the db
    fixture, avoiding "Database access not allowed".
    """
    if "transactional_db" in request.fixturenames:
        return "transactional_db"
    if "db" in request.fixturenames:
        return "db"
    marker = request.node.get_closest_marker("django_db")
    if marker is not None:
        return "transactional_db" if marker.kwargs.get("transaction") else "db"
    return None


def _resolve_test_actor():
    """Return the tap_test actor, re-running the idempotent sync if a
    transactional test flushed the seeded baseline."""
    from django.contrib.auth import get_user_model

    user_model = get_user_model()
    actor = user_model.objects.filter(tap_builtin_key=_TAP_TEST_KEY).first()
    if actor is None:
        from tap_auth.sync import sync_auth

        sync_auth()
        actor = user_model.objects.get(tap_builtin_key=_TAP_TEST_KEY)
    return actor


# Capabilities pre-authorized for the test session so a test that calls a
# service chokepoint directly (e.g. write_batch) — not via a decorated verb —
# finds a recorded decision. These are REAL authorizations: tap_test is a
# tap_admin member that holds them; we are not bypassing the gate, only
# recording up front that this admin session authorized them.
_SESSION_CAPS = ("grid.read", "grid.write", "grid.delete")


@pytest.fixture(autouse=True)
def default_caller_context(request):
    """Bind a CallerContext for the duration of each test.

    DB tests run as the authorized `tap_test` actor so the on-by-default
    service-boundary enforcement is satisfied without per-test boilerplate, and
    the standard admin capabilities are pre-authorized in an ambient scope so
    direct-chokepoint calls resolve. Decorated verbs still open their own scopes.
    Non-DB tests get a `None`-actor context (they do not reach the service
    boundary). A fresh batch_id is generated per test so writes stay isolated.
    """
    db_fixture = _db_fixture_name(request)
    if db_fixture is None:
        ctx = CallerContext(user=None, batch_id=str(uuid.uuid7()))
        set_caller_context(ctx)
        yield ctx
        set_caller_context(None)
        return

    # Enable DB access and order this fixture after the db fixture before querying.
    request.getfixturevalue(db_fixture)
    from tap_auth import policy

    actor = _resolve_test_actor()
    ctx = CallerContext(user=actor, batch_id=str(uuid.uuid7()))
    set_caller_context(ctx)
    token = policy.push_authorization_scope()
    for cap in _SESSION_CAPS:
        policy.authorize(ctx, cap)
    try:
        yield ctx
    finally:
        policy.pop_authorization_scope(token)
        set_caller_context(None)
