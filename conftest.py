"""Root-level pytest configuration and fixtures.

The `default_caller_context` fixture is applied automatically to every test
so that FLIP-enabled models can be saved without manually setting up a
CallerContext in every test. Tests that need to verify no-context behaviour
(e.g. NoBatchContextError) can call set_caller_context(None) to opt out.
"""

import uuid

import pytest

from tap_grid.caller_context import CallerContext, set_caller_context


@pytest.fixture(autouse=True)
def default_caller_context():
    """Provide a test-scoped CallerContext for the duration of each test.

    A fresh batch_id is generated per test so writes stay isolated.
    Tests verifying NoBatchContextError should call set_caller_context(None)
    before the save under test, then restore the context in a finally block
    or rely on this fixture to clean up after them.
    """
    ctx = CallerContext(user=None, batch_id=str(uuid.uuid7()))
    set_caller_context(ctx)
    yield ctx
    set_caller_context(None)
