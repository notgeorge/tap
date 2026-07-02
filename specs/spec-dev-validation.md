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
| req-dev-validation-map | [Validation Map](#validation-map) | Proposed | The spine: authoritative inventory of every validation surface |
| req-dev-validation-smoke-gate | [Cold-Boot Smoke Gate](#cold-boot-smoke-gate) | Proposed | Ordered cold-boot-one-cycle, halt-on-failure |
| req-dev-validation-real-backend | [Real-Backend Fidelity](#real-backend-fidelity) | Proposed | Gate runs the real task backend, never `ImmediateBackend` |
| req-dev-validation-canary-tier | [Canary Test Tier](#canary-test-tier) | Proposed | `-m smoke` blast-radius subset; does not substitute for the gate |
| req-dev-validation-known-broken | [Known-Broken Manifest](#known-broken-manifest) | Proposed | In-repo, ratchets down; named here as the house convention |
| req-dev-validation-collection-complete | [Collection Completeness](#collection-completeness) | Implemented | Every test file on disk is collected by the gate run; discovery not an allow-list; validates the validator |
| req-dev-validation-promote-hook | [Promote-Path Enforcement](#promote-path-enforcement) | Proposed | Reciprocal of `req-dev-multisession-promote-gate` |
| req-dev-validation-ratchet-harness | [Reusable Ratchet Harness](#reusable-ratchet-harness) | Proposed | Extract the shared compare-and-report core of the proliferating baseline ratchets |
| req-dev-validation-suite-tiers | [Suite Tiering & Performance](#suite-tiering--performance) | Proposed | Fast / affected / full test lanes so a slow full run leaves the inner loop; how-each-runs discipline |

Leaf surfaces referenced by the Map are owned elsewhere: spawn-env smoke in [spec-dev-multisession-smoketest.md](spec-dev-multisession-smoketest.md), teardown in [spec-dev-multisession-teardown.md](spec-dev-multisession-teardown.md), the log-site scanner in [spec-tap-logging.md](spec-tap-logging.md), and the async-delivery tiers in [spec-tap-cares-task-backend.md](../tap_cares/specs/spec-tap-cares-task-backend.md) (`req-tap-cares-task-backend-backlog-2`). This spec does not re-specify them.

### Validation Map
----
RID: `req-dev-validation-map`
Status: `Proposed`

The Validation Map is the spine of this spec and the single authoritative inventory of every validation surface in TAP. A surface that is not in the Map is, by definition, unaccounted-for: adding any validation surface anywhere in the repository REQUIRES adding (or updating) its row here in the same change. The Map records, per surface, what it proves, its cadence, and its honest guard status using the vocabulary below — including surfaces that are deliberately manual or deferred, so the validation posture and every gap are visible in one place rather than implied behind green checkmarks.

#### Guard-status vocabulary

- **CI-guarded** — failure is caught automatically by a committed test/gate that runs without human initiative (e.g. `pytest`).
- **Gate-guarded** — caught automatically by the pre-push gate ([Cold-Boot Smoke Gate](#cold-boot-smoke-gate)) before `origin/main` advances.
- **Manual (CI-unguarded by design)** — verified only when a human runs a documented procedure; labeled as such deliberately, not by oversight.
- **Named, deferred** — a known gap with an owning spec/backlog entry and a deferral trigger; not yet guarded.

#### The Map

| Surface | Owning spec | Proves | Cadence | Guard status |
| --- | --- | --- | --- | --- |
| Spawn-env health | `spec-dev-multisession-smoketest.md` | New session stack is namespaced, reachable (direct + labeled URL), isolated from primary, migrated, seeded, admin-bootstrapped | Per-spawn | Manual (CI-unguarded by design) |
| Teardown correctness | `spec-dev-multisession-teardown.md` | Despawn removes the worktree/stack with no leaked containers, networks, or volumes | Per-despawn | Manual (CI-unguarded by design) |
| Log-site tokens | `spec-tap-logging.md` (`req-tap-logging-site-id-scanner`) | Bare 4-hex token format + within-file hex uniqueness + baseline ratchet across all committed log calls | Per-commit (`pytest`) | CI-guarded (`tap/tests/test_log_site_ids.py`) |
| `record_*` site tokens | `spec-tap-cares-collector.md` | Within-file uniqueness of collector result site tokens | Per-commit (`pytest`) | CI-guarded (`tap_cares/tests/test_results_site_uniqueness.py`) |
| Authz coverage | `spec-tap-auth-v0.md` (`req-tap-auth-policy-9`) | Every call to a privileged graph sink (`write_batch`/`grift_import`/Search+Gryphon executors/`_*_internal`) sits inside a `@requires_capability`/`authorized()` gate; baseline ratchets to zero | Per-commit (`pytest`) | CI-guarded (`tap/tests/test_authz_coverage.py`) |
| Secret leak guard | `spec-tap-cares-secrets.md` (`req-tap-cares-secrets-leak-guard`) | No `*.secret.json` file or envelope-shaped (`scope`+`key`+`kind`+`data`) secret enters the repo tree — push-protection beyond `.gitignore`, excluding the mount + vendored dirs | Per-commit (`pytest`) | CI-guarded (`tap/tests/test_secret_leak_scan.py`) |
| Async-delivery — tier 1 | `spec-tap-cares-task-backend.md` (`-transactional-integrity-1`) | `run_collection` `on_commit` deferral is positively, mutation-provenly guarded | Per-commit (`pytest`) | CI-guarded (`TestTransactionalIntegrity`) |
| Async-delivery — tiers 2–3 | `spec-tap-cares-task-backend.md` (`-backlog-2`) | Real-worker fork safety, queue isolation, wall-clock lifecycle, pickup latency, crash recovery | Deferred | Named, deferred |
| Assembled-instance health | `specs/spec-tap-health-v0.md` (the pair) | A stood-up instance's real backends actually work: DatabaseCache table provisioned (`tap_cache`), live db + cache set/get round-trip + best-effort queue + secrets probe + auth-providers offline self-test probe pass. Catches the latent-provisioning-fault class (standup "succeeds" but a never-exercised-at-boot path is broken) | Per-commit (`pytest`) + per-spawn (`manage.py health` exec gate) | Partially guarded — **CI-guarded** for the unit pieces (`tap_health/tests/test_checks.py` cache-table system check; `tap_health/tests/` registry/service/projection-leak/command tests) and the database-tagged check fires loud at `migrate`/`check --database`; **per-spawn** the `manage.py health` non-zero-exit gate (`spawn-session.sh` Step 6.5) replaces both the prior 5xx-passes liveness blindness and the now-parked unauthenticated `/healthz` (`req-tap-health-exposure-4`). The full cold-boot assembled-instance live-health run under automation is **Named, deferred** → folds into the Cold-boot system cycle gate (CI/CD is roadmap item 5, post-July) |
| Gryphon executor-stage coverage | `plugins/gryphon_playground/specs/spec-gridkin-v0.md` (`req-gridkin-stage-coverage`) | Every executor dispatch stage (`gryphon_stage()` label, derived from source) is exercised by a WHERE-carrying Gridkin scenario; snapshot stage labels don't drift from the source. Closes the intent≠path-coverage gap (silent-wrong-answer bug on an unexercised dispatch path) | Per-commit (`pytest`) | CI-guarded (`plugins/gryphon_playground/tests/test_gridkin_internals.py::TestStageCoverage`) |
| Gryphon executor branch coverage | `plugins/gryphon_playground/specs/spec-gridkin-v0.md` (`req-gridkin-executor-branch-coverage`) | `executor.py` branch coverage (measured across the unit + SQL-capture + Gridkin + API suites) holds at/above a committed floor — the branch-level complement to the stage gate, catching an unexercised branch *within* a stage | On-demand script (~10-15 min instrumented run); pre-push once the gate absorbs it | Partially guarded — the ratchet comparison is **Manual (CI-unguarded by design)** via `scripts/gryphon-coverage-ratchet` (too slow for per-commit); the committed floor's well-formedness is **CI-guarded** (`tap_grid/tests/test_gryphon_coverage_baseline.py`). Folds into the Cold-Boot gate when built. First instance of the ratcheting-baseline convention applied to runtime coverage. |
| Gryphon metamorphic TLP | `plugins/gryphon_playground/specs/spec-gridkin-v0.md` (`req-gridkin-metamorphic-tlp`) | Ternary-logic-partitioning of corpus scenarios: TRUE/FALSE/(UNKNOWN) partitions reconstruct the unfiltered scan, discriminating the 2VL null-literal vs 3VL null-field boundary — executor self-consistency on the highest-risk null surface, independent of the model oracle | Per-commit (`pytest`) | CI-guarded (`plugins/gryphon_playground/tests/test_gryphon_metamorphic.py`) |
| Gryphon differential property fuzzer | `plugins/gryphon_playground/specs/spec-gridkin-v0.md` (`req-gridkin-property-fuzz`) | Seedable random GRIFT graph + random valid query over the model oracle's modeled surface → executor vs oracle agree on identity/row sets; the capstone that lifts coverage past hand-authored scenarios. Surfaced four executor/oracle bugs on first runs (all fixed + regression-locked); replayable from the seed alone | Per-commit (`pytest`, committed 12×15; env-tunable soak) | CI-guarded (`plugins/gryphon_playground/tests/test_gryphon_fuzz.py`) |
| Cold-boot system cycle | this spec (`req-dev-validation-smoke-gate`) | Fresh DB → migrate → seed → one real collector cycle → one scheduler fire, end to end | Pre-push | Gate-guarded *(target)* |
| Canary tier | this spec (`req-dev-validation-canary-tier`) | Blast-radius unit/functional subset still passes | Pre-push + per-commit | Gate-guarded *(target)* |
| Web render smoke (login/landing) | `tap_web/specs/spec-web-navigation.md` (`req-web-nav-chrome-read-free-3`) | The always-present base.html chrome renders without a 500 for both an anonymous caller (`GET /auth/login/` → 200) and an authenticated `grid.read` holder (`GET /` → 200) — catches a shared context processor / chrome read tripping a structural backstop, whose blast radius is every page | Per-commit (`pytest -m smoke`) | CI-guarded (`tap_auth/tests/test_login_wall.py`, `@pytest.mark.smoke`) |
| Collection completeness | this spec (`req-dev-validation-collection-complete`) | Every `test_*.py`/`*_test.py` on disk (minus the justified `_IGNORED_DIRS`) is collected by a full-repo run — the check that validates the validator, so "green" cannot mean "the subset pytest happened to collect passed" | Per-commit (`pytest`) | CI-guarded (`tap/tests/test_collection_completeness.py`) |
| Read-only search write detection | `tap_grid/specs/spec-grid-search.md` (`req-grid-search-readonly.sec-6`) | A write reaching the read-only `search_readonly` connection (SQLSTATE 25006) emits a `security` Flaw (`search_readonly_write_blocked`) before the DB rejection propagates — turns the otherwise-silent read-only block into a response-triggering alert. Connection-layer wrapper, so it covers every search execution lane. Distinct from the ORM read/write backstops (this is the raw-executor-SQL path they structurally cannot see) | Per-commit (`pytest`) | CI-guarded (`tap_grid/tests/test_search_readonly_guard.py`) |
| Plugin dependency consistency | `tap_plugins/specs/spec-plugin-architecture.md` (`req-plugin-arch-dependencies-4`) | Cross-plugin CODE dependencies stay coherent: declared manifest `depends_on` ⊇ AST-observed `tap_plugin.<other>` imports (no undeclared coupling), every required dep is present + install-ordered before its dependent, and min-versions hold — fail closed at pre-boot. The import graph is also the supply-chain/blast-radius map. Captures code deps only (collector-produced DATA ordering stays profile-explicit by design). | Pre-boot (`python -m tap.preboot`) + per-commit (`pytest`) | CI-guarded — pure check `tap/tests/test_plugin_deps.py`, manifest parse `tap_plugins/tests/test_manifest_depends_on.py`; the live pre-boot gate (`tap/preboot.py:dependency_consistency_guard`) runs per-boot/per-spawn |
| Plugin report contract | `tap_plugins/specs/spec-plugin-architecture.md` (`req-plugin-arch-install-registry-3`) | `manage.py plugins --json` / `tap_plugins.report.build_report()` output validates against `plugin-report.schema.json` on every build (drift between the read-model and its published contract fails loud), and a healthy report shows zero undeclared cross-plugin imports | Per-commit (`pytest`) + on every report build | CI-guarded (`tap_plugins/tests/test_report.py`) |

Rows marked *(target)* describe the intended state once this spec is implemented; their guard status is honestly `Named, deferred` until then. The Map is updated in the same change as any new or retired validation surface, and reviewed when it changes — the change to the Map *is* the visible decision.

**Collection-scope caveat (a guard that isn't collected does not guard).** A test that the default `pytest` run does not collect is **invisible to the gate** — it passes when named explicitly and silently protects nothing otherwise. This let the 2026-07-01 login regression ship green: `tap_auth`, `tap_boot`, and `tap_cares` all sat outside the `testpaths` **allow-list**, so their tests (including `test_login_wall.py`'s render assertions) were never in the gate. The allow-list is fail-open over a scattered per-app layout — a new app is uncollected until someone remembers to list it. The fix is structural, not another list entry: `pyproject.toml` no longer sets `testpaths`, so pytest **discovers** every test file from the repo root (an ignore-list, fail-safe), and [Collection Completeness](#collection-completeness) asserts the outcome so the scope can never silently narrow again. See that requirement.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-validation-map-1 | Map is authoritative | Proposed | Every validation surface in the repository has exactly one row in the Map. A surface absent from the Map is treated as unaccounted-for. | |
| req-dev-validation-map-2 | Honest guard status | Proposed | Each row's guard status uses the defined vocabulary; manual/deferred surfaces are labeled explicitly, never implied. | Counters the false-confidence failure mode. |
| req-dev-validation-map-3 | Co-change discipline | Proposed | Adding, moving, or retiring a validation surface anywhere REQUIRES updating its Map row in the same change. | The Map change is the reviewable decision. |
| req-dev-validation-map-4 | References, not copies | Proposed | The Map points at owning specs; it does not duplicate their requirements or acceptance criteria. | Prevents cross-spec drift. |

### Cold-Boot Smoke Gate
----
RID: `req-dev-validation-smoke-gate`
Status: `Proposed`

The gate is an ordered, deterministic, halt-on-failure check that a freshly-built environment can boot from zero and complete one real end-to-end cycle. It adopts the established shape of [spec-dev-multisession-smoketest.md](spec-dev-multisession-smoketest.md): an ordered set of checks with expected outcomes, run top-to-bottom, where any failure halts and is reported. It runs **inside the existing compose image** — never a reimplemented environment — because the container's Python build differs from a stock host interpreter and an environment that does not reproduce the image will diverge.

The cycle, in order:

1. Fresh database (no pre-existing state).
2. `migrate` applies cleanly from zero.
3. `import_plugin_grift --all` seeds plugin data (strict; a failed bundle fails the gate).
4. One real collector runs to a terminal `CollectionJob` state through the real task backend ([Real-Backend Fidelity](#real-backend-fidelity)).
5. One scheduler fire is evaluated.
6. Resulting grid state is asserted (the collector's expected nodes/edges/batch landed).

It is explicitly **not** broad correctness coverage — that is the canary tier and the deferred per-flow suites. It is one ordered run on a fresh database with no per-test isolation; this is intentional and matches the per-session isolated-Postgres model rather than fighting transactional-rollback semantics. Wall-clock budget: **correctness and real-backend fidelity over speed**. A 10+ minute promote that the developer steps away from is explicitly acceptable (the human is offline during it by design); the gate is not optimized for latency at the cost of fidelity. The cold-boot cycle is fixed; the canary tier is the tunable lever if total time must be bounded. The measured wall-clock is recorded here once Phase 1 (the backlogged gate build) lands.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-validation-smoke-gate-1 | Cold boot from zero | Proposed | The gate starts from a fresh database; `migrate` applies with no pre-existing schema/data. | |
| req-dev-validation-smoke-gate-2 | Seed is strict | Proposed | `import_plugin_grift --all` runs strict; any failed bundle fails the gate. | Aligns with `req-dev-multisession-spawn-import-strict-1`. |
| req-dev-validation-smoke-gate-3 | One real cycle | Proposed | A collector reaches a terminal `CollectionJob` state and a scheduler fire is evaluated within one ordered run. | |
| req-dev-validation-smoke-gate-4 | Grid state asserted | Proposed | The cycle's expected grid mutation is positively asserted, not inferred from absence of error. | Counters the false-confidence failure mode. **Drift resolved (2026-06-11):** the Phase-0 finding (grid-mutation signal was `CollectionJob.grift_batches.imported`, zero `PRODUCED_BATCH` edges, contradicting `spec-tap-cares-task-backend.md`) is closed — `req-grid-edge-produced-batch` is built, the CARES runtime now creates `PRODUCED_BATCH` edges at terminal state, and the `grift_batches` field is removed. The spike asserts grid mutation via `PRODUCED_BATCH` edges (disposition `imported`). A documented idempotent no-op (e.g. `DIFF_EMPTY`) is a valid SUCCESSFUL outcome, not a gate failure. |
| req-dev-validation-smoke-gate-5 | Runs in the compose image | Proposed | The gate executes inside the existing compose stack image, not a reconstructed environment. | The container Python build is non-stock. |
| req-dev-validation-smoke-gate-6 | Halt and report | Proposed | The first failing check halts the run and reports the failing step; the gate exits non-zero. | |

### Real-Backend Fidelity
----
RID: `req-dev-validation-real-backend`
Status: `Proposed`

This is the load-bearing requirement. The gate MUST exercise the cycle against the **real DB-backed task backend**, never the pytest `ImmediateBackend` substitute. `ImmediateBackend` runs the task inline in the enqueuing transaction, which masks exactly the bug class that motivated this spec: a row enqueued in a transaction a separate worker connection cannot yet see. A gate that runs under the substitute backend would have stayed green through the Steady-Queue incident and is therefore not a gate at all for this failure class.

This positions the gate as the real-backend, post-commit, in-process-drain tier: higher fidelity than any `ImmediateBackend` test, and complementary to — not a replacement for — the deferred out-of-process real-worker tiers owned by `spec-tap-cares-task-backend.md` `req-tap-cares-task-backend-backlog-2` (tier 2: real `SteadyQueueBackend` + worker polled for terminal state; tier 3: fork-safety CI smoke job). Those tiers remain `Named, deferred` in the Map; this requirement does not absorb them.

**Mechanism (Phase-0 proven).** The in-process drain is the production Steady Queue primitives without the supervisor/fork/thread-pool/polling-loop that normally *drive* them: `ScheduledExecution.dispatch_next_batch()` → `ReadyExecution.objects.claim(queues, limit, process_id)` → `ClaimedExecution.perform()`, looped to empty or a deadline. Two concrete facts established by the Phase-0 spike (`tap_cares/management/commands/dev_validation_spike.py`, run inside the compose image under real `tap.settings`): (1) `ReadyExecution.claim` short-circuits to `[]` when `process_id is None`, so the drain MUST register a synthetic `steady_queue` `Process` (no heartbeat/supervisor/fork) and pass its id, deregistering after; (2) under `manage.py` (autocommit, not pytest), `run_collection`'s `transaction.on_commit` enqueue fires immediately and the `Job`+`ReadyExecution` rows are committed before the drain claims them — the real commit boundary `ImmediateBackend` never crosses. The spike proved the linchpin end-to-end (real enqueue → commit → drain → terminal `CollectionJob`) and proved teeth (no-drain ⇒ job stays `READY` ⇒ non-zero exit; a `FAILED` collector ⇒ non-zero exit surfacing the readiness reason). Grid-state assertion counts `CollectionJob --PRODUCED_BATCH--> Batch` edges with `disposition="imported"` (the Phase-0 `grift_batches` drift is now closed — see the note on `req-dev-validation-smoke-gate-4`).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-validation-real-backend-1 | Not `ImmediateBackend` | Proposed | The gate configures the real DB-backed task backend; `ImmediateBackend` is never used in the gate path. | |
| req-dev-validation-real-backend-2 | Terminal state via real backend | Proposed | The collector reaches a terminal `CollectionJob` state through the real backend's enqueue→commit→drain path, not an inline call. | Mechanism proven in Phase 0 (see section body): synthetic `Process` + `ReadyExecution.claim` + `ClaimedExecution.perform` loop; `claim` requires a non-null `process_id`. |
| req-dev-validation-real-backend-3 | Defers tiers 2–3 honestly | Proposed | Out-of-process real-worker concurrency/fork/lifecycle coverage is explicitly out of scope here and tracked under `req-tap-cares-task-backend-backlog-2`. | No scope absorption; no parallel vocabulary. |

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
Status: `Proposed`

Known-broken state is enumerated in a committed manifest, never held in human memory. The gate exits non-zero on any failure **not** listed, and also on any listed entry that no longer fails (stale entries are removed so the manifest ratchets toward zero). Each entry carries a one-line reason and owning context. The manifest is seeded at landing with whatever is genuinely known-broken at that moment — possibly empty.

This requirement also **names, once, the house convention** the repository has independently reached for repeatedly: a *bounded, reviewed, in-repo manifest that ratchets down* is TAP's canonical mechanism for honest coverage accounting. Its instances are the log-site-ID baseline (`spec-tap-logging.md`), the authz-coverage baseline (`spec-tap-auth-v0.md` `req-tap-auth-policy-9`), the direct-write-coverage baseline (`tap/tests/_direct_write_baseline.txt`), the Gryphon executor branch-coverage floor (`tap_grid/gryphon/coverage-baseline.json`, `req-gridkin-executor-branch-coverage`), this known-broken manifest, canary-set membership ([Canary Test Tier](#canary-test-tier)), and honest `CI-unguarded` spec-status labeling (`spec-tap-cares-task-backend.md`). New honesty mechanisms SHOULD follow this pattern rather than invent a parallel one — and, per [Reusable Ratchet Harness](#reusable-ratchet-harness), should increasingly share its *implementation*, not just its shape.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-validation-known-broken-1 | In-repo, not in memory | Proposed | Known-broken is a committed manifest; the gate never depends on a human remembering an exclusion. | |
| req-dev-validation-known-broken-2 | Ratchets down | Proposed | A failure not in the manifest fails the gate; a manifest entry that no longer fails also fails the gate until removed. | |
| req-dev-validation-known-broken-3 | Per-entry justification | Proposed | Each entry has a one-line reason and owning context. | |
| req-dev-validation-known-broken-4 | Seeded at landing | Proposed | The manifest is seeded with whatever is known-broken when the gate lands; an empty manifest (effective strict mode) is the preferred state. | |
| req-dev-validation-known-broken-5 | Named house convention | Proposed | The bounded-reviewed-ratcheting-manifest pattern is named here as canonical; other honesty mechanisms reference it rather than reinvent. | One vocabulary across sessions. |

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

### Reusable Ratchet Harness
----
RID: `req-dev-validation-ratchet-harness`
Status: `Proposed`

> **Forward note, not a build (jotted 2026-07-01).** Seeded for a validation-focused
> session. The convention above names the *shape*; this requirement is the
> observation that the shape has proliferated enough to share an *implementation*,
> plus a sketch of what to extract. Do not build speculatively — build it when the
> next ratchet would be the third caller of the same copy-pasted compare-and-report
> logic, or when the [Cold-Boot Smoke Gate](#cold-boot-smoke-gate) needs to invoke
> several ratchets uniformly.

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
| req-dev-validation-ratchet-harness-1 | Shared compare core | Proposed | A single helper implements the floor and ceiling-to-zero ratchet directions, with one actionable regression message and one improvement/bump message, replacing per-caller copies. | Measurement stays bespoke per surface. |
| req-dev-validation-ratchet-harness-2 | Common baseline schema | Proposed | Ratchet baselines share a committed artifact shape carrying the value plus provenance (`measured_at_commit`, scope, note). | |
| req-dev-validation-ratchet-harness-3 | Emits its Map row | Proposed | The harness produces the surface's Validation Map row stub with standard guard-status phrasing so honest-status labeling cannot drift. | Ties to `req-dev-validation-map`. |
| req-dev-validation-ratchet-harness-4 | Incremental migration, no speculative rewrite | Proposed | Existing ratchets migrate to the shared core only as they are next touched; the harness is built when it would have its second or third real caller, not before. | Guards against framework-ahead-of-demand. |

### Suite Tiering & Performance
----
RID: `req-dev-validation-suite-tiers`
Status: `Proposed`

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
| req-dev-validation-suite-tiers-1 | Three named lanes | Proposed | The suite exposes fast (`-m smoke`), affected (`-m "not slow"` or impact-selected), and full lanes, with a documented "which runs when". | Fast tier membership is owned by `req-dev-validation-canary-tier`. |
| req-dev-validation-suite-tiers-2 | Parallel full run | Proposed | The full lane runs under `pytest-xdist` with per-worker databases; this does not conflict with the shared-DB single-invocation rule. | Highest-ROI lever. |
| req-dev-validation-suite-tiers-3 | Profiled, not guessed | Proposed | `slow` designations follow from `--durations` evidence, not intuition. | |
| req-dev-validation-suite-tiers-4 | Impact lane is not a gate | Proposed | Any test-impact/affected selection accelerates the inner loop only; the pre-push gate always runs the full lane. | Counters the substitution-backend blind spot. |

### Promote-Path Enforcement
----
RID: `req-dev-validation-promote-hook`
Status: `Proposed`

The promote path MUST run the gate before advancing `origin/main` and refuse to push on red. This covers `scripts/promote-to-main.sh`, `scripts/promote-all-sessions.sh` (via the per-session script), and the documented manual fallback sequence. This is the reciprocal of `req-dev-multisession-promote-gate` in [spec-dev-multisession.md](spec-dev-multisession.md): that spec owns the requirement *on the promote workflow*; this requirement owns the gate *contract it invokes*. The two cross-reference and MUST stay consistent.

The gate runs after the pre-push merge (so it validates the exact tree that will become `origin/main`) and before the atomic dual-refspec push. On red, the push does not happen and the failure is reported; `origin/main` is never advanced past a tree that failed the gate. This is the mechanical enforcement of the otherwise prose-only "no messy/broken state to main" discipline that protects every spawned session.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-validation-promote-hook-1 | Gate before push | Proposed | The promote path runs the gate after the pre-push merge and before the atomic push. | Validates the exact tree that becomes `origin/main`. |
| req-dev-validation-promote-hook-2 | Red blocks the push | Proposed | A failing gate aborts the promote; `origin/main` is not advanced. | |
| req-dev-validation-promote-hook-3 | Covers script and fallback | Proposed | Enforcement applies to `promote-to-main.sh`, the all-sessions orchestrator, and the documented manual sequence. | |
| req-dev-validation-promote-hook-4 | Reciprocal consistency | Proposed | This requirement and `req-dev-multisession-promote-gate` cross-reference and stay consistent; neither restates the other's substance. | |

## Out Of Scope (v0)

- **Out-of-process real-worker integration (tiers 2–3).** Owned by `spec-tap-cares-task-backend.md` `req-tap-cares-task-backend-backlog-2`. Trigger: the persistent customer-hosted instance, or the strategy doc sequencing it sooner.
- **Broad per-flow correctness suite.** The gate is cold-boot-one-cycle plus the canary tier, not exhaustive integration. Trigger: a capability going "cold" (built, no longer in the daily assessment loop) earns a targeted integration test for *that* flow first.
- **Server-side CI (e.g. GitHub Actions).** The pre-push gate is local for the solo window. Trigger: a second contributor (human or agent) such that "did you run it locally?" stops being answerable by trust; when it lands it MUST stand up the existing compose image, not reimplement the environment.
- **Stage- and prod-validation.** Sibling specs and new Map rows when those environments exist. Trigger: the persistent customer-hosted instance inflection.

## Future

The deferral triggers above are deliberately concrete, not "later":

1. **Persistent customer-hosted instance.** The named inflection point: the system runs where the developer is not watching it. At that point dog-fooding stops being the safety net and the deferred tiers' demand signal has objectively fired — Shape-2/3 worker integration, server-side CI, and stage/prod-validation siblings become warranted.
2. **A capability going "cold."** The earlier, sharper trigger: the moment a flow leaves the daily assessment loop it loses its only coverage (dog-fooding). That specific flow is the first to earn a targeted integration test, well before the broader inflection.

Tier sequencing across this spec and `spec-tap-cares-task-backend.md` `req-tap-cares-task-backend-backlog-2` is currently forward-referenced (by that backlog entry) to a strategy doc that does not yet exist. Until it does, this Future section plus the [Validation Map](#validation-map) are the interim sequencing home; creating the strategy doc and migrating sequencing into it is itself a deferred item, not part of v0 of this spec.

## Status Vocabulary

Standard TAP states: `Proposed`, `Approved for Development`, `In Development`, `Implemented`, `Verified`, `Refactoring`, `Deprecating`, `Deprecated`, `Backlog`.
