# Changelog

## [0.1.1](https://github.com/unified-systems-com/tap/compare/v0.1.0...v0.1.1) (2026-08-12)


### Features

* **grid:** edge property lanes — central hotlink check + schema-required warn mode ([871f7f7](https://github.com/unified-systems-com/tap/commit/871f7f77bdc197a4868f3572e5a775e620f404b3))


### Bug Fixes

* **boot:** TAP_PLUGINS is authoritative — collapse the two-source plugin-set race ([e4183c3](https://github.com/unified-systems-com/tap/commit/e4183c3664295f42fa9ce08d7f6cf61a52da2604))
* **cicd:** wire the release lane to the real app — tap-release-please ([d345c62](https://github.com/unified-systems-com/tap/commit/d345c627e9beaecea2d80206075f321b24989ecf))
* **ci:** gate api-fuzz boot on migrations APPLIED, not just health — the real flake root ([625ae08](https://github.com/unified-systems-com/tap/commit/625ae086017cda375c963afe02ce98a64c3847c0))
* **grid:** annotate migration functions + registry fixture — mypy ratchet clean ([8d942f9](https://github.com/unified-systems-com/tap/commit/8d942f94b1756e425453d3e47114d3d80ba308de))
* **health:** diversify readiness with a critical 'migrations' probe — the real flake fix ([b70d7f9](https://github.com/unified-systems-com/tap/commit/b70d7f93507ca0cb9e213fb82777baa9c6362f99))


### Documentation

* **dev-validation:** close the api-fuzz known-flake ledger row — two-source INSTALLED_APPS divergence, root-caused + fixed ([f242cf9](https://github.com/unified-systems-com/tap/commit/f242cf9444073833cfbb6755dacea40f6eb96307))
* **dev-validation:** correct the known-flake ledger — the real root was migrate-vs-boot, fixed by the migrations readiness probe ([d02b444](https://github.com/unified-systems-com/tap/commit/d02b444d7aceca68e701365c34bf6a3d0e010d51))
* **health:** probes-4 ACID — add migrations to the enumerated critical set ([2cbd947](https://github.com/unified-systems-com/tap/commit/2cbd94788976a7829cb8051cfa4de8338d6059e5))
* **health:** record the migrations probe in spec-tap-health-v0 — the first readiness-class probe ([3bbfa8f](https://github.com/unified-systems-com/tap/commit/3bbfa8f2d4c3e354e9e8b4161dcef051e2cd0310))
* **spec:** api-fuzz flake ESCALATED — recurred same day; investigation owned by session/unified ([cd70a1b](https://github.com/unified-systems-com/tap/commit/cd70a1beac5d59d31101109248619ec058e0f5de))
* **spec:** api-fuzz known-flake ledger — track setup-phase reds across sessions ([4b6104f](https://github.com/unified-systems-com/tap/commit/4b6104fc0ea546a89a0139454f62365337922d4c))
