"""Test-collection + test-support helpers for package-mode plugin tests.

Plugin tests live *inside* the namespace package (``tap_plugin/<slug>/tests/``) so
they ride in the built wheel and travel with the plugin — both as the all-plugins
CI lane's coverage and as an AI-legible corpus a maintenance agent can read
(see the ``ship-tests-in-wheel`` design note). Two consequences the rest of the
test system is built on:

* **Collection is by explicit path, not the repo-root walk.** pyproject
  ``addopts`` carries ``--ignore=plugins`` so the root discovery never descends
  into plugin source trees (which would double-collect the relocated tests). Plugin
  tests are added back by resolving each *installed* plugin's ``tests/`` dir here
  and passing it to pytest. An uninstalled plugin's tests are therefore never
  referenced at all — structural local scoping, no skip machinery — and the
  all-plugins CI lane owns full-set coverage.

* **Source-layout tests self-skip off a checkout.** A test that inspects the
  plugin *source* tree (``pyproject.toml``, the identity chain) cannot run from an
  installed wheel, where no source root exists. ``find_plugin_source_root`` returns
  ``None`` there so such tests ``skipif`` out, delegated to the plugin repo's own
  build; behavioural tests import ``tap_plugin.<slug>`` and run either way.

``scripts/test`` (the lane) and ``tap.guards`` collection-completeness both source
their plugin paths from here so the two never diverge.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path


def installed_plugin_slugs() -> list[str]:
    """Slugs of the plugins installed+enabled in THIS stack.

    Mirrors ``tap.settings``: honour an explicit ``TAP_PLUGINS`` override (the
    space-separated AppConfig paths pre-boot emits) when present, else fall back to
    entry-point discovery over installed distributions. Both reduce to the set of
    plugin slugs this stack actually runs.
    """
    env = os.environ.get("TAP_PLUGINS")
    if env is not None:
        return sorted({app.split(".")[1] for app in env.split() if app.startswith("tap_plugin.")})
    from tap.preboot import discover_entry_points

    return sorted(discover_entry_points())


def plugin_package_dir(slug: str) -> Path | None:
    """Filesystem location of the installed ``tap_plugin.<slug>`` package, or None.

    Resolved through the import system, so it points at the editable checkout
    (``plugins/<slug>/tap_plugin/<slug>``) or the site-packages install with equal
    fidelity — the caller never has to know which.
    """
    spec = importlib.util.find_spec(f"tap_plugin.{slug}")
    if spec is None or not spec.submodule_search_locations:
        return None
    return Path(next(iter(spec.submodule_search_locations)))


def plugin_test_dirs() -> list[Path]:
    """The ``tests/`` dir of every installed plugin that ships one."""
    dirs: list[Path] = []
    for slug in installed_plugin_slugs():
        pkg = plugin_package_dir(slug)
        if pkg is None:
            continue
        tests = pkg / "tests"
        if tests.is_dir():
            dirs.append(tests)
    return dirs


def find_plugin_source_root(test_file: str) -> Path | None:
    """Plugin *source* root (the dir holding ``pyproject.toml``) for a test file.

    Returns None when the plugin is installed as a wheel (no source tree in the
    ancestry) — the caller ``skipif``s, delegating source-layout validation to the
    plugin repo's own build. In a monorepo/checkout the nearest ancestor with a
    ``pyproject.toml`` is the plugin's own source root.
    """
    for parent in Path(test_file).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return None


def main() -> None:
    """Print each installed-plugin ``tests/`` dir on its own line (one per plugin).

    The collection seam for ``scripts/test``: the lane appends these paths to the
    pytest invocation so plugin tests are collected alongside the core walk.
    """
    for path in plugin_test_dirs():
        print(path)


if __name__ == "__main__":
    main()
