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

_PRUNED_DIR_NAMES = {"node_modules", "build", "dist", "venv", "CVS", "_darcs", "{arch}"}

# The ONLY deliberately-uncollected test dirs. Each MUST correspond to an `--ignore=`
# in pyproject `addopts`. Keep tiny; adding a row is a visible decision.
_IGNORED_DIRS = {
    # DEPRECATED 2026-05-19, out of INSTALLED_APPS — tests fail without the app
    # loaded; `--ignore=plugins/genericom` in addopts.
    "plugins/genericom",
}

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


def filesystem_test_files() -> set[str]:
    found: set[str] = set()
    for pattern in ("test_*.py", "*_test.py"):
        for path in REPO_ROOT.rglob(pattern):
            rel = path.relative_to(REPO_ROOT)
            if _is_pruned(rel) or _in_ignored_dir(rel) or rel.as_posix() in _IGNORED_FILES:
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
