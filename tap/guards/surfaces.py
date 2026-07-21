"""Declared non-guard validation surfaces — the negative space of the Map.

The harness `Guard` subclasses are self-describing: `manage.py guards` generates
their Map rows straight from the code, so they can never drift. But TAP's validation
posture also includes surfaces that are *not* harness guards — behavioral tests that
need a live transaction/render/fork, the pre-push cold-boot gate, on-demand scripts,
and deliberately-manual or deferred procedures. A "print all guards" report that
showed only the guards would silently erase that negative space, and the whole point
of the Validation Map (`spec-dev-validation.md` `req-dev-validation-map`, esp.
`-map-2` Honest guard status) is that gaps are *visible*, not implied behind green.

So the generated Map is the union of two sources: the discovered guards, and this
hand-maintained list of everything else. Each entry still carries a `rid` that is
machine-checked to resolve to a real requirement (`test_declared_surface_rid_resolves`),
so a declared surface cannot point at a requirement that does not exist — the same
discipline the guards get, applied to the negative space.

Adding a *guard* never touches this file (discovery finds it). Adding a non-guard
surface — a new behavioral suite, a new gate step, a new manual procedure — adds a
row here, and that addition is the reviewable decision.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeclaredSurface:
    """A validation surface that is not a harness `Guard` (the Map's negative space)."""

    #: Human-readable surface name (the Map's first column).
    surface: str
    #: The requirement it serves — machine-checked to resolve to a real requirement.
    rid: str
    #: When it runs, in the Map's cadence vocabulary.
    cadence: str
    #: Honest guard-status label (Map vocabulary).
    status: str
    #: What enforces it (test module / gate step / script) — the pointer, not a copy.
    enforced_by: str


# Ordered roughly by lifecycle: spawn/teardown, async delivery, health, the Gryphon
# executor-correctness ladder, the cold-boot gate steps, then per-commit behavioral
# suites. Rich "why" lives in each owning spec (references, not copies —
# `req-dev-validation-map-4`); this list is inventory + honest status.
DECLARED_SURFACES: tuple[DeclaredSurface, ...] = (
    DeclaredSurface(
        surface="Spawn-env health",
        rid="req-dev-multisession-smoketest-runtime",
        cadence="Per-spawn",
        status="Manual (CI-unguarded by design)",
        enforced_by="`spec-dev-multisession-smoketest.md` documented procedure",
    ),
    DeclaredSurface(
        surface="Teardown correctness",
        rid="req-dev-multisession-teardown-cleanup",
        cadence="Per-despawn",
        status="Manual (CI-unguarded by design)",
        enforced_by="`spec-dev-multisession-teardown.md` documented procedure",
    ),
    DeclaredSurface(
        surface="Async-delivery — tier 1 (transactional integrity)",
        rid="req-tap-cares-task-backend-transactional-integrity-1",
        cadence="Per-commit (`pytest`)",
        status="CI-guarded",
        enforced_by="`tap_cares` `TestTransactionalIntegrity`",
    ),
    DeclaredSurface(
        surface="Async-delivery — tiers 2–3 (worker/queue/lifecycle)",
        rid="req-tap-cares-task-backend-backlog-2",
        cadence="Deferred",
        status="Named, deferred",
        enforced_by="backlog — no fork/queue/lifecycle harness yet",
    ),
    DeclaredSurface(
        surface="All-plugins CI lane (free-runner fallback)",
        rid="req-dev-validation-all-plugins-lane",
        cadence="CI + promote fallback (TAP_PROMOTE_CI_WORKFLOW)",
        status="Retained fallback — lane PROVEN GREEN in a real Actions run; superseded as the promote gate by the CodeBuild product-line `test_all` lane, kept as the free-runner fallback when CodeBuild is unavailable",
        enforced_by=(
            "`.github/workflows/all-plugins.yml` (boots the `test_all` union, runs the full lane); "
            "`promote-to-main.sh` Step 2.6 runs it when `TAP_PROMOTE_CI_WORKFLOW=all-plugins.yml`"
        ),
    ),
    DeclaredSurface(
        surface="Plugin compatibility floor (requires_tap)",
        rid="req-plugin-extdev-compat-floor",
        cadence="Pre-boot (`python -m tap.preboot`) + author-time (`validate_plugin`)",
        status="CI-guarded",
        enforced_by=(
            "`tap.preboot._requires_tap_gate` (reject-at-boot) + the `requires-tap` "
            "`validate_plugin` check; unit-guarded by `tap/tests/test_core_version.py` and "
            "`tap/tests/test_preboot.py`, exercised end-to-end by the cold-boot gate (grid_fixtures declares a floor)"
        ),
    ),
    DeclaredSurface(
        surface="Per-plugin repo CI (reusable workflow)",
        rid="req-plugin-extdev-repo-ci",
        cadence="Per-PR in external plugin repos (`workflow_call`)",
        status="In development — conformance job is the solid core; boot-and-test is the dial-in surface for Aug-1",
        enforced_by=(
            "`.github/workflows/plugin-ci.yml` — `validate_plugin --strict` against a pinned "
            "core harness on free runners, plus an opt-in boot-and-test job"
        ),
    ),
    DeclaredSurface(
        surface="Scripted plugin release pre-release guard (release-plugin)",
        rid="req-dev-workspace-release",
        cadence="Operator-invoked at plugin release time (`scripts/release-plugin.sh`)",
        status="Built 2026-07-09 — refuses a red release; pure pin-bump core unit-guarded",
        enforced_by=(
            "`scripts/release-plugin.sh` runs `validate_plugin --strict` + the plugin suite "
            "in-container before tagging (refuse-on-red), then bumps consuming boot profiles via "
            "`tap.plugin_release`; the bump core is unit-guarded by `tap/tests/test_plugin_release.py`"
        ),
    ),
    DeclaredSurface(
        surface="Per-product-line CI lanes (CodeBuild)",
        rid="req-dev-validation-product-line-lanes",
        cadence="Pre-push (promote-triggered `test_all` union) + CI (every line on PR)",
        status="Gate-guarded — both lanes (`test_all`, `samsite`) PROVEN GREEN on AWS CodeBuild; the `test_all` union lane is the promote gate (option B); bootstrap-skips the one promote that first lands product-lines.yml on main",
        enforced_by=(
            "`.github/workflows/product-lines.yml` (per-line CodeBuild runners: `test_all` union + `samsite`); "
            "`ci/terraform/codebuild-runners/` (per-line projects/roles/webhook); "
            "`promote-to-main.sh` Step 2.6 dispatches `line=test_all` and blocks on it (req-dev-multisession-ci-gate)"
        ),
    ),
    DeclaredSurface(
        surface="Assembled-instance health",
        rid="req-tap-health-exposure-4",
        cadence="Per-commit (`pytest`) + per-spawn (`manage.py health` gate)",
        status="Partially guarded — CI-guarded units + per-spawn exec gate; full live cold-boot run Named, deferred",
        enforced_by="`tap_health/tests/` + `spawn-session.sh` health gate; folds into the cold-boot cycle",
    ),
    DeclaredSurface(
        surface="Gryphon executor-stage coverage",
        rid="req-gridkin-stage-coverage",
        cadence="Per-commit (`pytest`)",
        status="CI-guarded",
        enforced_by="`plugins/gryphon_playground/tap_plugin/gryphon_playground/tests/test_gridkin_internals.py::TestStageCoverage`",
    ),
    DeclaredSurface(
        surface="Gryphon executor branch coverage (ratchet comparison)",
        rid="req-gridkin-executor-branch-coverage",
        cadence="On-demand script (~10–15 min instrumented run)",
        status="Manual (CI-unguarded by design)",
        enforced_by="`scripts/gryphon-coverage-ratchet` (shared `tap.ratchet.ratchet_floor`); floor well-formedness is the CI guard",
    ),
    DeclaredSurface(
        surface="Gryphon metamorphic TLP",
        rid="req-gridkin-metamorphic-tlp",
        cadence="Per-commit (`pytest`)",
        status="CI-guarded",
        enforced_by="`plugins/gryphon_playground/tap_plugin/gryphon_playground/tests/test_gryphon_metamorphic.py`",
    ),
    DeclaredSurface(
        surface="Gryphon differential property fuzzer",
        rid="req-gridkin-property-fuzz",
        cadence="Per-commit (`pytest`, committed 12×15; env-tunable soak)",
        status="CI-guarded",
        enforced_by="`plugins/gryphon_playground/tap_plugin/gryphon_playground/tests/test_gryphon_fuzz.py`",
    ),
    DeclaredSurface(
        surface="Gryphon fuzz-campaign ledger",
        rid="req-gridkin-fuzz-campaign",
        cadence="On-demand script, loopable for hours",
        status="Manual (CI-unguarded by design) — trend instrument, not a gate",
        enforced_by="`scripts/gryphon-fuzz-campaign`; ledger `gridkin/fuzz-campaign-log.jsonl`",
    ),
    DeclaredSurface(
        surface="Gryphon findings ledger (bug locality)",
        rid="req-gridkin-findings-ledger",
        cadence="Fix-time append + on-demand report",
        status="Split — CI-guarded for well-formedness/vocabulary; Manual for the hotspot analysis",
        enforced_by="`plugins/gryphon_playground/tap_plugin/gryphon_playground/tests/test_gryphon_findings_ledger.py`; ledger `gridkin/gryphon-findings.jsonl`",
    ),
    DeclaredSurface(
        surface="Cold-boot system cycle",
        rid="req-dev-validation-smoke-gate",
        cadence="Pre-push (`scripts/gate`, wired into `promote-to-main.sh`)",
        status="Gate-guarded",
        enforced_by="`tap_boot/management/commands/cold_boot_gate.py`",
    ),
    DeclaredSurface(
        surface="Lean-boot core independence (import-leakage class)",
        rid="req-dev-validation-lean-boot",
        cadence="Pre-push (`scripts/gate-lean`, wired into `promote-to-main.sh`)",
        status="Gate-guarded",
        enforced_by="`scripts/gate-lean` (isolated `tap_leanboot` stack, core-only venv; catches core→plugin-dep imports the full-venv cold-boot gate cannot)",
    ),
    DeclaredSurface(
        surface="FIPS mode enforcement (declared vs actual)",
        rid="req-cicd-base-image-lifecycle-6",
        cadence="Per-boot (`docker/entrypoint.sh`)",
        status="Boot-gated (fail-closed)",
        enforced_by="`tap.fips` (`python -m tap.fips`): executes crypto and asserts a non-approved primitive is refused when TAP_FIPS_MODE=1 — proves the declared mode is enforced, never inspects files (D13/D15); TAP-ABORT on mismatch",
    ),
    DeclaredSurface(
        surface="Crypto Bill-of-Materials (every provider, not just OpenSSL)",
        rid="req-cicd-crypto-bom",
        cadence="Per-commit (`pytest`)",
        status="CI-guarded (fail-closed)",
        enforced_by="`tap.crypto_bom` (via `tap/tests/test_crypto_bom.py`): fingerprints every ELF artifact for crypto-provider signatures (Go/Rust `ring`/`aws-lc`/`libsodium`/bundled-OpenSSL/…) and fails on any provider not dispositioned VALIDATED/out-of-boundary/unreached in `tap.crypto_providers` — catches the silent non-OpenSSL leak `tap.fips` cannot see (L17); scans the `test_all` plugin union",
    ),
    DeclaredSurface(
        surface="System FIPS-provider gate (core + all plugins, global)",
        rid="req-cicd-crypto-bom",
        cadence="Per-boot (`docker/entrypoint.sh`, when `TAP_FIPS_MODE=1`)",
        status="Boot-gated (fail-closed)",
        enforced_by="`python -m tap.crypto_bom --gate`: under FIPS mode, scans the assembled environment (core + every installed plugin) and TAP-ABORTs on any non-validated provider unless an OPERATOR `fips_waivers` entry (boot profile, mandatory reason) excuses it — a plugin cannot excuse itself (declare-vs-decide)",
    ),
    DeclaredSurface(
        surface="Per-plugin crypto posture (conformance)",
        rid="req-cicd-crypto-bom",
        cadence="Per-plugin (`validate_plugin`; `--strict` in conformance CI)",
        status="Conformance-guarded (warn; strict→fail)",
        enforced_by="`tap_plugins.validate` `crypto-providers` check → `tap.crypto_bom.scan_plugin`: reports a plugin's shipped/declared crypto providers so a leak is visible at authoring time",
    ),
    DeclaredSurface(
        surface="Migration completeness (`makemigrations --check`)",
        rid="req-dev-validation-smoke-gate",
        cadence="Pre-push (`cold_boot_gate` step `schema:makemigrations`)",
        status="Gate-guarded",
        enforced_by="`cold_boot_gate` step `schema:makemigrations`",
    ),
    DeclaredSurface(
        surface="Canary tier",
        rid="req-dev-validation-canary-tier",
        cadence="Pre-push + per-commit",
        status="Gate-guarded *(target)* — Named, deferred until implemented",
        enforced_by="blast-radius subset (target); not yet built",
    ),
    DeclaredSurface(
        surface="Web render smoke (login/landing)",
        rid="req-web-nav-chrome-read-free-3",
        cadence="Per-commit (`pytest -m smoke`)",
        status="CI-guarded",
        enforced_by="`tap_auth/tests/test_login_wall.py` (`@pytest.mark.smoke`)",
    ),
    DeclaredSurface(
        surface="Read-only search write detection",
        rid="req-grid-search-readonly",
        cadence="Per-commit (`pytest`)",
        status="CI-guarded",
        enforced_by="`tap_grid/tests/test_search_readonly_guard.py`",
    ),
    DeclaredSurface(
        surface="Plugin report contract",
        rid="req-plugin-arch-install-registry-3",
        cadence="Per-commit (`pytest`) + on every report build",
        status="CI-guarded",
        enforced_by="`tap_plugins/tests/test_report.py` (schema validation)",
    ),
)
