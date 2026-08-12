"""The request-identity single source (derive-same-fact-twice audit #4).

`CallerContextMiddleware` binds one CallerContext per request; request-scoped
code consumes it via `require_caller_context()` rather than rebuilding one from
`request.user`. Four hand-rolled rebuilders (three tap_api routers + tap_web)
previously used a *different* authenticated-vs-anonymous predicate than the
middleware — two definitions of "who is calling" on an authorization surface.
These tests pin the accessor's fail-closed contract and that no rebuilder
returns.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tap_grid.caller_context import CallerContext, require_caller_context, set_caller_context
from tap_grid.exceptions import NoCallerContextError


class TestRequireCallerContext:
    def test_returns_the_bound_context_object(self):
        ctx = CallerContext(user=None, batch_id="b-1")
        set_caller_context(ctx)
        try:
            assert require_caller_context() is ctx
        finally:
            set_caller_context(None)

    def test_raises_when_unbound(self):
        set_caller_context(None)
        with pytest.raises(NoCallerContextError, match="CallerContextMiddleware"):
            require_caller_context()


class TestNoRebuildersRemain:
    """The rebuilders are gone and must not come back (audit #4 regression pin).

    A route that reconstructs identity from `request.user` re-forks the
    authenticated-vs-anonymous predicate away from the middleware's
    `is_authenticated`. Scans the request-handling surfaces for the shape.
    """

    def test_no_route_constructs_a_caller_context_from_request_user(self):
        repo_root = Path(__file__).resolve().parents[2]
        surfaces = [
            *(repo_root / "tap_api").rglob("*.py"),
            *(repo_root / "tap_web").rglob("*.py"),
            *(repo_root / "tap_viz").rglob("*.py"),
        ]
        # The rebuilder shape: deriving a user from request.user for a context.
        rebuilder = re.compile(r"request\.user\s+if\s+hasattr\(request\.user")
        offenders = [
            str(path.relative_to(repo_root))
            for path in surfaces
            if "tests" not in path.parts and rebuilder.search(path.read_text(encoding="utf-8", errors="ignore"))
        ]
        assert not offenders, (
            "request-scoped code rebuilds a CallerContext from request.user instead of "
            f"consuming the middleware-bound one: {offenders}. Use require_caller_context()."
        )
