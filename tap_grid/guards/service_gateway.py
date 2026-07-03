"""Service-gateway capability-coverage guard — exported gateway names are gated.

Every exported public gateway callable must carry `@requires_capability(...)` or
`@gates_per_operation`. Until `tap_grid.services.__all__` exists as the explicit
export manifest, this transitional guard treats public (non-underscore) top-level
functions in `tap_grid/services/` gateway modules as the export inventory. Enforced
by *location/export*, not a "does this look privileged?" heuristic — the heuristic is
exactly what let the Entity-spine reads ship ungated. Pure helpers live in `_impl.py`
(unscanned), below the gate. No baseline, no allowlist: a new ungated public gateway
callable fails immediately.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tap.guards.base import REPO_ROOT, Guard
from tap.source_scan import has_decorator, parse_file

_SERVICES_DIR = REPO_ROOT / "tap_grid" / "services"
_GATE_DECORATORS = frozenset({"requires_capability", "gates_per_operation"})


def _gateway_modules() -> list[Path]:
    modules: list[Path] = []
    for path in sorted(_SERVICES_DIR.glob("*.py")):
        if path.name == "__init__.py" or not path.name.startswith("_"):
            modules.append(path)
    return modules


def _ungated_public_defs(path: Path) -> list[str]:
    parsed = parse_file(path)
    # Fail LOUD, not open. The broad tree-scanners tolerate a parse error (skip the
    # file) because they walk the whole first-party tree and one unrelated broken
    # file must not blind the scan. This guard walks a tiny FIXED set — its own
    # gateway modules — so a parse failure here is in-scope: returning [] would
    # green the guard on an unparseable version of the exact surface it protects.
    assert parsed is not None, f"gateway module failed to read/parse (guard cannot verify it): {path}"
    ungated: list[str] = []
    # Top-level (`tree.body`) only: the export inventory is public top-level defs;
    # nested defs are below the gate by construction and out of scope here.
    for node in parsed.tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("_"):
            continue
        if has_decorator(node, _GATE_DECORATORS):
            continue
        ungated.append(f"{node.name}:{node.lineno}")
    return ungated


class ServiceGatewayGuard(Guard):
    slug = "service-gateway-coverage"
    map_row = "Service-gateway capability coverage"
    rid = "req-grid-service-gateway-gated"
    description = (
        "A public gateway callable exported by tap_grid.services without a capability decorator is an "
        "ungated entry into the graph service layer. Location/export is the contract: every exported "
        "public callable must be gated (or moved below the gate), so the gate can't be forgotten by a "
        "judgment call."
    )

    def check(self) -> None:
        modules = _gateway_modules()
        assert modules, f"no gateway modules found under {_SERVICES_DIR}"
        offenders = {path.name: ungated for path in modules if (ungated := _ungated_public_defs(path))}
        assert not offenders, (
            "Ungated public gateway callable(s) in tap_grid.services. Until tap_grid.services.__all__ "
            "exists, every public (non-underscore) top-level def in a gateway module must carry "
            "@requires_capability(...) or @gates_per_operation. Gate it, or if it is a pure helper move "
            f"it to _impl.py (below the gate). Offenders: {offenders}"
        )
