"""Static direct-write scanner — req-tap-auth-policy-9 Rule B (write half).

The build-time complement to the runtime write backstop (`tap_grid.write_guard`).
The runtime guard fails a node/edge write closed at execution time when it does
not route through the service layer; this scanner surfaces the same class at
authoring time so a direct write is caught before it runs — "detect by default,
permit by exception".

It flags *statically resolvable* direct ORM writes on TAP-managed model classes
(the class-level shapes), which carry no false positives because they name a known
graph model:

  <Model>.objects.create(...) / .get_or_create(...) / .bulk_create(...) /
      .bulk_update(...) / .update(...)
  <Model>.objects.filter(...)....delete() / .update()   (terminal queryset write)
  <Model>(...).save(...)                                 (construct-then-save)

where <Model> is a TAP-managed model (a `BaseModel` subclass — incl. `Edge` — or
`Entity`), enumerated at test time from the model registry (a purely syntactic
tool cannot know which models are graph-managed; this is why Rule B is in-house,
not Semgrep — see `req-tap-auth-policy-9`).

Instance writes through a variable (`obj.save()`, `obj.delete()`) are NOT resolved
here — their type is not knowable statically — and are left to the runtime guard.
The two compose: the lint catches class-level direct writes at authoring time; the
guard catches everything, including instance writes, at runtime.

Sanctioned write modules (the service layer itself and the model base that
implements save/delete), migrations, and tests are out of scope. A reviewed
exception is a `# TAP-WRITE-COV: <reason>` comment anywhere on the write's physical
span (so a black-wrapped call may carry it on a continuation line), or, as a last
resort, a line in `tap/tests/_direct_write_baseline.txt` (ratchets to zero).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from tap.logging import CallSite

# Manager writes: `<Model>.objects.<method>(...)`.
_MANAGER_WRITES: frozenset[str] = frozenset(
    {"create", "get_or_create", "bulk_create", "bulk_update", "update", "acreate", "aget_or_create"}
)
# Terminal queryset writes: `<Model>.objects.filter(...).<method>()`.
_TERMINAL_WRITES: frozenset[str] = frozenset({"delete", "update", "adelete", "aupdate"})

# Modules that legitimately write TAP-managed rows directly — the service layer is
# the sanctioned path, and models.py implements the guarded save/delete themselves.
_SANCTIONED_SUFFIXES: tuple[str, ...] = (
    "tap_grid/services.py",
    "tap_grid/models.py",
    "tap_grid/batch.py",
    "tap_grid/grift/importer.py",  # the grift_import service implementation (bulk write pipeline)
)

_EXEMPT_TOKEN = "TAP-WRITE-COV"


@dataclass
class DirectWriteScanResult:
    """Direct-write call sites on TAP-managed models found by the scan."""

    direct_writes: list[CallSite] = field(default_factory=list)
    exempt_skipped: list[CallSite] = field(default_factory=list)


def _is_model_ref(node: ast.expr, names: frozenset[str]) -> bool:
    """True if `node` names a TAP-managed model — `Model` or `pkg.Model`."""
    if isinstance(node, ast.Name):
        return node.id in names
    if isinstance(node, ast.Attribute):
        return node.attr in names
    return False


def _is_objects_of_model(node: ast.expr, names: frozenset[str]) -> bool:
    """True if `node` is `<Model>.objects` (or `<Model>.all_objects`)."""
    return (
        isinstance(node, ast.Attribute) and node.attr in ("objects", "all_objects") and _is_model_ref(node.value, names)
    )


def _chain_rooted_at_model_manager(node: ast.expr, names: frozenset[str]) -> bool:
    """True if the attribute/call chain roots at `<Model>.objects` — e.g.
    `<Model>.objects.filter(...).exclude(...)`, so a terminal `.delete()`/`.update()`
    on it is a queryset write to a TAP model."""
    while True:
        if _is_objects_of_model(node, names):
            return True
        if isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, ast.Attribute):
            node = node.value
        else:
            return False


def _is_direct_tap_write(call: ast.Call, names: frozenset[str]) -> bool:
    """True if `call` is a statically-resolvable direct write to a TAP model class."""
    func = call.func
    if not isinstance(func, ast.Attribute):
        return False
    method = func.attr

    # <Model>.objects.create(...) / bulk_create / update / ...
    if method in _MANAGER_WRITES and _is_objects_of_model(func.value, names):
        return True
    # <Model>.objects.filter(...)....delete() / .update()
    if method in _TERMINAL_WRITES and _chain_rooted_at_model_manager(func.value, names):
        return True
    # <Model>(...).save(...)
    return bool(
        method in ("save", "asave") and isinstance(func.value, ast.Call) and _is_model_ref(func.value.func, names)
    )


class _DirectWriteVisitor(ast.NodeVisitor):
    def __init__(self, path: Path, source_lines: list[str], names: frozenset[str]) -> None:
        self.path = path
        self.source_lines = source_lines
        self.names = names
        self.result = DirectWriteScanResult()

    def visit_Call(self, node: ast.Call) -> None:
        if _is_direct_tap_write(node, self.names):
            lineno = node.lineno
            site = CallSite(self.path, lineno)
            # Scan the call's full physical span for the exemption token, not just
            # its start line — black may wrap a chained write across several lines,
            # landing the trailing `# TAP-WRITE-COV:` comment below `node.lineno`.
            end = node.end_lineno or lineno
            span = self.source_lines[lineno - 1 : end]
            if any(_EXEMPT_TOKEN in line for line in span):
                self.result.exempt_skipped.append(site)
            else:
                self.result.direct_writes.append(site)
        self.generic_visit(node)


def _is_out_of_scope(path: Path) -> bool:
    """Sanctioned service modules, migrations, and tests are out of scope."""
    posix = path.as_posix()
    if any(posix.endswith(suffix) for suffix in _SANCTIONED_SUFFIXES):
        return True
    if "migrations" in path.parts:
        return True
    return "tests" in path.parts or path.name.startswith("test_") or path.name == "conftest.py"


def scan_direct_writes(roots: list[Path], tap_model_names: frozenset[str]) -> DirectWriteScanResult:
    """Flag class-level direct writes to TAP-managed models across `roots`.

    `tap_model_names` is the set of TAP-managed model class names (BaseModel
    subclasses + Entity), enumerated by the caller from the model registry. Files
    that fail to parse are skipped (real syntax errors surface elsewhere).
    """
    result = DirectWriteScanResult()
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts or _is_out_of_scope(path):
                continue
            try:
                source = path.read_text(encoding="utf-8")
            except OSError, UnicodeDecodeError:
                continue
            try:
                tree = ast.parse(source, filename=str(path))
            except SyntaxError:
                continue
            visitor = _DirectWriteVisitor(path, source.splitlines(), tap_model_names)
            visitor.visit(tree)
            result.direct_writes.extend(visitor.result.direct_writes)
            result.exempt_skipped.extend(visitor.result.exempt_skipped)
    return result
