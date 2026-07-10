# Development Validation

## Philosophy

For the current solo dog-food window (one developer, running real security assessments from the system on a laptop, through roughly mid-2026), the developer's own usage *is* the de facto whole-system integration suite. That is why the Steady-Queue-class transaction-visibility bug was caught at all — not by a test, but by the system being used. The automated validation gate's job is therefore deliberately narrow: catch what hands-on usage *cannot* — a cold boot from zero, the spawn-off-`main` path, and a capability that has gone "cold" (built but no longer exercised in the daily loop) — in the window between the moments the developer would otherwise notice. Its primary purpose is protecting the multi-session workflow: a rotted or broken `main` silently poisons every session spawned from it.

This spec is the **center of gravity for validation tracking**. It owns the cross-cutting pre-push gate and an authoritative **Validation Map**; it *references* the leaf validation surfaces (spawn-env smoke, teardown, the log-site scanner, the task-backend async-delivery tiers) rather than re-specifying them. As environments multiply, stage-validation and prod-validation become additive: new Map rows and sibling specs under this index, not divergent reinventions.

The discipline running through every requirement here is honest coverage accounting, adopted from the false-confidence failure mode named in `docs/aar/2026-05-16-aws-collector-sprint-sprawl.md` §4 and `spec-tap-cares-task-backend.md`: **a requirement whose only guard is a one-time manual check or "the suite still passes" is effectively unguarded, and MUST be labeled CI-unguarded — by design, not by oversight.** "Green" is only meaningful if known-broken is enumerated in the repository and never in a human's memory.

## Goals

