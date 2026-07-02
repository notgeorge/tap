"""Guard: every test file in the repo is actually collected by the gate run.

This validates the validator. The 2026-07-01 login regression shipped green
because whole apps' tests (`tap_auth`, `tap_boot`, `tap_cares`) lived outside the
`testpaths` allow-list and were therefore *never collected* by the default
`pytest` run — so "green" meant "the tests pytest happened to collect passed,"
and the collection was silently narrower than the code. No ordinary test can
catch that: the thing that failed is the collection scope, one layer beneath the
tests. This guard closes the class by asserting an outcome, not a config shape:

    every test file that exists on disk is collected by a full-repo run,
    except the small, justified set in `_IGNORED_DIRS`.

Being outcome-based, it catches the whole family of causes — a re-introduced
`testpaths` allow-list, a stray `--ignore`, a test dir that fails to import — not
just the specific mechanism that bit us. Any real exclusion in `addopts`
(`--ignore=...`) MUST be mirrored in `_IGNORED_DIRS` here, or a file it hides is
reported as an orphan: the registry below is the single visible ledger of
deliberate coverage holes (req-dev-validation-collection-complete).
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

# Repo root: tap/tests/this_file.py -> parents[2].
_REPO_ROOT = Path(__file__).resolve().parents[2]

# Directory basenames pytest's default `norecursedirs` prunes, plus dot-dirs
# (covers `.venv`, `.git`) and egg metadata. Mirrored here so the filesystem
# walk sees the same tree pytest does — without this the walk would descend into
# `.venv` and enumerate thousands of dependency test files.
_PRUNED_DIR_NAMES = {"node_modules", "build", "dist", "venv", "CVS", "_darcs", "{arch}"}

# The ONLY deliberately-uncollected test dirs. Each entry is a justified hole in
# coverage and MUST correspond to an `--ignore=` in pyproject `addopts` (or a
# marker deselection). Keep this tiny; adding a row is a visible decision.
_IGNORED_DIRS = {
    # DEPRECATED 2026-05-19, out of INSTALLED_APPS — tests fail without the app
    # loaded; `--ignore=plugins/genericom` in addopts.
    "plugins/genericom",
}

# Files that match the `test_*.py` glob but are NOT tests — pytest imports them
# and collects zero items, so they'd read as false orphans. Exact-path allowlist,
# deliberately narrow (a real test file must never be parked here to hide it).
_IGNORED_FILES = {
    # Django test-settings module (DJANGO_SETTINGS_MODULE = "tap.test_settings"),
    # not a test module.
    "tap/test_settings.py",
}


def _is_pruned(rel: Path) -> bool:
    """True if any path component is pruned (dot-dir / norecursedirs / egg-info)."""
    for part in rel.parts:
        if part.startswith("."):
            return True
        if part in _PRUNED_DIR_NAMES:
            return True
        if part.endswith((".egg", ".egg-info")):
            return True
    return False


def _in_ignored_dir(rel: Path) -> bool:
    rel_str = rel.as_posix()
    return any(rel_str == ig or rel_str.startswith(f"{ig}/") for ig in _IGNORED_DIRS)


def _filesystem_test_files() -> set[str]:
    """Every `test_*.py` / `*_test.py` on disk, minus pruned and ignored dirs."""
    found: set[str] = set()
    for pattern in ("test_*.py", "*_test.py"):
        for path in _REPO_ROOT.rglob(pattern):
            rel = path.relative_to(_REPO_ROOT)
            if _is_pruned(rel) or _in_ignored_dir(rel) or rel.as_posix() in _IGNORED_FILES:
                continue
            found.add(rel.as_posix())
    return found


def _collected_test_files() -> set[str]:
    """Files pytest actually collects the way the gate collects them.

    Runs `pytest --collect-only` from the repo root with **no explicit path**, so
    the collection scope is whatever the real gate would use — repo-root discovery
    today, or a `testpaths` allow-list if one were (re-)introduced. That is what
    gives the guard teeth: passing an explicit `.` would override `testpaths` and
    the guard could never catch its own regression. Clears the configured
    `addopts` (`-o addopts=`) so the run is under this function's control: no
    inherited `-v` (which would print the collection tree instead of flat node
    ids), no `-m 'not live_fetch'` marker filter (a marker-deselected file is
    still *collected*, so we count it, not drop it as a false orphan), and no
    inherited `--ignore`. The intentional exclusions are re-applied from
    `_IGNORED_DIRS` — the single source of truth, which
    `test_addopts_ignores_are_registered` proves matches the real `--ignore`s.
    """
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
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    files = {line.split("::", 1)[0].strip() for line in proc.stdout.splitlines() if "::" in line}
    if not files:  # collection produced nothing — a real failure, surface it
        raise AssertionError(
            f"pytest --collect-only returned no items.\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return files


def test_addopts_ignores_are_registered() -> None:
    """Every `--ignore=` in pyproject `addopts` MUST be in `_IGNORED_DIRS`.

    Keeps `_IGNORED_DIRS` the authoritative ledger of coverage holes: a real
    exclusion added to `addopts` but not registered here would otherwise let the
    gate skip a dir the completeness check still believes is covered.
    """
    pyproject = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text())
    addopts = pyproject["tool"]["pytest"]["ini_options"].get("addopts", "")
    ignored_in_addopts = set(re.findall(r"--ignore=(\S+)", addopts))
    unregistered = sorted(ignored_in_addopts - _IGNORED_DIRS)
    assert not unregistered, (
        "These dirs are `--ignore`d in pyproject `addopts` but not registered in "
        "`_IGNORED_DIRS` (so the completeness guard wrongly believes they are "
        f"covered): {unregistered}. Add them to `_IGNORED_DIRS` with justification."
    )


def test_every_test_file_is_collected() -> None:
    on_disk = _filesystem_test_files()
    collected = _collected_test_files()
    orphans = sorted(on_disk - collected)
    assert not orphans, (
        "These test files exist on disk but are NOT collected by the default "
        "pytest run — they will silently never gate:\n  "
        + "\n  ".join(orphans)
        + "\n\nEither bring them into discovery scope (do not add a `testpaths` "
        "allow-list) or, if the exclusion is intentional, add the dir to "
        "`_IGNORED_DIRS` in this file WITH justification and a matching "
        "`--ignore=` in pyproject `addopts`."
    )
