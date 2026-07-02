"""Plugin dependency-consistency guard — `req-plugin-arch-dependencies-4`.

Per-commit, install-order-independent half of the dependency gate: every in-repo
plugin's manifest `depends_on` must be a superset of its AST-observed
`tap_plugin.<other>` imports. An undeclared cross-plugin import is exactly the
silent coupling that bites when a plugin is extracted to a standalone repo — and it
is a fact of the source tree, checkable without booting.

The *full* check (install-set presence + ordering + min-version against a concrete
profile) stays in the pre-boot gate (`tap.preboot.dependency_consistency_guard`),
which has the profile's install order in hand. This guard is the authoring-time
catch that fires in CI before a spawn ever runs; the two are complementary, not
duplicative. Filesystem-based (reuses `tap.plugin_deps`), so it needs no DB or boot.
"""

from __future__ import annotations

from tap.guards.base import REPO_ROOT, Guard


class PluginDependencyConsistencyGuard(Guard):
    slug = "plugin-dependency-consistency"
    map_row = "Plugin dependency consistency"
    description = (
        "A plugin that imports another plugin's code without declaring it in manifest depends_on is "
        "silently coupled — the import graph and the declared graph diverge, and extraction to a "
        "standalone repo breaks with no warning. This asserts declared ⊇ observed across every in-repo "
        "plugin at authoring time; the pre-boot gate additionally enforces install-order per profile."
    )

    def check(self) -> None:
        from tap import plugin_deps

        packages = plugin_deps.discover_plugin_packages(REPO_ROOT)
        assert packages, "no in-repo plugin packages discovered — the guard would cover nothing"

        violations: list[str] = []
        for slug, pkg in sorted(packages.items()):
            declared = {d.slug for d in plugin_deps.read_declared_depends_on(pkg)}
            observed = plugin_deps.scan_observed_imports(pkg, slug)
            undeclared = sorted(observed - declared)
            if undeclared:
                violations.append(
                    f"  {slug}: imports {undeclared} but does not declare them in `depends_on` "
                    f"(declared: {sorted(declared) or 'none'})"
                )

        assert not violations, (
            "Undeclared cross-plugin import(s) — the manifest `depends_on` must list every plugin whose "
            "code is imported (req-plugin-arch-dependencies-4):\n" + "\n".join(violations)
        )
