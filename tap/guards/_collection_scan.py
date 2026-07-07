"""Shared scan helpers for the two collection-completeness guards.

The `_IGNORED_DIRS` ledger is the single visible list of deliberately-uncollected
test dirs — both guards read it (one checks it against pyproject `addopts`, the
other subtracts it from the on-disk set). Kept in one place so the ledger has one
home.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tap.guards.base import REPO_ROOT
from tap.plugin_testing import installed_plugin_slugs

_PRUNED_DIR_NAMES = {"node_modules", "build", "dist", "venv", "CVS", "_darcs", "{arch}"}

# The ONLY deliberately-uncollected test dirs. Each MUST correspond to an `--ignore=`
# in pyproject `addopts`. Keep tiny; adding a row is a visible decision.
_IGNORED_DIRS: set[str] = set()

# Files matching test_*.py that are NOT tests (pytest imports them, collects zero).
_IGNORED_FILES = {
    "tap/test_settings.py",  # DJANGO_SETTINGS_MODULE, not a test module
}


def _is_pruned(rel: Path) -> bool:
    for part in rel.parts:
        if part.startswith(".") or part in _PRUNED_DIR_NAMES or part.endswith((".egg", ".egg-info")):
            return True
    return False


def _in_ignored_dir(rel: Path) -> bool:
    rel_str = rel.as_posix()
    return any(rel_str == ig or rel_str.startswith(f"{ig}/") for ig in _IGNORED_DIRS)


def _uninstalled_plugin_test(rel: Path, installed: set[str]) -> bool:
    """Is ``rel`` a test file of a plugin NOT installed in this stack?

    Plugin tests now live inside the package (``plugins/<slug>/...``) and import by
    installed identity, so an uninstalled plugin's tests are legitimately uncollected
    here (the root-conftest ``collect_ignore`` drops them; the all-plugins CI lane
    owns their coverage). Subtracting them keeps the completeness guard honest per
    stack: fully strict in the all-plugins lane (nothing uninstalled → nothing
    subtracted), appropriately relaxed in a focused session. Mirrors the
    ``collect_ignore`` logic in the root conftest.
    """
    parts = rel.parts
    if len(parts) < 2 or parts[0] != "plugins":
        return False
    return parts[1] not in installed


def filesystem_test_files() -> set[str]:
    installed = set(installed_plugin_slugs())
    found: set[str] = set()
    for pattern in ("test_*.py", "*_test.py"):
        for path in REPO_ROOT.rglob(pattern):
            rel = path.relative_to(REPO_ROOT)
            if (
                _is_pruned(rel)
                or _in_ignored_dir(rel)
                or rel.as_posix() in _IGNORED_FILES
                or _uninstalled_plugin_test(rel, installed)
            ):
                continue
            found.add(rel.as_posix())
    return found


def collected_test_files() -> set[str]:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            *(f"--ignore={d}" for d in sorted(_IGNORED_DIRS)),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    files = {line.split("::", 1)[0].strip() for line in proc.stdout.splitlines() if "::" in line}
    if not files:
        raise AssertionError(
            f"pytest --collect-only returned no items.\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return files
