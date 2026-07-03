"""Plugin type-ownership affix guard — `req-plugin-type-collision-loud`.

Owner-namespacing (`spec-plugin-type-ownership-v0`) makes true type collisions
impossible *by construction* — but only if every plugin type actually carries its
owner affix. A forgotten affix silently re-opens the hole (two plugins could claim
the same bare name). This guard is the "loud, never silent" enforcement the spec
calls for (`req-plugin-type-collision-loud-3`): a filesystem-time check that every
in-repo plugin's declared node types carry the `<slug>__` prefix and every edge type
carries the `__<slug>` suffix, and that no qualified name is claimed by two plugins.

Manifest-based (reads each plugin's `tap-plugin.toml` `[models]`/`[editors]`/`[edges]`
keys), so it needs no DB or boot and fires per-commit in CI. Core/platform types stay
unqualified and are owned by core apps, not plugins, so they never appear here.
"""

from __future__ import annotations

import tomllib

from tap.guards.base import REPO_ROOT, Guard


class PluginTypeOwnershipGuard(Guard):
    slug = "plugin-type-ownership"
    map_row = "Plugin type-ownership affixes"
    rid = "req-plugin-type-collision-loud"
    cadence = "Per-commit (`pytest`)"
    description = (
        "Owner-namespacing removes type collisions only if every plugin type keeps its affix. A "
        "forgotten `<slug>__` prefix (node) or `__<slug>` suffix (edge) silently re-opens the hole two "
        "plugins claiming the same bare name would fall into. This asserts every in-repo plugin's "
        "declared node/edge types carry the owner affix and no qualified name is claimed twice."
    )

    def check(self) -> None:
        from tap import plugin_deps

        packages = plugin_deps.discover_plugin_packages(REPO_ROOT)
        assert packages, "no in-repo plugin packages discovered — the guard would cover nothing"

        missing: list[str] = []
        owners: dict[str, str] = {}  # qualified name -> declaring plugin slug
        dupes: list[str] = []

        for slug, pkg in sorted(packages.items()):
            manifest = pkg / "tap-plugin.toml"
            if not manifest.exists():
                continue
            with open(manifest, "rb") as fh:
                raw = tomllib.load(fh)
            node_prefix = f"{slug}__"
            edge_suffix = f"__{slug}"
            # [models] + [editors] keys are node entity_types; [edges] keys are edge types.
            node_types = list(raw.get("models", {})) + list(raw.get("editors", {}))
            edge_types = list(raw.get("edges", {}))
            # An [editors] key repeats its model's entity_type (the type it edits) — a
            # same-plugin overlap, not a collision. Only a DIFFERENT plugin claiming a
            # qualified name is the failure the guard exists to catch.
            for nt in node_types:
                if not nt.startswith(node_prefix):
                    missing.append(f"  {slug}: node type '{nt}' lacks the '{node_prefix}' owner prefix")
                if owners.get(nt, slug) != slug:
                    dupes.append(f"  qualified name '{nt}' claimed by both '{owners[nt]}' and '{slug}'")
                owners[nt] = slug
            for et in edge_types:
                if not et.endswith(edge_suffix):
                    missing.append(f"  {slug}: edge type '{et}' lacks the '{edge_suffix}' owner suffix")
                if owners.get(et, slug) != slug:
                    dupes.append(f"  qualified name '{et}' claimed by both '{owners[et]}' and '{slug}'")
                owners[et] = slug

        problems = missing + dupes
        assert not problems, (
            "Plugin type-ownership affix violation(s) — every plugin node type must be '<slug>__<name>' "
            "and every edge type '<NAME>__<slug>', each qualified name owned by exactly one plugin "
            "(req-plugin-type-node-prefix / -edge-suffix / -collision-loud):\n" + "\n".join(problems)
        )
