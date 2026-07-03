"""Static authz-coverage scanner (req-tap-auth-policy-9).

The build-time dual of the stateless enforcement backstop. The runtime backstop
(`tap_auth.enforcement`) catches an *unauthorized or actorless* actor reaching a
privileged graph sink. It cannot catch a *privileged* actor reaching a sink
through a forgotten gate — with no decision ledger (req-tap-auth-policy-8), a
forgotten `@requires_capability` on a path a privileged actor walks is silent.
This scanner closes that gap at build time: every call to a privileged sink must
sit inside a gated function (`@requires_capability`) or an `authorized(...)`
block, else it is flagged.

It reuses the shared source-scan primitives (`tap/source_scan.py`):
`first_party_source_roots` (first-party `tap_*` apps + `plugins/*`) and `CallSite`,
the same `ast`-at-collection-time approach, and the same baseline-ratchet +
exemption-marker model. `tap/guards/authz.py::AuthzCoverageRatchet` is the
enforcement surface (via `tap/tests/test_guards.py`); the baseline grandfathers
today's ungated paths and ratchets to zero as each per-app standard lands.

NOT Semgrep, deliberately (req-tap-auth-policy-9): a later rule — direct
graph-model ORM in panel/view zones, deferred to the tap_web standard — enumerates
graph-managed `BaseModel` subclasses at runtime, which a purely syntactic tool
cannot. Keeping the scanner in-house lets both rules share one harness and one
pytest gate.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

# Privileged graph sinks that are NOT gated at their own definition — a call to one
# must be reached through a gate, else it is ungated. `write_batch` is the
# undecorated write chokepoint (only the runtime backstop guards it); `grift_import`
# self-authorizes internally but is not decorated; the `_*_internal` write helpers
# are the entry points the per-app review found reached ambiently from
# tasks/registration.
#
# DELIBERATELY EXCLUDED: the read executors `execute_search` / `execute_gryphon_raw`
# / `explain_gryphon_raw`. Each is `@requires_capability("grid.read")` AT ITS OWN
# DEFINITION, gating on the CallerContext, fail-closed, regardless of caller — the
# gate cannot be bypassed by an ungated caller, so a call site is gated BY
# CONSTRUCTION, not "by accident". Flagging their callers made the scanner ~89%
# false-positive (33/37 baseline entries were self-gated read calls, chiefly
# dashboard panels), which drowned the genuine undecorated-write-sink debt. A guard
# that cries wolf gets ignored; this keeps it pointed at the sinks that actually
# lack a construction-time gate. (req-tap-auth-policy-9; see spec-dev-validation Map.)
SINK_CALLS: frozenset[str] = frozenset(
    {
        "write_batch",
        "grift_import",
        "_create_node_internal",
        "_patch_node_internal",
    }
)

# The decorator that gates a function, and the context manager that gates a block.
_GATE_DECORATOR = "requires_capability"
_GATE_CONTEXT = "authorized"

# Review-visible exemption marker: a line carrying this token is skipped — for the
# handful of helpers a per-function scanner cannot see are gated by their caller
# one frame up (e.g. a private `_*_impl` invoked inside the public entry point's
# `authorized()` block). It is a plain `# TAP-AUTHZ-COV: <reason>` comment by
# design — a hyphenated linter-suppression code would false-trigger ruff.
_EXEMPT_TOKEN = "TAP-AUTHZ-COV"


@dataclass(frozen=True)
class SinkSite:
    """One privileged-sink call site, keyed stably by enclosing scope + sink name.

    The baseline key is `<relpath>::<qualname>::<sink>` — NOT the line number — so
    an ungated sink does not drift in the baseline when unrelated edits move it up
    or down its file (the recurring `path:lineno` churn this replaces). `lineno` is
    retained only for human-friendly error messages, never for identity.
    """

    path: Path
    lineno: int
    qualname: str
    sink: str

    def key(self, repo_root: Path) -> str:
        return f"{self.path.relative_to(repo_root)}::{self.qualname}::{self.sink}"


@dataclass
class AuthzScanResult:
    """Ungated privileged-sink call sites found by `scan_authz_coverage()`."""

    ungated_sinks: list[SinkSite] = field(default_factory=list)
    exempt_skipped: list[SinkSite] = field(default_factory=list)


def _decorator_name(decorator: ast.expr) -> str | None:
    """Resolve a decorator expression to its callable name (handles `@x` and `@x(...)`)."""
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    if isinstance(target, ast.Attribute):
        return target.attr
    if isinstance(target, ast.Name):
        return target.id
    return None


def _is_gated_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True if the function carries a `@requires_capability(...)` decorator."""
    return any(_decorator_name(d) == _GATE_DECORATOR for d in node.decorator_list)


