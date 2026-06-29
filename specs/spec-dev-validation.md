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
| req-dev-validation-promote-hook | [Promote-Path Enforcement](#promote-path-enforcement) | Proposed | Reciprocal of `req-dev-multisession-promote-gate` |

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
| Async-delivery — tier 1 | `spec-tap-cares-task-backend.md` (`-transactional-integrity-1`) | `run_collection` `on_commit` deferral is positively, mutation-provenly guarded | Per-commit (`pytest`) | CI-guarded (`TestTransactionalIntegrity`) |
| Async-delivery — tiers 2–3 | `spec-tap-cares-task-backend.md` (`-backlog-2`) | Real-worker fork safety, queue isolation, wall-clock lifecycle, pickup latency, crash recovery | Deferred | Named, deferred |
| Assembled-instance health | `specs/spec-tap-health-v0.md` (the pair) | A stood-up instance's real backends actually work: DatabaseCache table provisioned (`tap_cache`), live db + cache set/get round-trip + best-effort queue + secrets probe pass. Catches the latent-provisioning-fault class (standup "succeeds" but a never-exercised-at-boot path is broken) | Per-commit (`pytest`) + per-spawn (`manage.py health` exec gate) | Partially guarded — **CI-guarded** for the unit pieces (`tap_health/tests/test_checks.py` cache-table system check; `tap_health/tests/` registry/service/projection-leak/command tests) and the database-tagged check fires loud at `migrate`/`check --database`; **per-spawn** the `manage.py health` non-zero-exit gate (`spawn-session.sh` Step 6.5) replaces both the prior 5xx-passes liveness blindness and the now-parked unauthenticated `/healthz` (`req-tap-health-exposure-4`). The full cold-boot assembled-instance live-health run under automation is **Named, deferred** → folds into the Cold-boot system cycle gate (CI/CD is roadmap item 5, post-July) |
| Cold-boot system cycle | this spec (`req-dev-validation-smoke-gate`) | Fresh DB → migrate → seed → one real collector cycle → one scheduler fire, end to end | Pre-push | Gate-guarded *(target)* |
| Canary tier | this spec (`req-dev-validation-canary-tier`) | Blast-radius unit/functional subset still passes | Pre-push + per-commit | Gate-guarded *(target)* |

Rows marked *(target)* describe the intended state once this spec is implemented; their guard status is honestly `Named, deferred` until then. The Map is updated in the same change as any new or retired validation surface, and reviewed when it changes — the change to the Map *is* the visible decision.

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

This requirement also **names, once, the house convention** the repository has independently reached for repeatedly: a *bounded, reviewed, in-repo manifest that ratchets down* is TAP's canonical mechanism for honest coverage accounting. Its instances are the log-site-ID baseline (`spec-tap-logging.md`), the authz-coverage baseline (`spec-tap-auth-v0.md` `req-tap-auth-policy-9`), this known-broken manifest, canary-set membership ([Canary Test Tier](#canary-test-tier)), and honest `CI-unguarded` spec-status labeling (`spec-tap-cares-task-backend.md`). New honesty mechanisms SHOULD follow this pattern rather than invent a parallel one.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-dev-validation-known-broken-1 | In-repo, not in memory | Proposed | Known-broken is a committed manifest; the gate never depends on a human remembering an exclusion. | |
| req-dev-validation-known-broken-2 | Ratchets down | Proposed | A failure not in the manifest fails the gate; a manifest entry that no longer fails also fails the gate until removed. | |
| req-dev-validation-known-broken-3 | Per-entry justification | Proposed | Each entry has a one-line reason and owning context. | |
| req-dev-validation-known-broken-4 | Seeded at landing | Proposed | The manifest is seeded with whatever is known-broken when the gate lands; an empty manifest (effective strict mode) is the preferred state. | |
| req-dev-validation-known-broken-5 | Named house convention | Proposed | The bounded-reviewed-ratcheting-manifest pattern is named here as canonical; other honesty mechanisms reference it rather than reinvent. | One vocabulary across sessions. |

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
