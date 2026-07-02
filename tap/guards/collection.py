"""Collection-completeness guards — `req-dev-validation-collection-complete`.

Validate the validator: every `test_*.py`/`*_test.py` on disk must be collected by
a full-repo run (minus a tiny justified ledger), and every `--ignore=` in pyproject
`addopts` must be registered in that ledger. Without this, "green" can silently mean
"the subset pytest happened to collect passed" — the exact hole that shipped the
2026-07-01 login regression.

Two invariants → two guards. `_IGNORED_DIRS` here is the single visible ledger of
deliberate coverage holes. Note: the orphan check forks `pytest --collect-only` over
the whole repo, so it is the slowest guard (still per-commit by design).
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

from tap.guards.base import REPO_ROOT, Guard

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


def _filesystem_test_files() -> set[str]:
    found: set[str] = set()
    for pattern in ("test_*.py", "*_test.py"):
        for path in REPO_ROOT.rglob(pattern):
            rel = path.relative_to(REPO_ROOT)
            if _is_pruned(rel) or _in_ignored_dir(rel) or rel.as_posix() in _IGNORED_FILES:
                continue
            found.add(rel.as_posix())
    return found


def _collected_test_files() -> set[str]:
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


class AddoptsIgnoresRegisteredGuard(Guard):
    slug = "collection-addopts-registered"
    map_row = "Collection completeness"
    description = (
        "A `--ignore=` added to pyproject addopts but not registered in the _IGNORED_DIRS ledger would "
        "let the gate skip a dir the completeness check still believes is covered — a silent coverage "
        "hole. This asserts every real ignore is an accounted-for, justified ledger entry."
    )

    def check(self) -> None:
        pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
        addopts = pyproject["tool"]["pytest"]["ini_options"].get("addopts", "")
        ignored_in_addopts = set(re.findall(r"--ignore=(\S+)", addopts))
        unregistered = sorted(ignored_in_addopts - _IGNORED_DIRS)
        assert not unregistered, (
            "These dirs are `--ignore`d in pyproject `addopts` but not registered in `_IGNORED_DIRS` "
            f"(so the completeness guard wrongly believes they are covered): {unregistered}. Add them to "
            "`_IGNORED_DIRS` with justification."
        )


class CollectionCompletenessGuard(Guard):
    slug = "collection-completeness"
    map_row = "Collection completeness"
    description = (
        "A test file on disk that the default pytest run doesn't collect silently gates nothing — the "
        "2026-07-01 login regression shipped green exactly this way. This asserts every on-disk test "
        "file (minus the justified ledger) is collected by a full-repo run, so the scope can't narrow "
        "unnoticed."
    )

    def check(self) -> None:
        orphans = sorted(_filesystem_test_files() - _collected_test_files())
        assert not orphans, (
            "These test files exist on disk but are NOT collected by the default pytest run — they will "
            "silently never gate:\n  "
            + "\n  ".join(orphans)
            + "\n\nEither bring them into discovery scope (do not add a `testpaths` allow-list) or, if the "
            "exclusion is intentional, add the dir to `_IGNORED_DIRS` in tap/guards/collection.py WITH "
            "justification and a matching `--ignore=` in pyproject `addopts`."
        )