|   |   |  |
| :---: | --- | --- |
| 1. | Honest Validation Map | One authoritative inventory of every validation surface, what it proves, when it runs, and its honest guard status. |
| 2. | Cold-Path Coverage | The gate asserts what dog-fooding structurally cannot: cold boot, spawn-off-`main`, and cold flows. |
| 3. | Binary Gate | Green means green. Known-broken is enumerated in-repo with per-entry justification and ratchets toward zero. |
| 4. | Pre-Push Enforcement | The promote path runs the gate and refuses to advance `origin/main` on red. |
| 5. | Additive Future | Stage- and prod-validation slot in as new Map rows + sibling specs, never as parallel reinventions. |

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-dev-validation-map | [Validation Map](#validation-map) | Implemented | The spine: authoritative inventory of every validation surface |
| req-dev-validation-smoke-gate | [Cold-Boot Smoke Gate](#cold-boot-smoke-gate) | Implemented | Ordered cold-boot-one-cycle, halt-on-failure (`manage.py cold_boot_gate` / `scripts/gate`) |
| req-dev-validation-real-backend | [Real-Backend Fidelity](#real-backend-fidelity) | Implemented | Gate runs the real task backend, never `ImmediateBackend` |
| req-dev-validation-lean-boot | [Lean-Boot Independence Gate](#lean-boot-independence-gate) | Implemented | Fresh, isolated, lean-installed stack boots `core`; catches core→plugin-dep import leakage (`scripts/gate-lean`) |
| req-dev-validation-canary-tier | [Canary Test Tier](#canary-test-tier) | Proposed | `-m smoke` blast-radius subset; does not substitute for the gate |
| req-dev-validation-known-broken | [Known-Broken Manifest](#known-broken-manifest) | Implemented | In-repo, ratchets down; named here as the house convention |
| req-dev-validation-collection-complete | [Collection Completeness](#collection-completeness) | Implemented | Every test file on disk is collected by the gate run; discovery not an allow-list; validates the validator |
| req-dev-validation-promote-hook | [Promote-Path Enforcement](#promote-path-enforcement) | Implemented | Reciprocal of `req-dev-multisession-promote-gate` |
| req-dev-validation-ratchet-harness | [Reusable Ratchet Harness](#reusable-ratchet-harness) | Implemented | `tap/ratchet.py` + `tap.guards` harness; every bespoke ratchet migrated onto it (provenance-schema sub-req deferred as YAGNI) |
| req-dev-validation-mypy-ratchet | [Static Typing Ratchet](#static-typing-ratchet) | Implemented | `mypy .` strict-mode error set frozen per file+error-code and ratcheting down; blocks new errors. Install-aware (filters to core + installed-plugin rows on both sides — see [spec-plugin-validation-distribution.md](spec-plugin-validation-distribution.md)) |
| req-dev-validation-suite-tiers | [Suite Tiering & Performance](#suite-tiering--performance) | Partially Implemented | xdist full + `--fast` lanes built (`scripts/test`); relevance-gated Gryphon-corpus selection built (coarse affected lane for the one dominant-cost corpus); profiled `slow` designations + full test-impact analysis + per-profile fast lane still to build (coupled to the streamlined boot profiles) |
| req-dev-validation-all-plugins-lane | [All-Plugins CI Lane](#all-plugins-ci-lane) | Proposed | Server-side lane that boots the full plugin union and runs the whole suite — the blocking all-plugins authority a focused local stack structurally cannot be once plugins leave the monorepo. Local validates what's installed here; this lane owns all-plugins truth. The boot record IS the known-good-set (BOM) it verifies. |
| req-dev-validation-product-line-lanes | [Per-Product-Line CI Lanes](#per-product-line-ci-lanes) | Implemented | Validate each product line (a plugin-pack + boot profile) on its own AWS CodeBuild GitHub Actions runner, in parallel across lines — parallelism along the product axis, not arbitrary shards. In-account IAM gives each lane native Bedrock / `aws_core` capability. The active CI direction; supersedes free-runner sharding. Infra applied (account 180731181784); `test_all` + `samsite` lanes proven green (2026-07-08); `test_all` union lane wired as the promote gate. The `samsite` git-install path is exercised end-to-end (PAT resolved from Secrets Manager via the secret-source seam); flipping `samsite.boot.json` fully back to git-source pends compliance_core/identity_core eviction + v0.2.0 re-release. |

Leaf surfaces referenced by the Map are owned elsewhere: spawn-env smoke in [spec-dev-multisession-smoketest.md](spec-dev-multisession-smoketest.md), teardown in [spec-dev-multisession-teardown.md](spec-dev-multisession-teardown.md), the log-site scanner in [spec-tap-logging.md](spec-tap-logging.md), and the async-delivery tiers in [spec-tap-cares-task-backend.md](../tap_cares/specs/spec-tap-cares-task-backend.md) (`req-tap-cares-task-backend-backlog-2`). This spec does not re-specify them.

Keeping the validation authority itself **plugin-agnostic** — so evicting a plugin lifts its guards, ratchet-baseline rows, and declared Map surfaces out cleanly rather than stranding central references — is specified in [spec-plugin-validation-distribution.md](spec-plugin-validation-distribution.md). The install-aware ratchet filtering it defines (a plugin-spanning ratchet compares core + installed-plugin rows only) is what lets a focused local stack run the mypy ratchet and the profile-resolution guard green while this lane owns full-set truth.

### Validation Map
----
RID: `req-dev-validation-map`
Status: `Implemented`

The Validation Map is the spine of this spec and the single authoritative inventory of every validation surface in TAP. A surface that is not in the Map is, by definition, unaccounted-for. The Map is **generated from the code**, not hand-maintained: a guarded surface earns its row by being a discovered `Guard` (`tap.guards`), and a non-guard surface (a behavioral suite, a gate step, a manual/deferred procedure) earns its row from `tap.guards.surfaces.DECLARED_SURFACES`. Adding a validation surface therefore means adding its guard or its declared-surface entry — each carrying a requirement `rid` that is machine-checked to resolve — and regenerating; that addition is the reviewable decision. The Map records, per surface, its cadence and its honest guard status using the vocabulary below — including surfaces that are deliberately manual or deferred, so the validation posture and every gap are visible in one place rather than implied behind green checkmarks.

#### Guard-status vocabulary

- **CI-guarded** — failure is caught automatically by a committed test/gate that runs without human initiative (e.g. `pytest`).
- **Gate-guarded** — caught automatically by the pre-push gate ([Cold-Boot Smoke Gate](#cold-boot-smoke-gate)) before `origin/main` advances.
- **Manual (CI-unguarded by design)** — verified only when a human runs a documented procedure; labeled as such deliberately, not by oversight.
- **Named, deferred** — a known gap with an owning spec/backlog entry and a deferral trigger; not yet guarded.

#### The Map

The inventory below is **generated** from the code — the discovered `Guard`
classes (`tap.guards`) plus the declared non-guard surfaces
(`tap.guards.surfaces.DECLARED_SURFACES`) — by `manage.py guards --sync-map`, and
a meta-test (`test_spec_map_in_sync`) fails if this block drifts from that output.
So the guarded rows can never fall out of step with the guards that enforce them,
and every row's Requirement is machine-checked to resolve to a real requirement
(`test_guard_rid_resolves` / `test_declared_surface_rid_resolves`). Edit a guard or
`DECLARED_SURFACES`, then run `manage.py guards --sync-map`; do not hand-edit the
block. Rich per-surface rationale lives in each owning spec and in each guard's
`description` (`manage.py guards`), not duplicated here (`req-dev-validation-map-4`).

<!-- BEGIN GENERATED MAP — manage.py guards --sync-map -->

| Surface | Requirement | Cadence | Status | Enforced by |
| --- | --- | --- | --- | --- |
| `record_*` site tokens | `req-tap-cares-collector-job-model-15` | Per-commit (`pytest`) | CI-guarded | `tap_cares.guards.record_site` (via `tap/tests/test_guards.py`) |
| All-plugins CI lane (free-runner fallback) | `req-dev-validation-all-plugins-lane` | CI + promote fallback (TAP_PROMOTE_CI_WORKFLOW) | Retained fallback — lane PROVEN GREEN in a real Actions run; superseded as the promote gate by the CodeBuild product-line `test_all` lane, kept as the free-runner fallback when CodeBuild is unavailable | `.github/workflows/all-plugins.yml` (boots the `test_all` union, runs the full lane); `promote-to-main.sh` Step 2.6 runs it when `TAP_PROMOTE_CI_WORKFLOW=all-plugins.yml` |
| Assembled-instance health | `req-tap-health-exposure-4` | Per-commit (`pytest`) + per-spawn (`manage.py health` gate) | Partially guarded — CI-guarded units + per-spawn exec gate; full live cold-boot run Named, deferred | `tap_health/tests/` + `spawn-session.sh` health gate; folds into the cold-boot cycle |
| Async-delivery — tier 1 (transactional integrity) | `req-tap-cares-task-backend-transactional-integrity-1` | Per-commit (`pytest`) | CI-guarded | `tap_cares` `TestTransactionalIntegrity` |
| Async-delivery — tiers 2–3 (worker/queue/lifecycle) | `req-tap-cares-task-backend-backlog-2` | Deferred | Named, deferred | backlog — no fork/queue/lifecycle harness yet |
| Authz coverage | `req-tap-auth-policy-9` | Per-commit (`pytest`) | CI-guarded | `tap.guards.authz` (via `tap/tests/test_guards.py`) |
| Canary tier | `req-dev-validation-canary-tier` | Pre-push + per-commit | Gate-guarded *(target)* — Named, deferred until implemented | blast-radius subset (target); not yet built |
| Cold-boot system cycle | `req-dev-validation-smoke-gate` | Pre-push (`scripts/gate`, wired into `promote-to-main.sh`) | Gate-guarded | `tap_boot/management/commands/cold_boot_gate.py` |
| Collection completeness | `req-dev-validation-collection-complete` | Per-commit (`pytest`) | CI-guarded | `tap.guards.collection_addopts`, `tap.guards.collection_completeness` (via `tap/tests/test_guards.py`) |
| Direct-write coverage | `req-tap-auth-policy-9` | Per-commit (`pytest`) | CI-guarded | `tap.guards.direct_write` (via `tap/tests/test_guards.py`) |
| Family-B public surface (pre-boot/boot) | `req-service-boundary-family-b-surface` | Per-commit (`pytest`) | CI-guarded | `tap.guards.public_surface` (via `tap/tests/test_guards.py`) |
| Gryphon branch-coverage floor (well-formedness) | `req-gridkin-executor-branch-coverage` | Per-commit (`pytest`) | CI-guarded | `tap_grid.guards.gryphon_coverage_floor` (via `tap/tests/test_guards.py`) |
| Gryphon differential property fuzzer | `req-gridkin-property-fuzz` | Per-commit (`pytest`, committed 12×15; env-tunable soak) | CI-guarded | `plugins/gryphon_playground/tap_plugin/gryphon_playground/tests/test_gryphon_fuzz.py` |
| Gryphon executor branch coverage (ratchet comparison) | `req-gridkin-executor-branch-coverage` | On-demand script (~10–15 min instrumented run) | Manual (CI-unguarded by design) | `scripts/gryphon-coverage-ratchet` (shared `tap.ratchet.ratchet_floor`); floor well-formedness is the CI guard |
| Gryphon executor-stage coverage | `req-gridkin-stage-coverage` | Per-commit (`pytest`) | CI-guarded | `plugins/gryphon_playground/tap_plugin/gryphon_playground/tests/test_gridkin_internals.py::TestStageCoverage` |
| Gryphon findings ledger (bug locality) | `req-gridkin-findings-ledger` | Fix-time append + on-demand report | Split — CI-guarded for well-formedness/vocabulary; Manual for the hotspot analysis | `plugins/gryphon_playground/tap_plugin/gryphon_playground/tests/test_gryphon_findings_ledger.py`; ledger `gridkin/gryphon-findings.jsonl` |
| Gryphon fuzz-campaign ledger | `req-gridkin-fuzz-campaign` | On-demand script, loopable for hours | Manual (CI-unguarded by design) — trend instrument, not a gate | `scripts/gryphon-fuzz-campaign`; ledger `gridkin/fuzz-campaign-log.jsonl` |
| Gryphon metamorphic TLP | `req-gridkin-metamorphic-tlp` | Per-commit (`pytest`) | CI-guarded | `plugins/gryphon_playground/tap_plugin/gryphon_playground/tests/test_gryphon_metamorphic.py` |
| JSON-file naming | `req-tap-json-naming` | Per-commit (`pytest`) | CI-guarded | `tap.guards.json_naming` (via `tap/tests/test_guards.py`) |
| Lean-boot core independence (import-leakage class) | `req-dev-validation-lean-boot` | Pre-push (`scripts/gate-lean`, wired into `promote-to-main.sh`) | Gate-guarded | `scripts/gate-lean` (isolated `tap_leanboot` stack, core-only venv; catches core→plugin-dep imports the full-venv cold-boot gate cannot) |
| Log-site tokens | `req-tap-logging-site-id-scanner` | Per-commit (`pytest`) | CI-guarded | `tap.guards.log_site_baseline`, `tap.guards.log_site_format`, `tap.guards.log_site_uniqueness` (via `tap/tests/test_guards.py`) |
| Migration completeness (`makemigrations --check`) | `req-dev-validation-smoke-gate` | Pre-push (`cold_boot_gate` step `schema:makemigrations`) | Gate-guarded | `cold_boot_gate` step `schema:makemigrations` |
| Per-plugin repo CI (reusable workflow) | `req-plugin-extdev-repo-ci` | Per-PR in external plugin repos (`workflow_call`) | In development — conformance job is the solid core; boot-and-test is the dial-in surface for Aug-1 | `.github/workflows/plugin-ci.yml` — `validate_plugin --strict` against a pinned core harness on free runners, plus an opt-in boot-and-test job |
| Per-product-line CI lanes (CodeBuild) | `req-dev-validation-product-line-lanes` | Pre-push (promote-triggered `test_all` union) + CI (every line on PR) | Gate-guarded — both lanes (`test_all`, `samsite`) PROVEN GREEN on AWS CodeBuild; the `test_all` union lane is the promote gate (option B); bootstrap-skips the one promote that first lands product-lines.yml on main | `.github/workflows/product-lines.yml` (per-line CodeBuild runners: `test_all` union + `samsite`); `ci/terraform/codebuild-runners/` (per-line projects/roles/webhook); `promote-to-main.sh` Step 2.6 dispatches `line=test_all` and blocks on it (req-dev-multisession-ci-gate) |
| Per-profile boot resolution | `req-dev-validation-smoke-gate` | Per-commit (`pytest`) + pre-push (`cold_boot_gate`) | CI-guarded + Gate-guarded | `tap_boot.guards.profile_resolution` (via `tap/tests/test_guards.py`) |
| Plugin compatibility floor (requires_tap) | `req-plugin-extdev-compat-floor` | Pre-boot (`python -m tap.preboot`) + author-time (`validate_plugin`) | CI-guarded | `tap.preboot._requires_tap_gate` (reject-at-boot) + the `requires-tap` `validate_plugin` check; unit-guarded by `tap/tests/test_core_version.py` and `tap/tests/test_preboot.py`, exercised end-to-end by the cold-boot gate (grid_fixtures declares a floor) |
| Plugin dependency consistency | `req-plugin-arch-dependencies-4` | Pre-boot (`python -m tap.preboot`) + per-commit (`pytest`) | CI-guarded | `tap_plugins.guards.dependency_consistency` (via `tap/tests/test_guards.py`) |
| Plugin report contract | `req-plugin-arch-install-registry-3` | Per-commit (`pytest`) + on every report build | CI-guarded | `tap_plugins/tests/test_report.py` (schema validation) |
| Plugin type-ownership affixes | `req-plugin-type-collision-loud` | Per-commit (`pytest`) | CI-guarded | `tap_plugins.guards.type_ownership` (via `tap/tests/test_guards.py`) |
| Read-only search write detection | `req-grid-search-readonly` | Per-commit (`pytest`) | CI-guarded | `tap_grid/tests/test_search_readonly_guard.py` |
| Recurring-task uniqueness | `req-tap-cares-task-backend-recurring-scope-4` | Per-commit (`pytest`) | CI-guarded | `tap_cares.guards.recurring` (via `tap/tests/test_guards.py`) |
| Schedule grift target integrity | `req-tap-cares-collector-model-10` | Per-commit (`pytest`) | CI-guarded | `tap_cares.guards.schedule_grift` (via `tap/tests/test_guards.py`) |
| Scripted plugin release pre-release guard (release-plugin) | `req-dev-workspace-release` | Operator-invoked at plugin release time (`scripts/release-plugin.sh`) | Built 2026-07-09 — refuses a red release; pure pin-bump core unit-guarded | `scripts/release-plugin.sh` runs `validate_plugin --strict` + the plugin suite in-container before tagging (refuse-on-red), then bumps consuming boot profiles via `tap.plugin_release`; the bump core is unit-guarded by `tap/tests/test_plugin_release.py` |
| Secret leak guard | `req-tap-cares-secrets-leak-guard` | Per-commit (`pytest`) | CI-guarded | `tap.guards.secret_leak` (via `tap/tests/test_guards.py`) |
| Service-layer boundary coverage | `req-service-boundary-guard` | Per-commit (`pytest`) | CI-guarded | `tap.guards.service_boundary` (via `tap/tests/test_guards.py`) |
| Service-layer boundary import encapsulation | `req-service-boundary-inviolability` | Per-commit (`pytest`) | CI-guarded | `tap.guards.service_boundary_imports` (via `tap/tests/test_guards.py`) |
| Spawn-env health | `req-dev-multisession-smoketest-runtime` | Per-spawn | Manual (CI-unguarded by design) | `spec-dev-multisession-smoketest.md` documented procedure |
| Static typing (mypy) | `req-dev-validation-mypy-ratchet` | Per-commit (`pytest`) | CI-guarded | `tap.guards.mypy` (via `tap/tests/test_guards.py`) |
| Teardown correctness | `req-dev-multisession-teardown-cleanup` | Per-despawn | Manual (CI-unguarded by design) | `spec-dev-multisession-teardown.md` documented procedure |
| Web render smoke (login/landing) | `req-web-nav-chrome-read-free-3` | Per-commit (`pytest -m smoke`) | CI-guarded | `tap_auth/tests/test_login_wall.py` (`@pytest.mark.smoke`) |

<!-- END GENERATED MAP -->

Rows marked *(target)* describe the intended state once this spec is implemented; their guard status is honestly `Named, deferred` until then. The Map is regenerated (`manage.py guards --sync-map`) in the same change as any new or retired validation surface, and reviewed when it changes — the change to the guard/declared-surface set (and the resulting block diff) *is* the visible decision.

**Collection-scope caveat (a guard that isn't collected does not guard).** A test that the default `pytest` run does not collect is **invisible to the gate** — it passes when named explicitly and silently protects nothing otherwise. This let the 2026-07-01 login regression ship green: `tap_auth`, `tap_boot`, and `tap_cares` all sat outside the `testpaths` **allow-list**, so their tests (including `test_login_wall.py`'s render assertions) were never in the gate. The allow-list is fail-open over a scattered per-app layout — a new app is uncollected until someone remembers to list it. The fix is structural, not another list entry: `pyproject.toml` no longer sets `testpaths`, so pytest **discovers** every test file from the repo root (an ignore-list, fail-safe), and [Collection Completeness](#collection-completeness) asserts the outcome so the scope can never silently narrow again. See that requirement.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-validation-map-1 | Map is authoritative | Implemented | Every validation surface in the repository has exactly one row in the Map. A surface absent from the Map is treated as unaccounted-for. | The Map is generated from the discovered guards + `DECLARED_SURFACES`, so a guard/surface with no row cannot exist. |
| req-dev-validation-map-2 | Honest guard status | Implemented | Each row's guard status uses the defined vocabulary; manual/deferred surfaces are labeled explicitly, never implied. | Counters the false-confidence failure mode. Status is carried per-guard and per-declared-surface, rendered into the row. |
| req-dev-validation-map-3 | Co-change discipline | Implemented | Adding, moving, or retiring a validation surface anywhere REQUIRES updating its Map row in the same change. | Enforced mechanically: adding a guard/surface changes the generated block, and `test_spec_map_in_sync` fails until it is regenerated. |
| req-dev-validation-map-4 | References, not copies | Implemented | The Map points at owning specs; it does not duplicate their requirements or acceptance criteria. | Prevents cross-spec drift. Rich "why" lives in guard `description` + owning specs. |
| req-dev-validation-map-5 | Generated, not hand-maintained | Implemented | The Map inventory is generated from the discovered guards + `DECLARED_SURFACES` by `manage.py guards --sync-map`; a meta-test fails if the committed block drifts from that output. Guarded rows cannot fall out of step with the code that enforces them. | `tap/tests/test_guards.py::test_spec_map_in_sync`. Closes the stale-Map-row drift class (an "Enforced by" pointer going stale unnoticed). |
| req-dev-validation-map-6 | Every surface resolves to a requirement | Implemented | Each guard's `rid` and each declared surface's `rid` resolves to a requirement actually defined in some spec (RID heading or requirements-table cell), not merely referenced. A surface cannot point at a requirement that does not exist. | Replaces the prior "map_row ∈ prose table" check. Caught `req-dev-validation-mypy-ratchet` being referenced-but-undefined. |

### Cold-Boot Smoke Gate
----
RID: `req-dev-validation-smoke-gate`
Status: `Implemented`

The gate is an ordered, deterministic, halt-on-failure check that a freshly-built environment can boot from zero and complete one real end-to-end cycle. It adopts the established shape of [spec-dev-multisession-smoketest.md](spec-dev-multisession-smoketest.md): an ordered set of checks with expected outcomes, run top-to-bottom, where any failure halts and is reported. It runs **inside the existing compose image** — never a reimplemented environment — because the container's Python build differs from a stock host interpreter and an environment that does not reproduce the image will diverge.

The cycle, in order:

1. Fresh database (no pre-existing state).
2. `migrate` applies cleanly from zero.
3. `import_plugin_grift --all` seeds plugin data (strict; a failed bundle fails the gate).
4. One real collector runs to a terminal `CollectionJob` state through the real task backend ([Real-Backend Fidelity](#real-backend-fidelity)).
5. One scheduler fire is evaluated.
6. Resulting grid state is asserted (the collector's expected nodes/edges/batch landed).

It is explicitly **not** broad correctness coverage — that is the canary tier and the deferred per-flow suites. It is one ordered run on a fresh database with no per-test isolation; this is intentional and matches the per-session isolated-Postgres model rather than fighting transactional-rollback semantics. Wall-clock budget: **correctness and real-backend fidelity over speed**. A 10+ minute promote that the developer steps away from is explicitly acceptable (the human is offline during it by design); the gate is not optimized for latency at the cost of fidelity. The cold-boot cycle is fixed; the canary tier is the tunable lever if total time must be bounded.

**As built (Phase 1).** The gate is `manage.py cold_boot_gate` (in `tap_boot`), the single artifact local dev, `scripts/gate`, and `scripts/promote-to-main.sh` all invoke identically. `scripts/gate` provisions a **fresh scratch database** on the running stack's Postgres (a management command cannot cleanly `migrate`-from-zero its own connection), points the command's `DATABASE_URL` at it, and drops it on exit — so the cycle runs inside the existing compose image (req-...-5) without a second stack or touching the session DB. The ordered steps: `schema:migrate` (createcachetable→migrate from zero) → `schema:makemigrations` (`--check`) → `profiles:resolve` (every *installable* profile resolves; see the per-profile axis below) → `seed:boot-test_all` (strict `test_all` union boot — the seed path across every plugin; formerly `seed:boot-base` before the 2026-07-03 baseline flip renamed `base`→`test_all`) → `collector:cycle` (real backend + in-process drain + PRODUCED_BATCH assertion, scheduler evaluated in the same drain) → `health`. **Measured wall-clock: ~66–107s** (green path). Because `seed:boot-test_all` boots the full plugin union, the gate is a **full-install** check: the promote runs it with `--skip-if-not-installable`, so a focused session (where `test_all` is not installable) skips it loudly and the [all-plugins CI lane](#all-plugins-ci-lane) owns full cold-boot truth (`req-dev-validation-smoke-gate-8`). `profiles:resolve` is install-aware through the same shared filter (`tap_boot.profile.installable_profile_ids`) that backs both the pytest profile-resolution guard and this skip predicate. The collector fired is the **deterministic offline canary** `grid_fixtures:canary` (`--collector` overrides it to drive a real domain collector): a `CollectorBase` in the neutral `grid_fixtures` fixtures plugin that emits a fixed two-node/one-edge `grid_fixtures__*` GRIFT batch from inline constants — **no network, no credentials, no filesystem read** — so the gate's real-backend cycle positively asserts grid mutation without ever flaking on an upstream being down. It is self-contained (emits its own plugin's vocabulary) and, like all of `grid_fixtures`, installs only into dev/test profiles, never a lean customer profile. Per-commit guard: `plugins/grid_fixtures/tap_plugin/grid_fixtures/tests/test_canary_collector.py`.

**Per-profile axis (agenda item 5).** The gate cold-resolves **every shipped `boot/*.boot.json` profile** against the live registries (`boot --check` → the zero-mutation pre-resolution the real boot runs), rather than making pytest discovery plugin-aware (which would fight the design and require de-hardcoding lotr from the core suites). This is the axis that catches the same bug class as the 2026-07-02 `base`-profile break — and, on the build of this gate, immediately caught a live one: `boot/samsite.boot.json`'s four fire-collector keys were still on their stale module-path scopes (`tap_plugin.aws_core.collectors.boto3_collector.collector:boto3`) after the collector-identity refactor repointed only the grift `SCHEDULED_TARGET` edges, so `boot --profile samsite` — the live-demo profile behind the active roadmap Done-Test — aborted at resolution. Fixed to `scope:key` (`aws_core:boto3`, …) and regression-locked by `tap_boot/tests/test_shipped_profiles_resolve.py`. Firing collectors that need live network/creds (aws, github) is out of the hermetic gate by design; the break lives in resolution, before any firing.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-validation-smoke-gate-1 | Cold boot from zero | Implemented | The gate starts from a fresh database; `migrate` applies with no pre-existing schema/data. | `scripts/gate` provisions a fresh scratch DB; step `schema:migrate`. |
| req-dev-validation-smoke-gate-2 | Seed is strict | Implemented | Strict seed; any failed bundle fails the gate. | Step `seed:boot-test_all` runs the real `test_all` (union) boot (population seeds through the same `seed_plugin` op `import_plugin_grift` uses); aligns with `req-dev-multisession-spawn-import-strict-1`. Renamed from `seed:boot-base` in the 2026-07-03 baseline flip. |
| req-dev-validation-smoke-gate-3 | One real cycle | Implemented | A collector reaches a terminal `CollectionJob` state and a scheduler fire is evaluated within one ordered run. | Step `collector:cycle`; the in-process drain dispatches the scheduler queue in the same run. |
| req-dev-validation-smoke-gate-4 | Grid state asserted | Implemented | The cycle's expected grid mutation is positively asserted, not inferred from absence of error. | Counters the false-confidence failure mode. Asserted via `PRODUCED_BATCH` edges (disposition `imported`); a documented idempotent no-op (e.g. `DIFF_EMPTY`) is a valid SUCCESSFUL outcome, not a gate failure. **Drift resolved (2026-06-11):** `req-grid-edge-produced-batch` is built; the `grift_batches` field is removed. |
| req-dev-validation-smoke-gate-5 | Runs in the compose image | Implemented | The gate executes inside the existing compose stack image, not a reconstructed environment. | The container Python build is non-stock. `scripts/gate` runs the command via `dc exec web`. |
| req-dev-validation-smoke-gate-6 | Halt and report | Implemented | The first failing check halts the run and reports the failing step; the gate exits non-zero. | Verified live (a bogus `--collector` halts at step 5, skips step 6, exits 1). |
| req-dev-validation-smoke-gate-7 | Every installable profile resolves | Implemented | The gate cold-resolves every shipped boot profile whose plugins are installed in this stack against the live registries (per-profile axis); a rotted fire-collector key or missing plugin/bundle fails the gate. | Step `profiles:resolve` + per-commit `test_shipped_profiles_resolve.py`. Install-aware via the single shared filter `tap_boot.profile.installable_profile_ids` (the same one the pytest guard and the focused-skip check below use — one definition, no drift). On a full stack that is every profile. Caught + fixed the live `samsite` break on build. |
| req-dev-validation-smoke-gate-8 | Focused-stack skip (full-install gate) | Implemented | Step `seed:boot-test_all` boots the whole `test_all` union, so this gate is inherently a **full-install** check. On a focused stack (a plugin subset installed — `test_all` not installable) the promote invokes it with `--skip-if-not-installable`; the gate emits a loud SKIP and exits 0, delegating full cold-boot truth to the all-plugins CI lane. | The local gate validates what's installed; the [all-plugins CI lane](#all-plugins-ci-lane) (`req-dev-validation-all-plugins-lane`) boots `test_all` on a full-install runner and owns full-set truth. Mirrors the install-aware pytest lane (`req-dev-validation-collection-complete-4`) and profile-resolution guard. The full-stack predicate is `"test_all" in installable_profile_ids(...)`. A standalone `scripts/gate` (no flag) still runs fully — the skip is opt-in, so the gate stays honest for a full manual check. |

### Real-Backend Fidelity
----
RID: `req-dev-validation-real-backend`
Status: `Implemented`

This is the load-bearing requirement. The gate MUST exercise the cycle against the **real DB-backed task backend**, never the pytest `ImmediateBackend` substitute. `ImmediateBackend` runs the task inline in the enqueuing transaction, which masks exactly the bug class that motivated this spec: a row enqueued in a transaction a separate worker connection cannot yet see. A gate that runs under the substitute backend would have stayed green through the Steady-Queue incident and is therefore not a gate at all for this failure class.

This positions the gate as the real-backend, post-commit, in-process-drain tier: higher fidelity than any `ImmediateBackend` test, and complementary to — not a replacement for — the deferred out-of-process real-worker tiers owned by `spec-tap-cares-task-backend.md` `req-tap-cares-task-backend-backlog-2` (tier 2: real `SteadyQueueBackend` + worker polled for terminal state; tier 3: fork-safety CI smoke job). Those tiers remain `Named, deferred` in the Map; this requirement does not absorb them.

**Mechanism (Phase-0 proven, Phase-1 shared).** The in-process drain — extracted to `tap_cares/dev_validation.py:drain_ready_executions` and shared by the Phase-0 spike and the Phase-1 gate — is the production Steady Queue primitives without the supervisor/fork/thread-pool/polling-loop that normally *drive* them: `ScheduledExecution.dispatch_next_batch()` → `ReadyExecution.objects.claim(queues, limit, process_id)` → `ClaimedExecution.perform()`, looped to empty or a deadline. Two concrete facts established by the Phase-0 spike (`tap_cares/management/commands/dev_validation_spike.py`, run inside the compose image under real `tap.settings`): (1) `ReadyExecution.claim` short-circuits to `[]` when `process_id is None`, so the drain MUST register a synthetic `steady_queue` `Process` (no heartbeat/supervisor/fork) and pass its id, deregistering after; (2) under `manage.py` (autocommit, not pytest), `run_collection`'s `transaction.on_commit` enqueue fires immediately and the `Job`+`ReadyExecution` rows are committed before the drain claims them — the real commit boundary `ImmediateBackend` never crosses. The spike proved the linchpin end-to-end (real enqueue → commit → drain → terminal `CollectionJob`) and proved teeth (no-drain ⇒ job stays `READY` ⇒ non-zero exit; a `FAILED` collector ⇒ non-zero exit surfacing the readiness reason). Grid-state assertion counts `CollectionJob --PRODUCED_BATCH--> Batch` edges with `disposition="imported"` (the Phase-0 `grift_batches` drift is now closed — see the note on `req-dev-validation-smoke-gate-4`).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-validation-real-backend-1 | Not `ImmediateBackend` | Implemented | The gate configures the real DB-backed task backend; `ImmediateBackend` is never used in the gate path. | `cold_boot_gate` refuses to run under `ImmediateBackend` (`_guard_real_backend`). |
| req-dev-validation-real-backend-2 | Terminal state via real backend | Implemented | The collector reaches a terminal `CollectionJob` state through the real backend's enqueue→commit→drain path, not an inline call. | Shared `drain_ready_executions`: synthetic `Process` + `ReadyExecution.claim` + `ClaimedExecution.perform` loop; `claim` requires a non-null `process_id`. Verified live (SUCCESSFUL, 1 batch imported). |
| req-dev-validation-real-backend-3 | Defers tiers 2–3 honestly | Implemented | Out-of-process real-worker concurrency/fork/lifecycle coverage is explicitly out of scope here and tracked under `req-tap-cares-task-backend-backlog-2`. | No scope absorption; no parallel vocabulary. |

### Canary Test Tier
----
RID: `req-dev-validation-canary-tier`
Status: `Proposed`

A `@pytest.mark.smoke` marker designates the high-signal canary subset of the fast test suite: tests whose failure means "the foundation moved, dive deep," as opposed to "one feature regressed." The promotion criterion is **blast radius, not importance**: a test earns the marker only if it sits on the trunk — its failure predicts mass downstream failure (e.g. service-layer Entity creation, plugin GRIFT import landing on the grid, registry collector resolution). A narrow test of one feature's edge case is not a canary even when the feature is important. The criterion is deliberately answerable in seconds at test-authoring time, by the author — the only person who reliably knows a test's blast radius — because retrofitting canary designation later is archaeology that does not happen.

The canary tier runs under the standard fast-test environment (including `ImmediateBackend`) and therefore **does not and cannot substitute for** the [Cold-Boot Smoke Gate](#cold-boot-smoke-gate) / [Real-Backend Fidelity](#real-backend-fidelity): tagging a unit test `smoke` does not close the real-backend gap. The gate is both: the cold-boot real-backend cycle *and* `pytest -m smoke`.

Canary membership is governed as a bounded, reviewed set (see [Known-Broken Manifest](#known-broken-manifest) for the shared house pattern): the marker lives in the test, but the *set* of markers is enumerated with a one-line "what breaks downstream if this fails" per entry, and a fitness cap (runtime or count) forces eviction when a better-upstream canary supersedes one.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-validation-canary-tier-1 | Marker exists | Proposed | `@pytest.mark.smoke` is a registered marker; `pytest -m smoke` selects the canary subset. | |
| req-dev-validation-canary-tier-2 | Blast-radius criterion | Proposed | A test earns `smoke` only if its failure predicts broad downstream failure (trunk, not branch). Importance alone is explicitly insufficient. | |
| req-dev-validation-canary-tier-3 | Authored, not retrofitted | Proposed | Canary designation is applied at test-authoring time and is part of the test-writing workflow, not a later audit. | |
| req-dev-validation-canary-tier-4 | Does not substitute for the gate | Proposed | The canary tier never replaces the real-backend cold-boot gate; both run. | The substitution-backend blind spot. |
| req-dev-validation-canary-tier-5 | Bounded, justified membership | Proposed | The canary set is enumerated with a per-entry downstream-failure justification and a fitness cap that forces eviction. | Same house pattern as the known-broken manifest. |

### Known-Broken Manifest
----
RID: `req-dev-validation-known-broken`
Status: `Implemented`

Known-broken state is enumerated in a committed manifest, never held in human memory. The gate exits non-zero on any failure **not** listed, and also on any listed entry that no longer fails (stale entries are removed so the manifest ratchets toward zero). Each entry carries a one-line reason and owning context. The manifest is seeded at landing with whatever is genuinely known-broken at that moment — possibly empty.

This requirement also **names, once, the house convention** the repository has independently reached for repeatedly: a *bounded, reviewed, in-repo manifest that ratchets down* is TAP's canonical mechanism for honest coverage accounting. Its instances are the log-site-ID baseline (`spec-tap-logging.md`), the authz-coverage baseline (`spec-tap-auth-v0.md` `req-tap-auth-policy-9`), the direct-write-coverage baseline (`tap/tests/_direct_write_baseline.txt`), the Gryphon executor branch-coverage floor (`tap_grid/gryphon/coverage-baseline.json`, `req-gridkin-executor-branch-coverage`), this known-broken manifest, canary-set membership ([Canary Test Tier](#canary-test-tier)), and honest `CI-unguarded` spec-status labeling (`spec-tap-cares-task-backend.md`). New honesty mechanisms SHOULD follow this pattern rather than invent a parallel one — and, per [Reusable Ratchet Harness](#reusable-ratchet-harness), should increasingly share its *implementation*, not just its shape.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-validation-known-broken-1 | In-repo, not in memory | Implemented | Known-broken is a committed manifest; the gate never depends on a human remembering an exclusion. | `tap_boot/tap_boot.cold_boot_gate_known_broken.json`. |
| req-dev-validation-known-broken-2 | Ratchets down | Implemented | A failure not in the manifest fails the gate; a manifest entry that no longer fails also fails the gate until removed. | Both directions verified live (tolerate path GREEN; stale entry → RED). |
| req-dev-validation-known-broken-3 | Per-entry justification | Implemented | Each entry has a one-line reason and owning context. | Missing `step`/`reason` fails the gate. |
| req-dev-validation-known-broken-4 | Seeded at landing | Implemented | The manifest is seeded with whatever is known-broken when the gate lands; an empty manifest (effective strict mode) is the preferred state. | Seeded **empty** — the gate lands green with no known-broken. |
| req-dev-validation-known-broken-5 | Named house convention | Implemented | The bounded-reviewed-ratcheting-manifest pattern is named here as canonical; other honesty mechanisms reference it rather than reinvent. | One vocabulary across sessions. |

### Collection Completeness
----
RID: `req-dev-validation-collection-complete`
Status: `Implemented`

Every test file that exists on disk MUST be collected by the default full-repo `pytest` run, except a small, justified set of intentional exclusions. This is the guard that **validates the validator**: without it, "green" silently means "the subset pytest happened to collect passed," and the subset can drift narrower than the code with no signal.

#### Status Details

This requirement exists because of a concrete miss. The 2026-07-01 login regression shipped green while `test_login_wall.py` was red, because `pyproject.toml` `testpaths` was an **allow-list** (`["tap", "tap_grid", …]`) that omitted whole apps — `tap_auth`, `tap_boot`, `tap_cares` — so their tests were never collected by the gate. No ordinary test can catch this: the failure is in the collection scope, one layer beneath the tests.

#### Implementation

- **Discovery, not an allow-list.** `pyproject.toml` sets no `testpaths`; pytest discovers every `test_*.py`/`*_test.py` from the repo root, minus `norecursedirs` (`.venv`, `node_modules`, `build`, `dist`, dot-dirs) and the explicit `--ignore`s in `addopts`. Discovery is fail-safe (a new test dir is collected automatically); an allow-list is fail-open (a new app is uncollected until someone remembers it). The reversibility argument of `spec-security-posture.md` applies: coverage config should fail toward over-collection, never under.
- **Outcome-based guard.** `tap/tests/test_collection_completeness.py` enumerates the on-disk test files and diffs them against the set a full `pytest --collect-only .` run collects (real `addopts`, marker filter overridden to a tautology so opt-in `-m` tests are not false orphans). Any file on disk but not collected fails the guard, naming the orphan. Being outcome-based, it catches every cause — a re-introduced `testpaths`, a stray `--ignore`, an import error that drops a module — not just the original mechanism.
- **Single visible ledger of holes.** The guard's `_IGNORED_DIRS` is the one place deliberate coverage exclusions live; each entry is justified and MUST correspond to an `--ignore=` in `addopts`. A real `--ignore` not mirrored there surfaces as an orphan, forcing the exclusion to be recorded rather than hidden.

#### Development

This is the honest-coverage-accounting discipline of this spec turned on the test suite itself: the Map's `CI-guarded` rows each *assume* their test is collected, and nothing verified that assumption until now. The guard is cheap (one `--collect-only` subprocess, no test execution) and structural, so the class cannot silently recur.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-validation-collection-complete-1 | Discovery, not allow-list | Implemented | `pyproject.toml` sets no `testpaths`; test collection is repo-root discovery minus an explicit ignore-list. | Fail-safe over the scattered per-app layout. |
| req-dev-validation-collection-complete-2 | Every file collected | Implemented | A guard asserts every on-disk `test_*.py`/`*_test.py`, minus justified `_IGNORED_DIRS`, is collected by a full-repo run. | `tap/tests/test_collection_completeness.py`. |
| req-dev-validation-collection-complete-3 | Justified holes only | Implemented | Each intentional exclusion is a justified `_IGNORED_DIRS` entry mirrored by an `addopts` `--ignore`; an unmirrored ignore fails the guard. | The single visible ledger of coverage holes. |
| req-dev-validation-collection-complete-4 | Install-aware for plugins | Implemented | Plugin tests live inside the package (`tap_plugin/<slug>/tests/`); the walk collects *installed* plugins' tests, and the guard subtracts *uninstalled* plugins' test files (via `tap.plugin_testing`) as a legitimate, delegated hole. Fully strict in the all-plugins lane (nothing uninstalled); relaxed per focused stack, with that coverage owned by [`req-dev-validation-all-plugins-lane`](#all-plugins-ci-lane). | Not a silent narrowing: the delegation is to a named, gated lane. Distinct from `_IGNORED_DIRS` (permanent, hand-listed holes) — this hole is dynamic per stack. |

### Reusable Ratchet Harness
----
RID: `req-dev-validation-ratchet-harness`
Status: `Implemented`

> **BUILT (2026-07-02, session/validation-creation).** Extracted on demand once the
> shape had its third-plus caller (per the discipline below). `tap/ratchet.py` holds
> the Django-free compare core (`ratchet_ceiling` / `ratchet_floor` /
> `read_baseline_set`); `tap.guards` adds the `Guard` / `CeilingRatchet` base and the
> filesystem-discovered, distributed guard set. Every bespoke ratchet migrated onto it
> (authz, direct-write, log-site ×3, gryphon coverage-floor, mypy, known-broken). The
> one deferred sub-req is the provenance-carrying baseline schema (`-2`), YAGNI until a
> consumer needs it. The section below records the original demand signal + design.

#### Why now (the demand signal)

The ratcheting-baseline pattern is no longer one mechanism — it is at least four, and
two of them (the direct-write-coverage baseline and the Gryphon executor
branch-coverage floor) landed *on the same day, in independent sessions, blind to
each other*, each hand-rolling its own "measure → compare to a committed number/set →
fail on regression → tell the human to bump on improvement" loop. Independent
convergence on one shape is the signal that the shape wants a shared core. The cost
of not extracting it is N slightly-different failure messages, N slightly-different
ratchet-direction bugs, and N places the dev-validation gate must special-case when
it comes to invoke them.

#### What generalizes vs. what stays bespoke

The **measurement** is irreducibly per-surface and MUST stay bespoke — a static AST
scan (log-site, authz), a runtime `coverage.py` run (Gryphon branch, direct-write), a
full smoke cycle. Do not try to unify measurement; that way lies a framework nobody
can read.

What generalizes is everything *after* the current value is in hand:

- **Baseline artifact schema.** A common committed shape: the ratchet value
  (scalar / count / set / manifest), plus provenance (`measured_at_commit`, what was
  measured over, a human `note`). Today each invents its own file format
  (`.json`, `.txt`, inline constant).
- **Compare + ratchet-direction.** One helper each for the two directions —
  *floor* (must not decrease; coverage %) and *ceiling→zero* (must not increase;
  uncovered-count / known-broken). Both share: fail on regression with a uniform,
  actionable message; on an *un-locked improvement*, fail-or-warn telling the human to
  bump the baseline so gains are captured (the single most-repeated hand-rolled bit).
- **Honest-status reporting.** Every ratchet already owes a Validation Map row with a
  guard-status label; the harness can emit the row stub and the standard
  `Manual (CI-unguarded by design)` vs `CI-guarded` phrasing so labeling can't drift.
- **Sub-point tolerance + integer flooring** for float metrics (the Gryphon ratchet's
  `int(current) < floor` rule) so wobble is not a false regression.

Sketch: a small `tap/ratchet.py` exposing `ratchet_floor(current, baseline_path, ...)`
and `ratchet_ceiling(current, baseline_path, ...)` over a shared baseline schema, with
uniform exit codes and messages. The existing callers (Gryphon
`scripts/gryphon-coverage-ratchet`, the authz/direct-write/log-site guards) migrate to
it incrementally; none is rewritten speculatively.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-validation-ratchet-harness-1 | Shared compare core | Implemented | A single helper implements the floor and ceiling-to-zero ratchet directions, with one actionable regression message and one improvement/bump message, replacing per-caller copies. | `tap/ratchet.py` (`ratchet_ceiling` / `ratchet_floor` / `read_baseline_set`); `tap.guards.CeilingRatchet` wraps the ceiling direction. Measurement stays bespoke per surface. |
| req-dev-validation-ratchet-harness-2 | Common baseline schema | Deferred | Ratchet baselines share a committed artifact shape carrying the value plus provenance (`measured_at_commit`, scope, note). | Deferred as YAGNI: baselines remain line-per-entry text (each with a header comment); no consumer needs structured provenance yet. Revisit if a caller does. |
| req-dev-validation-ratchet-harness-3 | Emits its Map row | Implemented | The harness produces the surface's Validation Map row with standard guard-status phrasing so honest-status labeling cannot drift. | Realized more strongly than a stub: guards carry `map_row`/`rid`/`cadence`/`status`, and `render_map_markdown()` generates the row (`req-dev-validation-map-5`). |
| req-dev-validation-ratchet-harness-4 | Incremental migration, no speculative rewrite | Implemented | Existing ratchets migrate to the shared core only as they are next touched; the harness is built when it would have its second or third real caller, not before. | Migrated: authz, direct-write, log-site (×3), gryphon coverage-floor, mypy, known-broken. Guards against framework-ahead-of-demand. |

### Static Typing Ratchet
----
RID: `req-dev-validation-mypy-ratchet`
Status: `Implemented`

`pyproject.toml` sets mypy `strict=true`, but for a long time nothing *gated* on it, so the error set drifted to ~1200. Auditing that debt found it is overwhelmingly noise, not latent bugs — django-stubs dynamic-ORM friction (`attr-defined`, `type-arg`) plus a `no-untyped-call` cascade off untyped test fixtures — so a clean-to-zero sweep would be a ~1200-line, near-zero-value diff. The value is **forward**: freeze the audited debt and block anything *new*. `mypy .` is ratcheted through the shared [Reusable Ratchet Harness](#reusable-ratchet-harness) core (`CeilingRatchet`), keyed per `path:error-code:count` (never line numbers, so an edit that shifts lines does not churn the baseline); a new error bumps a count, which fails both teeth (new key present, and the ratchet notices the recorded key is stale). A genuinely-new `union-attr`/`None`-access on new code therefore fails at authoring time, while the baselined debt ratchets down as files are cleaned. The same change also fixed the package-mode namespace-plugin resolution (`[tool.mypy] exclude` + `py.typed` markers) that made `mypy .` double-walk and abort with "Source file found twice".

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-validation-mypy-ratchet-1 | Strict mypy is gated | Implemented | A per-commit guard runs `mypy .` and fails on any error outside the committed baseline. | `tap/guards/mypy.py::MypyRatchet` via `tap/tests/test_guards.py`. |
| req-dev-validation-mypy-ratchet-2 | Line-drift-proof key | Implemented | The baseline keys each entry by `path:error-code:count`, not line number, so unrelated edits do not churn it; a new error of the same code bumps the count and fails. | Known blind spot: fix+regress of the same code in the same file leaves the count unchanged (acceptable — the surface is noise). |
| req-dev-validation-mypy-ratchet-3 | Debt is audited and honest | Implemented | The baselined errors are recorded as audited debt (django-stubs friction + test fixture cascade), and the ratchet only moves down; a reviewed typing change re-baselines via one command. | `manage.py guards --sync-mypy`. |

### Suite Tiering & Performance
----
RID: `req-dev-validation-suite-tiers`
Status: `Partially Implemented`

> **Forward note, not a build (jotted 2026-07-01).** Seeded for the
> validation-focused session. The corpus has grown fast (the Gryphon suites alone
> now run 7–18 minutes), and a full run has crept onto the inner loop. This is the
> tiering + acceleration strategy to pull it back off. `req-dev-validation-canary-tier`
> already owns the *membership discipline* of the fast tier; this requirement owns
> the *tiering model and the performance levers* around it.

#### The model: fast / affected / full

Three lanes, and the load-bearing insight is that the fix is usually *when each
lane runs*, not making the full run fast. A 15-minute full suite is fine if it runs
at the promote gate and not on every save.

- **Fast (smoke) — seconds, every save / pre-commit.** A curated blast-radius
  subset, governed by `-m smoke` and the membership rules in
  [Canary Test Tier](#canary-test-tier) (a test earns `smoke` only if its failure
  predicts broad downstream failure — importance alone is insufficient).
- **Affected — ~a minute, per chunk.** The tests touching what changed, selected by
  marker (`-m "not slow"`) or by test-impact analysis (below).
- **Full — the slow run, at the pre-push gate / CI only.** Everything, including the
  DB-heavy integration suites. Slow is acceptable here *by design*; this lane is the
  binary gate, not the inner loop.

#### As built — relevance-gated corpus (2026-07-08)

The first increment of the affected lane is deliberately narrow: it targets the one
surface that actually dominates the clock — the Gryphon corpus
(`plugins/gryphon_playground`, 7–18 min). Rather than per-test impact analysis
(`testmon`, deferred), `scripts/test` makes a single coarse decision: **run the corpus
only when the diff since `origin/main` touches the executor's footprint**, otherwise
skip it with a loud, logged notice. This lets `gryphon_playground` stay in the tree
(keeping the corpus available to other sessions and as Player-3 food-for-thought)
without taxing every unrelated local edit.

- **Footprint** (conservative — errs toward *running*, because the executor compiles
  onto shared grid machinery, so a false *skip* would be a silent-wrong-result
  false-green, precisely what the corpus exists to catch): `tap_grid/`,
  `plugins/gryphon_playground/`, `plugins/grid_fixtures/`, `tap_api/routers/gryphon.py`.
  The `tap_grid/` prefix is intentionally coarse (the whole grid read/materialization/
  edge layer, not just `tap_grid/gryphon/`); narrowing it to the executor's true
  transitive-import set — *derived*, not hand-authored, to avoid drift — is a later
  optimization. The wins land on the common cases that touch none of these: `tap_web`,
  `tap_viz`, `tap_auth`, docs/specs, and non-fixture plugin work.
- `--fast` remains the unconditional force-skip; `--gryphon` is the new unconditional
  force-run. An undeterminable merge-base (detached/shallow clone) or a
  non-interactive invocation defaults to **running** the corpus (fail toward
  correctness).
- **Gate safety** (`req-dev-validation-suite-tiers-4`): auto-selection is a
  *local-interactive accelerator only*. The promote gate invokes `scripts/test
  --gryphon` (explicit force-full) and the all-plugins CI lane runs `pytest -n 4`
  directly (never through `scripts/test`), so neither can inherit a relevance-skip.
  The corpus stays an un-sampled gate.

#### Acceleration levers, ranked by ROI for this DB-bound suite

1. **Parallelize first — `pytest-xdist -n auto`.** The single biggest win for a
   DB-heavy Django suite, and low-effort. `pytest-django` gives each xdist worker its
   *own* test database, so it does **not** violate the standing "run overlapping
   suites as one invocation or they deadlock the test DB" rule — that rule is about
   two separate pytest *processes* sharing *one* DB; xdist is one process, N workers,
   N separate DBs. Expect roughly `cores`× on the full run.
2. **Profile before cutting — `pytest --durations=25`.** Time is rarely spread evenly;
   it concentrates in a handful of DB-seeding integration tests. Mark the offenders
   `slow` and add them to `smoke` only if they meet the blast-radius bar.
3. **Attack the per-test DB cost — the real hot spot.** `@pytest.mark.django_db(transaction=True)`
   is expensive (it truncates tables between tests rather than rolling back a
   transaction); it is genuinely required where `on_commit`/service-layer hooks fire
   (e.g. the Gridkin GRIFT seed) but should not be the default elsewhere. `--reuse-db`
   skips migrate/create-DB between local runs. A *separate* shared-seed "fast Gridkin"
   lane (seed a fixture once, run its read-only scenarios against it) would collapse
   much of the per-scenario cost — a speed lane only, since it trades away the
   per-scenario isolation `req-gridkin-runner-contract-2` requires of the canonical
   suite.
4. **Test-impact analysis for the affected lane — `pytest-testmon`.** Runs only tests
   whose covered code changed (same lineage as the branch-coverage data the ratchets
   now collect). A local accelerator for deciding *what to run fast*, never a
   substitute for the full gate — its tracking DB can go stale on config/env changes.

#### Anti-patterns to avoid

- The fast tier drifting into "the important tests" instead of the blast-radius set
  (the canary-tier bar exists precisely to prevent this).
- Optimizing before `--durations` says where the time is.
- Trusting an affected/impact lane as a gate — it accelerates the inner loop; the
  full lane is what refuses the push.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-validation-suite-tiers-1 | Three named lanes | Partially Implemented | The suite exposes fast (`-m smoke`), affected (`-m "not slow"` or impact-selected), and full lanes, with a documented "which runs when". | Built: full + `--fast` lanes (`scripts/test`, documented in `docs/misc/test-parallelization-xdist-notes.md`), plus the relevance-gated Gryphon-corpus selection (`suite-tiers-5`) as the first affected-lane increment. Missing: general per-test impact selection + the `-m smoke` fast tier (membership owned by `req-dev-validation-canary-tier`). |
| req-dev-validation-suite-tiers-2 | Parallel full run | Implemented | The full lane runs under `pytest-xdist` with per-worker databases; this does not conflict with the shared-DB single-invocation rule. | `scripts/test` (`-n auto`), kept out of `addopts` on purpose. Highest-ROI lever; delivered. |
| req-dev-validation-suite-tiers-3 | Profiled, not guessed | Proposed | `slow` designations follow from `--durations` evidence, not intuition. | |
| req-dev-validation-suite-tiers-4 | Impact lane is not a gate | Implemented | Any test-impact/affected selection accelerates the inner loop only; the pre-push gate always runs the full lane. | Counters the substitution-backend blind spot. Enforced for the corpus-relevance lane (`suite-tiers-5`): the promote gate calls `scripts/test --gryphon` (force-full), the all-plugins CI lane runs `pytest -n 4` directly (never via `scripts/test`), and a non-interactive `scripts/test` also force-runs — so no gate path can inherit a relevance-skip. |
| req-dev-validation-suite-tiers-5 | Relevance-gated corpus | Implemented | The default local lane runs the Gryphon corpus only when the diff since `origin/main` (merge-base through working tree, incl. untracked) touches the executor footprint; `--fast` force-skips, `--gryphon` force-runs; an undeterminable base or a non-interactive run defaults to running it. | Coarse path-based first increment of the affected lane, scoped to the one dominant-cost corpus. Footprint (conservative, errs toward running): `tap_grid/`, `plugins/gryphon_playground/`, `plugins/grid_fixtures/`, `tap_api/routers/gryphon.py`. Local-interactive accelerator only — never weakens the gate (`suite-tiers-4`). `scripts/test`. |

### Lean-Boot Independence Gate
----
RID: `req-dev-validation-lean-boot`
Status: `Implemented`

The cold-boot gate ([Cold-Boot Smoke Gate](#cold-boot-smoke-gate)) runs inside the **already-running stack's venv** — a per-compose-project named volume (`venv:/app/.venv`) that holds whatever the container's boot profile installed (the full `test_all` union under the promote gate). That venv-sharing is a **structural blind spot** for one failure class: a **core** (`tap_*`) module that imports a **plugin-only** dependency (e.g. `requests`, `jwt`, `boto3`). In a full venv the leaked package is already importable, so the import silently succeeds and the leak stays invisible — yet a real **lean deployment** (the `core` product baseline, a customer with a minimal plugin set, or a plugin evicted to its own repo) would fail to boot with `ModuleNotFoundError`. Booting `core` *in-process* inside the full-venv gate has **zero teeth** here; only a genuinely separate, lean-**installed** environment catches it.

**As built.** `scripts/gate-lean` stands up a **throwaway session in its own compose project** (`tap_leanboot`) — which gives it its **own `venv` named volume**, i.e. a **core-only virtualenv** — via the real spawn-off-`main` path (`scripts/spawn-session.sh --boot core`, worktree written under `WORKTREE_BASE` in system tmp, non-interactive). It boots the zero-plugin `core` profile and gates on `manage.py health`. Because the venv is core-only, any core module that reaches for a plugin-only dependency fails at pre-boot / migrate / boot — exactly the class the in-container gate cannot see. On **any** exit the throwaway is nuked (containers, volumes, networks, worktree, branch, registry row) via `despawn-session.sh --yes` (a commitless throwaway is always CLEAN); on **failure** diagnostics (`compose ps` + web logs) are captured to a sibling `*-diag.log` **before** teardown so a red gate is debuggable — deeper post-mortem via the `/diagnose-failed-session-spawn` skill. Proven both directions on build: `core` boots healthy in isolation (GREEN, ~clean teardown, zero residue), and an injected core `import boto3` is caught RED with the `ModuleNotFoundError` captured to the diag log.

This is the second half of `req-boot-minimal-baseline-5` (spec-tap-boot-v0.md): the baseline flip made `core` the product baseline and the union a test-only tier; this gate is what keeps `core` **honestly** bootable in isolation as the code evolves.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-validation-lean-boot-1 | Isolated lean venv | Implemented | The gate boots in a separate compose project so the venv is a fresh, core-only install — not the running stack's full venv. | `scripts/gate-lean` → `tap_leanboot` project → own `venv` volume. The venv-sharing blind spot is the whole reason it exists. |
| req-dev-validation-lean-boot-2 | Real spawn standup path | Implemented | The gate exercises the actual `spawn-session.sh` standup (build → pre-boot → migrate → boot → health), not a bespoke reimplementation. | Faithful to the path a real spawn / customer standup takes; also transitively smoke-tests `spawn-session.sh`. Branches the throwaway from the invoking worktree's **HEAD** (`TAP_SPAWN_BASE_REF`), so under a promote it tests the just-merged tree — the exact tree about to become `origin/main`, which local `main` does not yet point at. |
| req-dev-validation-lean-boot-3 | Catches import leakage | Implemented | A core module importing a plugin-only dependency fails the gate. | Verified: an injected `import boto3` in a core module → RED with `ModuleNotFoundError: No module named 'boto3'` captured. |
| req-dev-validation-lean-boot-4 | Bulletproof teardown | Implemented | On any exit (success, failure, interrupt) the throwaway is fully nuked; no containers/volumes/worktree/branch/registry residue. | Trap → `despawn-session.sh --yes` with an inline `compose down -v` + `worktree remove` fallback. Throwaway lives in system tmp, never `~/tap-sessions`. |
| req-dev-validation-lean-boot-5 | Diagnose before nuke | Implemented | On failure, diagnostics are captured to a durable log before teardown so a red gate is debuggable. | Sibling `*-diag.log` (survives the worktree nuke); `/diagnose-failed-session-spawn` skill for the post-mortem. |

#### Future

- **Fast-fail on crash-loop — resolved 2026-07-03** (`req-boot-abort-signal`, spec-tap-boot-v0.md). A leak no longer waits out the 300s readiness timeout: the standup pipeline emits the `ABORT` signal (`req-tap-logging-abort-signal`) on fatal failure, and `spawn-session.sh` Step 5 tails for the rendered `TAP-ABORT:` line and checks the container-exited/restarting state — so a leak reds in seconds with its reason. `gate-lean` inherits it.
- **Profile matrix.** Today the gate boots `core` (strictest signal). A follow-on could sweep `core` + `core_dev` (and, once plugins are evicted, a representative lean customer profile) if a leak class emerges that only a non-empty lean set exposes.

### Promote-Path Enforcement
----
RID: `req-dev-validation-promote-hook`
Status: `Implemented`

The promote path MUST run the gate before advancing `origin/main` and refuse to push on red. This covers `scripts/promote-to-main.sh`, `scripts/promote-all-sessions.sh` (via the per-session script), and the documented manual fallback sequence. **As built the promote path composes three validation surfaces** (Step 2.5): the **full pytest lane** (`scripts/test --gryphon` — `--gryphon` forces the Gryphon corpus on unconditionally so the gate never inherits the local relevance-skip of `req-dev-validation-suite-tiers-5`) — which catches unit/functional regressions the cold-boot cycle structurally cannot (e.g. a stale collector key red'ing a unit test — the exact class that shipped to `main` red *because no promote gate existed yet*: the 2026-07-02 collector-identity refactor left the module-path key in `test_orchestrator.py`'s `_KSI_COLLECTOR` fixture, and the ungated promote published it) — then the **cold-boot gate** (`scripts/gate`), then the **lean-boot independence gate** (`scripts/gate-lean`, [above](#lean-boot-independence-gate)) which catches the core→plugin-dep import-leakage class the full-venv cold-boot gate structurally cannot. All three must be green; any red aborts before the atomic push. This is the reciprocal of `req-dev-multisession-promote-gate` in [spec-dev-multisession.md](spec-dev-multisession.md): that spec owns the requirement *on the promote workflow*; this requirement owns the gate *contract it invokes*. The two cross-reference and MUST stay consistent.

The gate runs after the pre-push merge (so it validates the exact tree that will become `origin/main`) and before the atomic dual-refspec push. On red, the push does not happen and the failure is reported; `origin/main` is never advanced past a tree that failed the gate. This is the mechanical enforcement of the otherwise prose-only "no messy/broken state to main" discipline that protects every spawned session.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-validation-promote-hook-1 | Gate before push | Implemented | The promote path runs the gate after the pre-push merge and before the atomic push. | `scripts/promote-to-main.sh` Step 2.5 (after merge, before atomic push): full lane (`scripts/test --gryphon`, force-full) → cold-boot gate → lean-boot gate. Validates the exact tree that becomes `origin/main`. |
| req-dev-validation-promote-hook-2 | Red blocks the push | Implemented | A failing gate aborts the promote; `origin/main` is not advanced. | `scripts/gate` non-zero → `fail` before Step 3. |
| req-dev-validation-promote-hook-3 | Covers script and fallback | Implemented | Enforcement applies to `promote-to-main.sh`, the all-sessions orchestrator, and the documented manual sequence. | `promote-all-sessions.sh` calls `promote-to-main.sh` per session (transitive). |
| req-dev-validation-promote-hook-4 | Reciprocal consistency | Implemented | This requirement and `req-dev-multisession-promote-gate` cross-reference and stay consistent; neither restates the other's substance. | |

### All-Plugins CI Lane
----
RID: `req-dev-validation-all-plugins-lane`
Status: `Proposed`

**The trigger fired early, via a path not originally listed.** [Server-side CI](#out-of-scope-v0) was deferred (v0) until "a second contributor" made "did you run it locally?" un-answerable by trust. Plugin **eviction** fired an equivalent trigger first: once a plugin's source leaves the monorepo, a focused local stack *structurally cannot* run that plugin's tests, so "the local gate is green" stops meaning "all plugins are green." The response is a **local/CI split**: the local promote gate validates *what is installed in this stack*; a **server-side all-plugins lane** owns *all-plugins truth*. It stands up the existing compose image and boots the `test_all` union (per the Out-Of-Scope constraint — it does not reimplement the environment).

**The boot record is the known-good-set (BOM) the lane verifies.** A boot record's `install.plugins[]` already pins each plugin's source+rev with an integrity digest ([spec-tap-boot-bootstrap.md](spec-tap-boot-bootstrap.md)); that *is* a bill-of-materials in the sense Jenkins (`bom-<line>.x`), Backstage (`versions` manifest), and Airflow (`constraints-*`) use one — a pinned set verified to work *together*. Adopting a new plugin version is therefore: bump its rev in the record → the all-plugins lane re-verifies the whole set → promote. That is the `can-i-deploy` gate semantics (Pact) implemented over TAP's own BOM: never trust "latest × latest," only "this set, tested together." The lane's **hard gate on promote is legitimate here** — TAP's plugin set is small and first-party/curated, so it is the Airflow "in-repo providers hard-gate" case, not the Jenkins PCT "soft gate over a third-party universe" case.

**Prior-art placement.** TAP is in the Airflow/Ansible bucket (plugins extracted to their own repos, in-process Python packages, independent release); the convergent answer there is a min-core floor + a plugin-CI matrix against real core (incl. HEAD) + a pinned known-good-set — *not* a Terraform-style wire protocol (overkill in-process) nor Pact contracts (HTTP bodies can't see Python signature/type/exception breakage). See the plugin-testing prior-art sweep.

**Runner choice — shard the free lane, don't buy hardware.** A measured green run spends **~95% of wall-clock in the pytest lane** (1292s of ~21.5 min; build+boot is a ~100s fixed tax, and the image-layer cache — `cache-from/to type=gha`, landed `f051ba9e` — is a real hit, ~40s vs minutes cold). That single number decides the runner question: the lane is near-perfectly shardable, and it is Postgres-I/O-bound, so *N independent Postgres instances* (one per shard) relieves the bottleneck better than *more cores on one box* (where one Postgres shares them). The winning lever is therefore **matrix-sharding across free 2-core runners** (`-lane-7`), not GitHub org-only larger runners (8-core = $0.022/min, no included minutes, forces an org migration + the promote→PR-gate redesign) and not AWS self-hosted (more cost + a standing ops surface, no faster than sharding for this workload). Baseline CI is ~free on the personal account (~$0–20/mo at the 2026 $0.006/min rate), so nothing here is a *cost* play — it is a wall-clock play at ~$5/mo. The full evaluation, including where AWS *does* earn its keep (AWS-native Bedrock / `aws_core` testing — a capability axis, not a speed axis; see the Out-Of-Scope AWS-native runner entry), is [doc-dev-validation-ci-runner-strategy.md](../docs/misc/doc-dev-validation-ci-runner-strategy.md).

| Sub-RID | Name | Status | Acceptance | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-validation-all-plugins-lane-1 | Local/CI split | Proposed | The local gate validates only installed plugins (install-aware collection, `req-dev-validation-collection-complete`); the all-plugins lane is the sole authority that every shipped plugin's tests pass. | Closes the focused-session gap that was previously bypassed. |
| req-dev-validation-all-plugins-lane-2 | Boots the union in the real image | Proposed | The lane boots the `test_all` union (v2: from git-installed, test-carrying wheels) in the compose image and runs the full pytest lane; it does not reimplement the environment. | v1 drafted at `.github/workflows/all-plugins.yml` (monorepo checkout). Not yet a proven pipeline — GitHub Actions is not exercisable from the dev loop. |
| req-dev-validation-all-plugins-lane-3 | Blocking on promote (BOM verify) | Proposed | `promote-to-main.sh` triggers the lane on the merged tree and refuses to advance `origin/main` on red (option B: trigger + poll, keeps the atomic push). Reciprocal of `req-dev-multisession-ci-gate`. | The `can-i-deploy`-over-the-boot-record gate. |
| req-dev-validation-all-plugins-lane-4 | Plugin-side CI vs. core | Proposed | Each evicted plugin repo's CI installs core + the plugin + its declared test dependencies and runs the plugin's tests, at minimum against **core-main** (drift early-warning); a min/latest-core matrix is a later addition. This is where a plugin change is validated *as it is pushed*. | Needs core to be git-consumable by the plugin CI (clone the monorepo @ref + boot). Publishing a `tap-core` package + tagging core releases (for a min/latest matrix) is deferred. |
| req-dev-validation-all-plugins-lane-5 | Plugin ships its own test/CI boot profile | Proposed | A plugin ships a minimum test boot record (`boot/*.boot.json` inside the package) that CI pulls and boots. It declares the plugin's cross-plugin **test** dependencies so CI pulls and tests them alongside — a self-contained mini-BOM scoped to "what this plugin needs to be tested." | Reuses the shippable-boot-record machinery; a concrete, exercised home for `req-plugin-arch-dependencies` "declare-now" deps. |
| req-dev-validation-all-plugins-lane-6 | Min-core floor (load-time) | Proposed | Plugins declare a supported core-version range and core refuses to load an out-of-range plugin at boot. | The cheapest foundational edge (P1; universal across ecosystems). Owned by [spec-plugin-architecture.md](../tap_plugins/specs/spec-plugin-architecture.md) `req-plugin-arch-min-core`; named here as the load-time complement to this lane. |
| req-dev-validation-all-plugins-lane-7 | Sharded execution (free-runner parallelism) | Parked | **PARKED 2026-07-08 — superseded by per-product-line CodeBuild lanes (`req-dev-validation-product-line-lanes`).** Built + exercised on CI (proved the machinery + aggregate gate + that even-split is non-viable — shards ran 51s/10min/25min-timeout, so `.test_durations` is mandatory — and surfaced the xdist test-DB flake fixed via the pre-migrated template, `TAP_TEST_DB_TEMPLATE`). Shelved as a documented free-runner fallback (commit `aa902128`) because per-product-line lanes parallelize along a *meaningful* axis (profile boundaries) and the AWS-native capability is wanted anyway. Original design retained below for reference. — The lane runs as a `matrix` of N shards (start N=3) across free 2-core runners: each shard does the cached build → boots its **own** `test_all` stack → runs a disjoint, duration-balanced slice of the suite (`pytest-split`, committed `.test_durations`; composes with per-shard xdist as `--splits N --group G -n 4`); the union of shards ≡ the single-lane test set. A single aggregate gate job (`needs:` all shards) is the one status the promote path polls, so `req-dev-validation-all-plugins-lane-3` / `req-dev-multisession-ci-gate` wiring changes minimally. The aggregate fails closed if any shard reds. | Wall-clock ~21.5min→~8–9min at N=3 (the test lane is ~95% of wall-clock, so the ~100s per-shard build+boot tax is cheap and each shard's own Postgres relieves the I/O bottleneck). **Balance by duration, not by logical boundary:** the dominant-cost gryphon corpus (`plugins/gryphon_playground`) is *subdivided across* shards, never pinned to its own shard — a dedicated shard would become the long pole (~14min) and gut the win. It subdivides cleanly because it is hundreds of small parametrized nodes (~99 gridkin scenarios + ~180+ fuzz cases + metamorphic + internals) with no monolithic long pole (the campaign/soak is `skipif`-gated off in the lane); fuzz node-ids are seed-stable so `.test_durations` stays valid (rolling the seed/counts → graceful even-split fallback, refresh durations). The CI lane keeps running the **full** corpus (no `--ignore`) — `scripts/test`'s executor-footprint relevance-gate stays a *local* inner-loop accelerator, never applied to this all-plugins-truth gate. Same single validation surface (not a new Map row — `req-dev-validation-map-3` is triggered by add/move/retire, not by internal parallelism; the declared-surface `description` gets the shard note at implementation via `--sync-map`). Composes with the layer cache already on `main` (every shard's `cache-from: type=gha` hits the same warm cache — no build-once-to-registry step). Decision record: [doc-dev-validation-ci-runner-strategy.md](../docs/misc/doc-dev-validation-ci-runner-strategy.md). |

### Per-Product-Line CI Lanes
----
RID: `req-dev-validation-product-line-lanes`
Status: `Proposed`

**The parallelization axis is the product, not the test suite.** TAP's products *are*
boot profiles: a product line = a plugin-pack + boot profile (`samsite`; a FedRAMP line
— now the evicted `fedramp_20x_ksi` repo; customer-specific lines). Rather than shard one
monolithic `test_all` run for speed (parked `req-dev-validation-all-plugins-lane-7`),
validate **each product line on its own lane** — booting *that line's profile*, running
*that line's tests* (install-aware collection, `req-dev-validation-collection-complete`,
scopes to core + the booted profile's plugins), in parallel across lines. This
parallelizes along a *meaningful* boundary (each lane validates a real deliverable),
scales with the business (new line = new lane), and sidesteps the monolithic-`test_all`
sharding flakiness because each lane is a deterministic, smaller profile. `test_all`
remains one lane (the union superset).

**Vehicle: AWS CodeBuild as a GitHub Actions runner.** One CodeBuild project per line
(webhook on `WORKFLOW_JOB_QUEUED`), EC2-mode + privileged so the compose stack runs
(docker-in-docker), and — the point — running **in our account** so each lane carries an
IAM role for native Bedrock / `aws_core` STS testing (no long-lived creds in GH secrets).
Not a hand-built EC2 fleet (multi-day + standing ops), not a managed SaaS runner (speed
but no in-account identity). Decision (2026-07-08): aws_core account, us-east-1, first
lanes `test_all` + `samsite`, provisioned with Terraform. Each lane clones a per-profile
pre-migrated template DB (`scripts/build-test-template` + `TAP_TEST_DB_TEMPLATE`) for
fast, race-free setup. Full evaluation incl. the non-EC2 lanes table:
[doc-dev-validation-ci-runner-strategy.md](../docs/misc/doc-dev-validation-ci-runner-strategy.md).

**Artifacts (authored, not yet applied — blocked on the AWS-side CodeConnections auth):**
`ci/terraform/codebuild-runners/` (Terraform: connection, per-line CodeBuild project +
webhook + IAM role) and `.github/workflows/product-lines.yml` (the per-line matrix lane).

| Sub-RID | Name | Status | Acceptance | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-validation-product-line-lanes-1 | One lane per product line | Implemented | Each product line (profile) has a lane that boots *that* profile and runs *that* line's tests; lines run in parallel. Adding a line = one Terraform `product_lines` entry + one workflow matrix entry. | Meaningful (product) axis. `test_all` is the union superset lane. `test_all` + `samsite` lanes proven green on CodeBuild (2026-07-08). |
| req-dev-validation-product-line-lanes-2 | CodeBuild GHA runner | Implemented | Each lane runs on an AWS CodeBuild project registered as a GitHub Actions runner (EC2-mode, `privileged_mode` for docker-in-docker). Managed service — no AMI/NAT/autoscaler. | `ci/terraform/codebuild-runners/main.tf`; applied to account 180731181784 / us-east-1 via the CodeConnections GitHub app. |
| req-dev-validation-product-line-lanes-3 | Per-profile template clone | Implemented | Each lane builds a per-profile pre-migrated template DB and workers clone it (`TAP_TEST_DB_TEMPLATE`), eliminating the per-worker migrate-from-zero race + speeding setup. | `scripts/build-test-template`; `tap/test_settings.py`. Tier-0 RAM-backed Postgres (`docker-compose.ci.yml`) gave a further ~3.9× on the test lane. |
| req-dev-validation-product-line-lanes-4 | In-account capability, least-privilege per line | Implemented | Each lane's IAM role is per-line (grants can diverge) and grants only what that line tests need — native Bedrock and/or scoped `aws_core` STS, plus a per-line `GetSecretValue` grant on the plugin-pull secret for lines that git-install private plugins (`needs_plugin_pull`). The AWS-native reason to run CI here. | `ci/terraform/codebuild-runners/iam.tf`, `secrets.tf`; reuse the External-ID discipline from `plugins/aws_core/.../handoff/cross-account-role.yaml`. |
| req-dev-validation-product-line-lanes-5 | IaC in-repo, state out | Implemented | The provisioning is Terraform tracked in-repo; state + real tfvars (ARNs/account ids) are gitignored, never committed. The plugin-pull secret is a shell only (no `secret_version`) so no secret material lands in tfstate. | `ci/terraform/codebuild-runners/.gitignore`, `terraform.tfvars.example`, `secrets.tf`. |
| req-dev-validation-product-line-lanes-6 | Promote-gate + Map row when live | Implemented | The `test_all` union lane is wired as the promote gate (`promote-to-main.sh` Step 2.6 dispatches `line=test_all`, option B, reciprocal of `req-dev-multisession-ci-gate`), superseding the free-runner `all-plugins.yml` — which is retained as the fallback via `TAP_PROMOTE_CI_WORKFLOW=all-plugins.yml`. Map row added via `DECLARED_SURFACES` ("Per-product-line CI lanes (CodeBuild)"). | The gate bootstrap-skips the one promote that first lands `product-lines.yml` on `origin/main`, by construction (same detection as the original all-plugins gate). |

## Out Of Scope (v0)

- **Out-of-process real-worker integration (tiers 2–3).** Owned by `spec-tap-cares-task-backend.md` `req-tap-cares-task-backend-backlog-2`. Trigger: the persistent customer-hosted instance, or the strategy doc sequencing it sooner.
- **Broad per-flow correctness suite.** The gate is cold-boot-one-cycle plus the canary tier, not exhaustive integration. Trigger: a capability going "cold" (built, no longer in the daily assessment loop) earns a targeted integration test for *that* flow first.
- **Server-side CI (e.g. GitHub Actions).** ~~The pre-push gate is local for the solo window.~~ **Trigger fired early (2026-07-07), via a path not listed here: plugin eviction.** Once a plugin's source leaves the monorepo, a focused local stack cannot run its tests, so the local gate stops meaning "all plugins green" — an equivalent loss-of-trust to the "second contributor" trigger. Promoted to [`req-dev-validation-all-plugins-lane`](#all-plugins-ci-lane) (Proposed). As required, it stands up the existing compose image rather than reimplementing the environment. The "second contributor" path remains the trigger for the *fuller* PR-gated model (option A); the eviction-driven lane is the minimal server-side surface (option B).
- **Per-product-line CodeBuild lanes** — no longer out of scope: promoted to the active requirement [`req-dev-validation-product-line-lanes`](#per-product-line-ci-lanes) (Implemented), superseding the parked free-runner sharding. Artifacts authored (`ci/terraform/codebuild-runners/`, `.github/workflows/product-lines.yml`); CodeConnections app authorized + Terraform applied (account 180731181784); `test_all` + `samsite` lanes proven green (2026-07-08); the `test_all` union lane is the promote gate. GitHub's postponed-not-cancelled 2026 $0.002/min self-hosted charge is the standing tail risk.
- **Stage- and prod-validation.** Sibling specs and new Map rows when those environments exist. Trigger: the persistent customer-hosted instance inflection.

## Future

The deferral triggers above are deliberately concrete, not "later":

1. **Persistent customer-hosted instance.** The named inflection point: the system runs where the developer is not watching it. At that point dog-fooding stops being the safety net and the deferred tiers' demand signal has objectively fired — Shape-2/3 worker integration, the *fuller* server-side CI (PR-gated, option A), and stage/prod-validation siblings become warranted. (A narrow slice of server-side CI — the [all-plugins lane](#all-plugins-ci-lane) — was pulled forward early by plugin eviction; see Out Of Scope.)
2. **A capability going "cold."** The earlier, sharper trigger: the moment a flow leaves the daily assessment loop it loses its only coverage (dog-fooding). That specific flow is the first to earn a targeted integration test, well before the broader inflection.

Tier sequencing across this spec and `spec-tap-cares-task-backend.md` `req-tap-cares-task-backend-backlog-2` is currently forward-referenced (by that backlog entry) to a strategy doc that does not yet exist. Until it does, this Future section plus the [Validation Map](#validation-map) are the interim sequencing home; creating the strategy doc and migrating sequencing into it is itself a deferred item, not part of v0 of this spec.

## Status Vocabulary

Standard TAP states: `Proposed`, `Approved for Development`, `In Development`, `Implemented`, `Verified`, `Refactoring`, `Deprecating`, `Deprecated`, `Backlog`.
