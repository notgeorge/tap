"""Root-level pytest configuration — collection scoping ONLY.

The test-harness fixtures (the `tap_test` caller context, the auth-bootstrap
seeding, the service-write hatch) do NOT live here. They are a real pytest
plugin — `tap/pytest_harness.py`, loaded via `-p tap.pytest_harness` in the
configfile's `addopts` — because conftest loading depends on how pytest was
invoked: pytest 9.1 stopped
loading the rootdir conftest chain for `--pyargs`-resolved packages (2026-08-09),
which silently stripped the harness from every `pytest --pyargs tap_plugin.<slug>`
run (plugin-ci lane 2) and failed every plugin DB test at the service boundary.
An entry-point plugin loads in every invocation mode; a conftest does not. Do not
move load-bearing fixtures back here. (req-tap-test-fixtures / spec-tap-testing.md)

What legitimately remains here is rootdir-scoped COLLECTION configuration —
`collect_ignore` is a conftest-only pytest hook variable, and it only matters when
collection walks this repo tree, which is exactly the case where this conftest is
guaranteed to load.
"""

from pathlib import Path

from tap.plugin_testing import installed_plugin_slugs

_REPO_ROOT = Path(__file__).resolve().parent


def _uninstalled_plugin_test_dirs() -> list[str]:
    """Test dirs of plugins present on disk but NOT installed in this stack.

    Plugin tests now live inside the package (``plugins/<slug>/tap_plugin/<slug>/
    tests/``, or the legacy ``plugins/<slug>/tests/`` for pre-package plugins) and
    import by installed identity (``tap_plugin.<slug>...``), so collecting them for a
    plugin this stack did not install would ImportError at collection time — the
    focused-session wound. The repo-root walk still descends into ``plugins/`` and
    collects every *installed* plugin's tests automatically (fail-safe discovery,
    no allow-list); this returns only the *uninstalled* ones for ``collect_ignore``,
    so their coverage is delegated to the all-plugins CI lane rather than red'ing the
    local run. See ``tap.plugin_testing`` and req-dev-validation-collection-complete.
    """
    plugins_dir = _REPO_ROOT / "plugins"
    if not plugins_dir.is_dir():
        return []
    installed = set(installed_plugin_slugs())
    ignore: list[str] = []
    for slug_dir in sorted(plugins_dir.iterdir()):
        if not slug_dir.is_dir() or slug_dir.name in installed:
            continue
        # Package-mode layout (tests inside the namespace package) + legacy layout.
        for tests in sorted(slug_dir.glob("tap_plugin/*/tests")):
            ignore.append(str(tests))
        legacy = slug_dir / "tests"
        if legacy.is_dir():
            ignore.append(str(legacy))
    return ignore


# Consumed by pytest at collection time (root-conftest `collect_ignore`).
collect_ignore = _uninstalled_plugin_test_dirs()
