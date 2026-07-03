"""Filesystem-based discovery of distributed guards.

Guards are *owned where the thing they protect lives*: cross-cutting whole-repo
guards in `tap/guards/`, app-owned guards in `<app>/guards/`, plugin-owned guards
in `<plugin>/guards/`. Each is a `guards/` package with one concrete guard per
file; importing a guard module registers its `Guard` subclass (via
`__init_subclass__` in `base.py`). This walks every owner and imports its guard
modules so `all_guards()` sees the full set.

Discovery is **filesystem-based, not Django-app-registry-based**, by reusing
`first_party_source_roots` (see `tap.source_scan`). That is deliberate: some guards
(per-profile boot resolution, plugin-dependency consistency) also run inside the
pre-boot gate, before `django.setup()`. A guard is just an object with `check()`;
the pre-boot gate imports the specific ones it needs directly, while this discovery
is for the harness's "run them all + report" path. Both work without the app
registry loaded.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

from tap.guards.base import REPO_ROOT, Guard, all_guards
from tap.source_scan import first_party_source_roots


def _module_for_root(root: Path) -> str:
    """Dotted import name for a first-party source root.

    `tap_*` app roots import by their directory name (`tap_cares`). Package-mode
    plugin roots live at `plugins/<slug>/tap_plugin/<slug>` and import as the PEP
    420 namespace `tap_plugin.<slug>`.
    """
    parts = root.relative_to(REPO_ROOT).parts
    if "tap_plugin" in parts:
        return ".".join(parts[parts.index("tap_plugin") :])
    return parts[-1]


def _load_guard_package(package_name: str) -> None:
    """Import every non-underscore module in `<package_name>` so its guards register.

    A missing package (an owner with no `guards/` dir) is silently skipped. Modules
    are imported for their `__init_subclass__` side effect; non-guard modules (base,
    report, shared `_*` helpers) simply register nothing.
    """
    try:
        package = importlib.import_module(package_name)
    except ModuleNotFoundError:
        return
    package_path = getattr(package, "__path__", None)
    if package_path is None:
        return
    for info in pkgutil.iter_modules(package_path):
        if info.name.startswith("_"):
            continue
        importlib.import_module(f"{package_name}.{info.name}")


def discover_guards() -> list[Guard]:
    """Import all guard modules across every owner, then return the full guard set.

    Order: the platform's own `tap.guards` package first, then each first-party
    source root's `guards` package. Idempotent — re-importing a module is a no-op,
    so calling this repeatedly (per test, per report) is cheap.
    """
    _load_guard_package("tap.guards")
    for root in first_party_source_roots(REPO_ROOT):
        _load_guard_package(f"{_module_for_root(root)}.guards")
    return all_guards()
