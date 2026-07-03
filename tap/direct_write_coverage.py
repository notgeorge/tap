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
resort, a line in `tap/guards/baselines/direct_write.txt` (ratchets to zero).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from tap.source_scan import ScopeStackVisitor, iter_parsed_sources, semantic_hash

# Manager writes: `<Model>.objects.<method>(...)`.
_MANAGER_WRITES: frozenset[str] = frozenset(
    {"create", "get_or_create", "bulk_create", "bulk_update", "update", "acreate", "aget_or_create"}
)
# Terminal queryset writes: `<Model>.objects.filter(...).<method>()`.
_TERMINAL_WRITES: frozenset[str] = frozenset({"delete", "update", "adelete", "aupdate"})

# Modules that legitimately write TAP-managed rows directly — the service layer is
# the sanctioned path, and models.py implements the guarded save/delete themselves.
# The service layer is a package (tap_grid/services/): every module in it is the
# sanctioned direct-write path, covered by the package check in _is_out_of_scope.
_SANCTIONED_SUFFIXES: tuple[str, ...] = (
    "tap_grid/models.py",
    "tap_grid/batch.py",
    "tap_grid/grift/importer.py",  # the grift_import service implementation (bulk write pipeline)
)

_EXEMPT_TOKEN = "TAP-WRITE-COV"


@dataclass(frozen=True)
class DirectWriteSite:
    """One class-level direct-write call site on a TAP-managed model.

    Keyed stably by enclosing scope + ``Model.op`` — never the line number —
    mirroring authz's `SinkSite`, so a flagged write does not drift in the baseline
    when unrelated edits move it (the `path:lineno` churn this replaces,
    `req-tap-callsite-identity-anchor`). ``lineno`` is retained for navigation and
    messages only. ``node_dump`` is the positions-stripped AST serialization that
    discriminates two writes sharing an anchor (`req-tap-callsite-identity-discriminator`).
    """

    path: Path
    lineno: int
    qualname: str
    model: str
    op: str
    node_dump: str

    def anchor(self, repo_root: Path) -> str:
        """The drift-proof anchor `path::qualname::Model.op` (no line number)."""
        return f"{self.path.relative_to(repo_root).as_posix()}::{self.qualname}::{self.model}.{self.op}"

    def discriminator(self, repo_root: Path) -> str:
        """Semantic hash over location-free canonical material — tells apart two
        distinct writes at the same anchor. Byte-identical writes collide here and
        fall back to an ordinal in `tap.guards.callsite.disambiguate`."""
        return semantic_hash(
            self.path.relative_to(repo_root).as_posix(),
            self.qualname,
            "direct-write",
            f"{self.model}.{self.op}",
            self.node_dump,
        )


@dataclass
class DirectWriteScanResult:
    """Direct-write call sites on TAP-managed models found by the scan."""

    direct_writes: list[DirectWriteSite] = field(default_factory=list)
    exempt_skipped: list[DirectWriteSite] = field(default_factory=list)


def _model_ref_name(node: ast.expr, names: frozenset[str]) -> str | None:
    """The model class name if `node` names a TAP-managed model (`Model` / `pkg.Model`)."""
    if isinstance(node, ast.Name) and node.id in names:
        return node.id
    if isinstance(node, ast.Attribute) and node.attr in names:
        return node.attr
    return None


def _is_model_ref(node: ast.expr, names: frozenset[str]) -> bool:
    """True if `node` names a TAP-managed model — `Model` or `pkg.Model`."""
    return _model_ref_name(node, names) is not None


def _model_of_manager(node: ast.expr, names: frozenset[str]) -> str | None:
    """The model name if `node` is `<Model>.objects` (or `<Model>.all_objects`), else None."""
    if isinstance(node, ast.Attribute) and node.attr in ("objects", "all_objects"):
        return _model_ref_name(node.value, names)
    return None


def _model_of_chain(node: ast.expr, names: frozenset[str]) -> str | None:
    """The model name if the attribute/call chain roots at `<Model>.objects` — e.g.
    `<Model>.objects.filter(...).exclude(...)`, so a terminal `.delete()`/`.update()`
    on it is a queryset write to that TAP model."""
    while True:
        model = _model_of_manager(node, names)
        if model is not None:
            return model
        if isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, ast.Attribute):
            node = node.value
        else:
            return None


def _direct_write_target(call: ast.Call, names: frozenset[str]) -> tuple[str, str] | None:
    """`(model, op)` if `call` is a statically-resolvable direct write to a TAP model, else None."""
    func = call.func
    if not isinstance(func, ast.Attribute):
        return None
    method = func.attr

    # <Model>.objects.create(...) / bulk_create / update / ...
    if method in _MANAGER_WRITES:
        model = _model_of_manager(func.value, names)
        if model is not None:
            return (model, method)
    # <Model>.objects.filter(...)....delete() / .update()
    if method in _TERMINAL_WRITES:
        model = _model_of_chain(func.value, names)
        if model is not None:
            return (model, method)
    # <Model>(...).save(...)
    if method in ("save", "asave") and isinstance(func.value, ast.Call):
        model = _model_ref_name(func.value.func, names)
        if model is not None:
            return (model, method)
    return None


class _DirectWriteVisitor(ScopeStackVisitor):
    """Flag class-level direct writes to TAP-managed models, carrying the enclosing
    `qualname` from the shared `ScopeStackVisitor` (`req-tap-callsite-identity-anchor`)."""

    def __init__(self, path: Path, source_lines: list[str], names: frozenset[str]) -> None:
        super().__init__()
        self.path = path
        self.source_lines = source_lines
        self.names = names
        self.result = DirectWriteScanResult()

    def visit_Call(self, node: ast.Call) -> None:
        target = _direct_write_target(node, self.names)
        if target is not None:
            model, op = target
            lineno = node.lineno
            qualname = self.current_qualname()
            site = DirectWriteSite(
                self.path,
                lineno,
                qualname,
                model,
                op,
                # Positions-stripped structural dump: the drift-proof discriminator
                # material (`req-tap-callsite-identity-discriminator-4`).
                ast.dump(node, include_attributes=False),
            )
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
    if "tap_grid/services/" in posix:  # the whole service-layer package is sanctioned
        return True
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
    for parsed in iter_parsed_sources(roots, skip=_is_out_of_scope):
        visitor = _DirectWriteVisitor(parsed.path, parsed.lines, tap_model_names)
        visitor.visit(parsed.tree)
        result.direct_writes.extend(visitor.result.direct_writes)
        result.exempt_skipped.extend(visitor.result.exempt_skipped)
    return result
