"""Service-gateway capability-coverage lint — location IS the contract.

Every public function in the ``tap_grid.services`` package (the grid service-layer
gateway) MUST be capability-gated. This test enforces that by *location*, not by a
"does this look like a privileged sink?" heuristic: the fragile heuristic is exactly
what let the Entity-spine reads (resolve_entity/get_node/get_edge/get_object) ship
ungated (2026-07-02 read-gap closure).

The rule, trivially enumerable:

  - Public gateway functions live in ``tap_grid/services/`` in a non-underscore
    module (``__init__.py`` today; future domain submodules like ``nodes.py``).
    Every top-level ``def`` there whose name does not start with ``_`` must carry
    ``@requires_capability(...)`` OR ``@gates_per_operation`` (the reviewed marker
    for functions like ``write_batch`` that authorize per operation in the body).
  - Pure helpers live in ``_impl.py`` (and any ``_``-prefixed module), which this
    lint does not scan — they run *below* the gate, after a gateway function has
    already authorized the caller.

If you add a public function to the gateway, the only way to satisfy this lint is
to gate it. There is no baseline and no allowlist: a new ungated public function
fails immediately. That is the whole point — the gate can't be forgotten because
the location demands it.

See spec-security-posture; sibling of ``test_authz_coverage`` (which covers the
wider app surface — views, endpoints — via the sink heuristic + ratchet).
"""

from __future__ import annotations

import ast
from pathlib import Path

_SERVICES_DIR = Path(__file__).resolve().parent.parent.parent / "tap_grid" / "services"

# Decorators that satisfy the gate requirement (matched by name in source AST).
_GATE_DECORATORS = frozenset({"requires_capability", "gates_per_operation"})


def _gateway_modules() -> list[Path]:
    """Public gateway modules in tap_grid/services/ — everything except _impl and
    other ``_``-prefixed helper modules. ``__init__.py`` is included explicitly
    (its stem starts with ``_`` but it is the public API surface, not a helper)."""
    modules: list[Path] = []
    for path in sorted(_SERVICES_DIR.glob("*.py")):
        if path.name == "__init__.py" or not path.name.startswith("_"):
            modules.append(path)
    return modules


def _decorator_name(node: ast.expr) -> str:
    """Best-effort dotted/callable decorator name: ``requires_capability`` from
    ``@requires_capability(...)``, ``gates_per_operation`` from a bare name."""
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _ungated_public_defs(path: Path) -> list[str]:
    """Return ``name:lineno`` for every ungated public top-level def in ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    ungated: list[str] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("_"):
            continue  # helpers / dunder are not gateway surface
        decorators = {_decorator_name(d) for d in node.decorator_list}
        if decorators & _GATE_DECORATORS:
            continue
        ungated.append(f"{node.name}:{node.lineno}")
    return ungated


def test_every_public_gateway_function_is_capability_gated() -> None:
    """No ungated public function may exist in the tap_grid.services gateway."""
    modules = _gateway_modules()
    assert modules, f"no gateway modules found under {_SERVICES_DIR}"

    offenders: dict[str, list[str]] = {}
    for path in modules:
        ungated = _ungated_public_defs(path)
        if ungated:
            offenders[path.name] = ungated

    assert not offenders, (
        "Ungated public function(s) in the tap_grid.services gateway. Every public "
        "(non-underscore) top-level def here must carry @requires_capability(...) or "
        "@gates_per_operation. Gate it, or if it is a pure helper move it to _impl.py "
        f"(below the gate). Offenders: {offenders}"
    )
