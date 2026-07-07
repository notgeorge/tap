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
from pathlib import Path

import pytest

from tap.plugin_testing import installed_plugin_slugs
from tap_grid.caller_context import CallerContext, set_caller_context

_TAP_TEST_KEY = "tap_test"

_REPO_ROOT = Path(__file__).resolve().parent


def _uninstalled_plugin_test_dirs() -> list[str]:
    """Test dirs of plugins present on disk but NOT installed in this stack.

    Plugin tests now live inside the package (``plugins/<slug>/tap_plugin/<slug>/
    tests/``, or the legacy ``plugins/<slug>/tests/`` for pre-package plugins) and
    import by installed identity (``tap_plugin.<slug>...``), so collecting them for a
    plugin this stack did not install would ImportError at collection time — the
    focused-session wound. The repo-root walk still descends into ``plugins/`` and
    collects every *installed* plugin's tests automatically (fail-safe discovery,
    no allow-list); this returns only the *uninstalled* ones for ``collect_ignore``,
    so their coverage is delegated to the all-plugins CI lane rather than red'ing the
    local run. See ``tap.plugin_testing`` and req-dev-validation-collection-complete.
    """
    plugins_dir = _REPO_ROOT / "plugins"
    if not plugins_dir.is_dir():
        return []
    installed = set(installed_plugin_slugs())
    ignore: list[str] = []
    for slug_dir in sorted(plugins_dir.iterdir()):
        if not slug_dir.is_dir() or slug_dir.name in installed:
            continue
        # Package-mode layout (tests inside the namespace package) + legacy layout.
        for tests in sorted(slug_dir.glob("tap_plugin/*/tests")):
            ignore.append(str(tests))
        legacy = slug_dir / "tests"
        if legacy.is_dir():
            ignore.append(str(legacy))
    return ignore


# Consumed by pytest at collection time (root-conftest `collect_ignore`).
collect_ignore = _uninstalled_plugin_test_dirs()


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


@pytest.fixture(autouse=True)
def default_caller_context(request):
    """Bind a CallerContext for the duration of each test.

    DB tests run as the `tap_test` actor — a `tap_admin` member that *holds* every
    capability — so the on-by-default service-boundary enforcement is satisfied
    without per-test boilerplate: the stateless backstop re-checks what the actor
    holds (req-tap-auth-policy-8), and tap_test holds it, so there is nothing to
    pre-authorize. Non-DB tests get a `None`-actor context (they do not reach the
    service boundary). A fresh batch_id is generated per test so writes stay
    isolated.
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

    actor = _resolve_test_actor()
    ctx = CallerContext(user=actor, batch_id=str(uuid.uuid7()))
    set_caller_context(ctx)
    try:
        yield ctx
    finally:
        set_caller_context(None)


@pytest.fixture(autouse=True)
def _service_write_hatch(request):
    """Permit direct-ORM model setup in tests (req-tap-auth-write-batch-routing).

    The write backstop fails a node/edge write that does not route through the
    service layer. Tests are the sanctioned below-service write zone (like
    migrations): a great deal of test setup legitimately does direct
    `.objects.create()` / `.save()` (including intentional model-level tests). So
    each test runs inside `unguarded_write()` by default — prod enforces the guard,
    and the static lint carries authoring-time detection of direct writes in app
    code. A test that needs to exercise the guard itself opts out with
    `@pytest.mark.enforce_write_guard`.
    """
    from tap_grid.write_guard import unguarded_write

    if request.node.get_closest_marker("enforce_write_guard"):
        yield
        return
    with unguarded_write():
        yield
