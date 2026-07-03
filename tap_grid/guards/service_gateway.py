"""Service-gateway capability-coverage guard — location IS the contract.

Every public (non-underscore) top-level function in `tap_grid/services/` must carry
`@requires_capability(...)` or `@gates_per_operation`. Enforced by *location*, not a
"does this look privileged?" heuristic — the heuristic is exactly what let the
Entity-spine reads ship ungated. Pure helpers live in `_impl.py` (unscanned), below
the gate. No baseline, no allowlist: a new ungated public function fails immediately.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tap.guards.base import REPO_ROOT, Guard

_SERVICES_DIR = REPO_ROOT / "tap_grid" / "services"
_GATE_DECORATORS = frozenset({"requires_capability", "gates_per_operation"})


def _gateway_modules() -> list[Path]:
    modules: list[Path] = []
    for path in sorted(_SERVICES_DIR.glob("*.py")):
        if path.name == "__init__.py" or not path.name.startswith("_"):
            modules.append(path)
    return modules


def _decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _ungated_public_defs(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    ungated: list[str] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("_"):
            continue
        decorators = {_decorator_name(d) for d in node.decorator_list}
        if decorators & _GATE_DECORATORS:
            continue
        ungated.append(f"{node.name}:{node.lineno}")
    return ungated


class ServiceGatewayGuard(Guard):
    slug = "service-gateway-coverage"
    map_row = "Service-gateway capability coverage"
    rid = "req-grid-service-gateway-gated"
    description = (
        "A public function added to the tap_grid.services gateway without a capability decorator is an "
        "ungated entry into the graph service layer. Location is the contract: every public def here must "
        "be gated (or moved to _impl.py below the gate), so the gate can't be forgotten by a judgment call."
    )

    def check(self) -> None:
        modules = _gateway_modules()
        assert modules, f"no gateway modules found under {_SERVICES_DIR}"
        offenders = {path.name: ungated for path in modules if (ungated := _ungated_public_defs(path))}
        assert not offenders, (
            "Ungated public function(s) in the tap_grid.services gateway. Every public (non-underscore) "
            "top-level def here must carry @requires_capability(...) or @gates_per_operation. Gate it, or "
            f"if it is a pure helper move it to _impl.py (below the gate). Offenders: {offenders}"
        )