def _with_is_authorized(node: ast.With | ast.AsyncWith) -> bool:
    """True if any context manager in the `with` is an `authorized(...)` call."""
    for item in node.items:
        expr = item.context_expr
        func = expr.func if isinstance(expr, ast.Call) else expr
        if isinstance(func, ast.Attribute) and func.attr == _GATE_CONTEXT:
            return True
        if isinstance(func, ast.Name) and func.id == _GATE_CONTEXT:
            return True
    return False


def _call_name(node: ast.Call) -> str | None:
    """The called function's name (`foo` from `foo(...)` or `x.foo(...)`)."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


class _AuthzVisitor(ast.NodeVisitor):
    """Track the gated-context depth and flag sink calls reached at depth 0.

    Entering a `@requires_capability` function or an `authorized(...)` block
    increments the depth; a sink call seen while depth is 0 is ungated. A nested
    function inside a gated one stays covered (the outer gate authorizes the whole
    synchronous call), which matches the runtime semantics.
    """

    def __init__(self, path: Path, source_lines: list[str]) -> None:
        self.path = path
        self.source_lines = source_lines
        self.gated_depth = 0
        # Enclosing def/class names, for the stable `qualname` half of the key.
        # Pushed unconditionally (name tracking) — distinct from `gated_depth`,
        # which only counts *gated* frames.
        self.scope_stack: list[str] = []
        self.result = AuthzScanResult()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        gated = _is_gated_function(node)
        self.gated_depth += int(gated)
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()
        self.gated_depth -= int(gated)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        gated = _is_gated_function(node)
        self.gated_depth += int(gated)
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()
        self.gated_depth -= int(gated)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # Track the class name for method qualnames; classes do not gate.
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_With(self, node: ast.With) -> None:
        gated = _with_is_authorized(node)
        self.gated_depth += int(gated)
        self.generic_visit(node)
        self.gated_depth -= int(gated)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        gated = _with_is_authorized(node)
        self.gated_depth += int(gated)
        self.generic_visit(node)
        self.gated_depth -= int(gated)

    def visit_Call(self, node: ast.Call) -> None:
        sink = _call_name(node)
        if sink in SINK_CALLS and self.gated_depth == 0:
            lineno = node.lineno
            line = self.source_lines[lineno - 1] if 0 < lineno <= len(self.source_lines) else ""
            qualname = ".".join(self.scope_stack) if self.scope_stack else "<module>"
            site = SinkSite(self.path, lineno, qualname, sink)
            if _EXEMPT_TOKEN in line:
                self.result.exempt_skipped.append(site)
            else:
                self.result.ungated_sinks.append(site)
        self.generic_visit(node)


def _is_test_path(path: Path) -> bool:
    """Test code legitimately calls sinks directly (conftest binds an authorized
    actor); it is not a production authz path, so it is out of scope for the scan."""
    return "tests" in path.parts or path.name.startswith("test_") or path.name == "conftest.py"


def scan_authz_coverage(roots: list[Path]) -> AuthzScanResult:
    """Walk each root and flag ungated privileged-sink calls (req-tap-auth-policy-9).

    Files that fail to parse are skipped (pytest collection catches real syntax
    errors elsewhere). Test files are skipped — see `_is_test_path`. Use
    `tap.source_scan.first_party_source_roots()` to derive the first-party-app +
    plugin roots.
    """
    result = AuthzScanResult()
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts or _is_test_path(path):
                continue
            try:
                source = path.read_text(encoding="utf-8")
            except OSError, UnicodeDecodeError:
                continue
            try:
                tree = ast.parse(source, filename=str(path))
            except SyntaxError:
                continue
            visitor = _AuthzVisitor(path, source.splitlines())
            visitor.visit(tree)
            result.ungated_sinks.extend(visitor.result.ungated_sinks)
            result.exempt_skipped.extend(visitor.result.exempt_skipped)
    return result
