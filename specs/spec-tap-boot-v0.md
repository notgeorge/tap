# TAP Boot v0 Specification

## Philosophy

`tap_boot`-style booting is how a TAP instance goes from a fresh database to a usable, populated, self-describing instance — **declaratively, deterministically, and with zero human interaction**. Before `tap_boot`, that journey was split between a flat collector-only boot profile (`tap_cares`' `fire_boot_collectors`) and `scripts/spawn-session.sh`, which did the *actual* ordered standup in bash: migrate → `sync_auth` → `import_plugin_grift` → reconcile → fire collectors → `createsuperuser`. The orchestration lived in a dev shell script, so a customer standup had no declared, reproducible contract. **v0 (landed) closes that gap:** one `manage.py boot` command applies one boot profile in fixed phases, and `spawn-session.sh` calls it.

The core doctrine is:

> One bootloader applies one multi-section boot profile in fixed phases. The profile *is* the configuration: config-as-code, lights-out, zero-touch. Standup is the same path in dev and in a customer's environment.

Boot is **configuration-as-code**, not an interactive wizard. There are no prompts, ever. The profile declares the desired instance state; the bootloader makes it so, idempotently, and fails loud if the profile is malformed.

Boot config is **trusted at the same level as application code**. A privileged operator's boot profile may do powerful, destructive things — overwrite the instance keystone, hard-sync capabilities, deactivate users. The bootloader validates *shape* (schema) and *correctness* (idempotent convergence, ordering), but it does **not** sandbox the operator's intent. The guards exist to stop a malformed profile from silently bricking a zero-touch standup — they are anti-footgun, not anti-operator.

The complexity bar is a real, multi-plugin instance: bringing up a samsite-grade instance (auth + several interdependent plugins + an ordered collector pipeline) exercises enough of the machinery to prove it. We design to that bar and let it teach us where the model needs to bend — in particular, whether collector firing stays a distinct step or becomes something plugins own as they come online.

## Goals

|   |   |   |
| :---: | --- | --- |
| 1. | One Path | A single bootloader command is the canonical standup for both dev and customer instances. |
| 2. | Config As Code | The boot profile fully declares instance state; standup is zero-touch and lights-out. |
| 3. | Composable | Each capability app owns its profile section's schema and apply logic; the bootloader composes them. |
| 4. | Idempotent | Re-applying a profile converges; standup is repeatable and safe to re-run. |
| 5. | Ordered & Loud | Phases run in a fixed, safe order; the whole profile is validated before anything is applied; failures are loud. |

## v0 Scope (minimal-useful)

v0 builds the **minimal standup path**: a single `manage.py boot` command that runs the existing standup operations in fixed phases under the bootloader actor, replacing the ordered bash steps in `spawn-session.sh` (`req-boot-spawn-bridge`). This is `step-rampart-launch-ready`'s "clean instance bring-up" — one declarative, reproducible command, with the dev path being the seed of the customer path.

All boot logic — command, phase sequencing, boot context, profile handling, logging, and (when built) the section handlers + registry — lives in the **`tap_boot` app**, first in `INSTALLED_APPS`, depending on and calling the capability apps' reusable, boot-agnostic ops. The domain apps stay boot-agnostic: **no boot logic in `tap_grid`/`tap_auth`/`tap_cares`/`tap_plugins`.**

> **Status — v0 landed 2026-06-24.** `manage.py boot --profile <id>` runs `auth → population` and is what `spawn-session.sh` now calls (the old `sync_auth`/`import_plugin_grift`/`reconcile_collectors`/`fire_boot_collectors`/`createsuperuser` steps are gone; `fire_boot_collectors` is removed). The profile is the ordered-steps shape (`boot/<id>.json`, version 1, `population.steps` of `seed-plugin`/`fire-collector`); `boot/base.json` (seed-all, no collectors) is the plain-spawn default, `boot/samsite.json` the demo standup. Boot-agnostic ops added/reused: `tap_auth.sync_auth` + new `tap_auth.ensure_initial_admin`, `tap_plugins.seeding.seed_plugin`, `tap_cares.reconcile_collector_nodes` + new `tap_cares.services.fire_collector_and_await`. Phases live as functions in `tap_boot/orchestrator.py` so each becomes a section-handler body when `req-boot-sections` lands. Covered by `tap_boot/tests/` and proven live on samsite (boto3 collector fired a real AWS pull; a missing-secret collector aborted loud). Deferred per below remain `Proposed`.

Deliberately **deferred until a real consumer drives the shape** (skepticism-of-overbuilding, per the Rampart roadmap):

- **App-registered section handlers + registry + per-section schema composition (`req-boot-sections`) and two-layer validate-before-apply (`req-boot-validate`)** — kept `Proposed` as the planned shape, but **not built in v0**. Their first consumer is the authN **Google OIDC provider configuration** (`req-tap-auth-providers`): that config will define the section + schema shape concretely, so it is built when authN lands, not guessed ahead of it. v0 implements the phases directly in the boot command; the structure is chosen so a phase's op-call becomes a handler body later — an additive refactor, not a rewrite.
- **Instance keystone generation (`req-boot-identity`)** — backlog, not critical path. In v0 the instance keystone comes from plugin GRIFT (the samsite bundle already lays down the "Samsite" keystone).
- **`--dry-run`/`plan`, the formal idempotency convergence contract (`req-boot-idempotent`), and a durable boot report (`req-boot-report`)** — deferred; v0 relies on the underlying ops being idempotent and on action logging.

## Roadmap Alignment

This spec supports `plan/road-rampart.md`:

- `step-rampart-first-paying-customer` names the boot loader directly: *"expand to support plugins… boot profiles that you can load and will be smart enough to start up with all plugins and you'll need to figure out the auth system and what it means to self-configure (remember all those places where you hardcoded config in secrets files?)"* and *"Configuration… important settings can be added and set… initially stored as part of the boot profile."*
- It is the substrate `spec-tap-auth-v0.md` (`req-tap-auth-boot`) already assumes: an `auth` section in "the larger TAP boot profile" applied by a bootloader that composes per-app schema fragments. That bootloader is defined here.

## Prior Art

This spec follows well-trodden declarative-provisioning patterns rather than inventing boot machinery:

- **Kubernetes `kubectl apply`** — declarative desired-state that converges idempotently; re-applying the same manifest is a no-op. TAP's idempotent re-apply follows this.
- **Terraform** — config-as-code with `plan` (dry-run) before `apply`, and a hard line between *authoring* config and *applying* it. TAP's `--dry-run` and the boot-applies / authoring-is-separate split mirror this.
- **Helm values / Kustomize** — a single declarative document composed of sections owned by different concerns. TAP's multi-section profile + per-app section handlers mirror this, but composition lives in plain Python (app-registered handlers), not template/`$ref` machinery.
- **cloud-init / Ansible** — zero-touch, no-prompt provisioning from a declarative spec. TAP's lights-out doctrine mirrors this.
- **Django `migrate`** — idempotent forward application already runs in the container entrypoint; boot layers the instance-state convergence above migrations, not inside them.
- **Existing TAP machinery** — the `tap_cares` collector boot profile (`spec-dev-boot-collectors.md`), the `tap_grid` registry's duplicate-key guard (`tap_grid/registry.py`), and the `req-tap-auth-boot` auth-boot ordering are absorbed and generalized rather than replaced.

## Relationship To Other Specs

- **Absorbs `specs/spec-dev-boot-collectors.md`.** Its collector-firing mechanics — firing via `run_collection`, sequential ordered firing, per-profile `on_failure`, opt-in selection — are preserved as the `fire-collector` step-type inside this spec's population phase. The standalone `fire_boot_collectors` framing is generalized into the bootloader; the collector spec's RIDs remain the detailed contract for *how a collector is fired*.
- **Provides the bootloader `req-tap-auth-boot` assumes.** The `auth` section is `tap_auth`'s registered section handler; the auth-boot ordering (capability sync → protected group sync → built-in actor sync → initial admin → provider validation/build → provider/domain deactivation) is that handler's internal apply sequence, run within this spec's `auth` phase.

## Requirements

| RID | Name | Status | Notes |
| --- | --- | :---: | --- |
| req-boot-app | [Bootloader Ownership](#bootloader-ownership) | Implemented | **v0.** One `manage.py boot`; all boot logic lives in `tap_boot`, which calls capability-app ops |
| req-boot-profile | [Multi-Section Profile](#multi-section-profile) | Implemented | **v0 (minimal).** One profile drives standup (plugins to seed + collectors to fire) via the `population` section; app-owned multi-section composition deferred |
| req-boot-sections | [App-Registered Section Handlers](#app-registered-section-handlers) | Proposed | **Deferred** to first consumer (authN Google OIDC config); handlers/registry live in `tap_boot` |
| req-boot-validate | [Validate Before Apply](#validate-before-apply) | Proposed | **Deferred** with `req-boot-sections`. v0 keeps only: schema shape + unknown plugin/collector key fails loud |
| req-boot-phases | [Fixed Phase Order](#fixed-phase-order) | Implemented | **v0: auth → population** (bootloader resolved in auth, bound for population); fuller order is future |
| req-boot-population | [Population Phase](#population-phase) | Implemented | **v0.** Ordered seed-plugin / fire-collector; unknown key aborts first |
| req-boot-identity | [Identity Section](#identity-section) | Proposed | **Backlog, not critical path.** Generate a keystone only if none exists; v0 keystone comes from plugin GRIFT |
| req-boot-idempotent | [Idempotent Re-Apply](#idempotent-re-apply) | Implemented | **v0 principle** (ops are idempotent; seed + admin re-apply tested); formal convergence contract deferred |
| req-boot-trust | [Config-As-Code Trust Model](#config-as-code-trust-model) | Implemented | **v0.** Boot config is code-level-trusted; guards are anti-footgun, not anti-operator |
| req-boot-secrets | [Secret References Only](#secret-references-only) | Implemented | **v0.** Profiles reference `TAP_SECRETS_ROOT` keys / env, never embed secrets; missing secret fails loud at apply |
| req-boot-spawn-bridge | [Spawn Bridge](#spawn-bridge) | Implemented | **v0.** `spawn-session.sh` calls the bootloader; dev == customer standup |
| req-boot-report | [Boot Logging](#boot-logging) | Implemented | **v0.** Boot logs actions with secrets redacted; durable report deferred |

---

### Bootloader Ownership
----
RID: `req-boot-app`  
Status: `Implemented`

A single bootloader command is the canonical path that stands a TAP instance up from a fresh, migrated database to a usable, populated, self-describing instance. It is a platform capability, not a plugin.

#### Implementation

- The bootloader is an explicit `manage.py` command (e.g. `manage.py boot`), not silent app-startup mutation.
- It owns: profile resolution and load, full-profile validation, fixed phase sequencing, per-section dispatch to registered handlers, idempotent application, and action logging.
- It does **not** own provider/auth/collector internals — each is owned by its capability app's section handler (`req-boot-sections`). The bootloader is the orchestrator and the contract enforcer.
- **Code home: the `tap_boot` app owns all boot logic.** Everything boot — the `manage.py boot` command, profile handling, the boot context (`tap_bootloader` actor resolution + per-run state), phase sequencing, action logging, and (when built, `req-boot-sections`) the section handlers + their registry — lives in the first-party `tap_boot` app. `tap_boot` sits first in `INSTALLED_APPS` and depends on the capability apps, calling their reusable, boot-agnostic ops (`tap_auth.sync_auth`, the `tap_grid` service layer, `tap_cares` collector firing / reconcile, the plugin GRIFT import path). **No boot logic lives in `tap_grid`/`tap_auth`/`tap_cares`/`tap_plugins`** — the dependency direction is one-way (`tap_boot → everything`), which is also why the section-handler base/registry live in `tap_boot`, not `tap_grid` (nothing below boot imports them). Same rationale as `tap_auth`: a cross-cutting management plane deserves a named app.
- Database migrations remain in the container entrypoint (idempotent, safe to re-run) and are a precondition of boot, not a boot phase.
- The bootloader is the canonical standup for **both** dev (`spawn-session.sh`, `req-boot-spawn-bridge`) and customer deployments, so the path is dog-fooded continuously before a customer sees it.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-app-1 | Explicit Command | Proposed | Boot is an explicit `manage.py` command, not startup-time mutation. | |
| req-boot-app-2 | Single Orchestrator | Proposed | One bootloader owns sequencing, validation, and dispatch; sections own their internals. | |
| req-boot-app-3 | Canonical Standup | Proposed | The same bootloader path is used for dev and customer standup. | |
| req-boot-app-4 | tap_boot Code Home | Proposed | All boot logic — command, sequencing, boot context, profile handling, logging, and (when built) section handlers + registry — lives in `tap_boot`; domain apps expose boot-agnostic ops that boot calls; no boot logic in other apps. | |

---

### Multi-Section Profile
----
RID: `req-boot-profile`  
Status: `Implemented`

A boot profile is a single config-as-code document composed of named sections.

#### Implementation

> **v0 (minimal):** the profile drives standup with the plugins to seed + collectors to fire (≈ today's flat `boot/<id>.json`, e.g. `boot/samsite.json`) plus minimal admin info. Named, app-owned sections composed from per-app JSON-Schema fragments (below) are the planned shape but are **deferred** to their first consumer (`req-boot-sections`); v0 does not compose per-app schemas.

- A profile is a version-controlled file. Selection and the no-profile behavior differ by mode:
  - **dev / manual:** `--profile` > `TAP_BOOT_PROFILE` > none ⇒ clean no-op for outbound work (the existing opt-in — a bare run reaches out to nothing).
  - **customer / deploy / entrypoint:** an explicit profile is **required**. Coming up with no profile — empty but apparently healthy — is a failure, not a no-op: deploy boot fails loud unless an explicit `--allow-empty` is passed. A deployment must never silently start empty because `TAP_BOOT_PROFILE` was accidentally omitted.
- v1 sections: `identity`, `auth`, `population`. The section set is open — any capability app may register a section (`req-boot-sections`).
- The profile supersedes the flat collector-only profile shape: the existing collector list becomes the `fire-collector` steps of the `population` section (`req-boot-population`).
- A profile carries only declarative state and secret *references* (`req-boot-secrets`), never secret values.
- Each section's shape is defined by its owning app's mandatory JSON Schema fragment; the profile as a whole is the composition of those fragments plus a thin bootloader-owned envelope (version, profile metadata, section ordering-within-population).
- A profile with no `population` outbound steps is a safe, no-network standup (identity + auth only).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-profile-1 | Named Sections | Proposed | A profile is a document of named sections, not a flat list. | |
| req-boot-profile-2 | Supersedes Flat Profile | Proposed | The collector-only profile is absorbed as the population fire-collector steps. | |
| req-boot-profile-3 | References Not Secrets | Proposed | Profiles contain only declarative state and secret references. | |
| req-boot-profile-4 | Opt-In Outbound | Proposed | With no population outbound steps selected, standup reaches out to nothing. | |
| req-boot-profile-5 | Deploy Requires Profile | Proposed | Customer/deploy/entrypoint boot requires an explicit profile (or explicit `--allow-empty`); a missing profile fails loud, never a silent empty-but-healthy start. | |

---

### App-Registered Section Handlers
----
RID: `req-boot-sections`  
Status: `Proposed`

Each capability app owns its profile section through a registered handler. Apps cannot overwrite each other's sections.

#### Implementation

> **Deferred — not built in v0** (see [v0 Scope](#v0-scope-minimal-useful)). Kept `Proposed` as the planned shape; its first consumer is the authN Google OIDC provider configuration (`req-tap-auth-providers`), which will define the section + schema shape concretely. v0 implements the phases directly in the boot command (`req-boot-phases`); a phase's op-call becomes a handler body when this lands — an additive refactor, not a rewrite.

- A section handler bundles: a stable `section_key`, a **mandatory** JSON Schema fragment for that section's shape, and a `validate(section_data)` / `plan(section_data)` / `apply(section_data)` interface — not merely a schema plus `apply(dry_run=True)`. `validate` does **semantic pre-resolution** (resolve references, catch impossible config) before any mutation; `plan` reports what would change; `apply` mutates.
- Handlers register on a `tap_grid` `Registry` (`tap_grid/registry.py`), which **raises `ImproperlyConfigured` on a duplicate key** by default (no `merge_fn`). Two apps registering the same `section_key` is therefore a hard startup error — the immutability is structural, not convention.
- Registering a handler without a schema fragment is itself a registration error: every section is schema-described or it does not exist.
- The bootloader passes each handler **only its own section's data** — this isolates *configuration*: a handler cannot be driven by another section's config, so config-level cross-section coupling is structurally impossible. It is **not** a code sandbox: handler code is trusted Python and can technically query or mutate anything, exactly like all boot code (`req-boot-trust`). The guarantee is honest as **data isolation, not code isolation**.
- Section handlers and the registry live in `tap_boot` (not the domain apps): each handler calls the relevant capability app's boot-agnostic ops (`auth` → `tap_auth.sync_auth` + initial admin + provider config; `identity` → the `tap_grid` keystone service; `population` → the plugin GRIFT import path + `tap_cares` collector firing). This keeps the dependency direction one-way (`req-boot-app`).
- The registry is populated at app `ready()` time (read-only registration only, consistent with `req-plugin-load-v0-ready-readonly`); the handlers' `apply` runs only under the explicit boot command.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-sections-1 | Registered Handlers | Proposed | Sections are provided by app-registered handlers on a `tap_grid` registry. | |
| req-boot-sections-2 | Duplicate Section Fails | Proposed | Two handlers for one `section_key` raise `ImproperlyConfigured` at startup. | |
| req-boot-sections-3 | Schema Mandatory | Proposed | A handler without a JSON Schema fragment cannot register. | |
| req-boot-sections-4 | Section Data Isolation | Proposed | A handler receives only its own section's *data* (config isolation, no cross-section config coupling); handler *code* remains trusted, not sandboxed. | |

---

### Validate Before Apply
----
RID: `req-boot-validate`  
Status: `Proposed`

The whole profile is validated before any of it is applied.

#### Implementation

> **Deferred with `req-boot-sections` — not built in v0** (see [v0 Scope](#v0-scope-minimal-useful)). The two-layer framework lands with the section handlers it validates (first consumer: authN Google OIDC config). v0 keeps only the cheap guard that already exists in `fire_boot_collectors`: an unknown plugin/collector key fails loud before any population step (`req-boot-population`).

- Validation has **two layers, both before any mutation**:
  1. **Schema (shape):** every present section validates against its handler's JSON Schema fragment; unknown section keys and unknown fields fail loud (`additionalProperties: false` at the section level).
  2. **Semantic (pre-resolution):** each handler's `validate` resolves references before any `apply` runs — unknown plugin/collector keys, missing required secret references, unsupported profile version, and impossible/contradictory config (e.g. an auth config that would lock out every admin) are caught up front, not discovered mid-mutation. This generalizes `fire_boot_collectors`' existing "unknown key aborts before any collector fires." Schema alone catches shape, not these.
- A `--dry-run` / `plan` mode runs both validation layers and reports the planned actions (which sections, which population steps, in what order) **without mutating** state. It is the **best current plan, not a guarantee** — like Terraform's plan, state can drift between plan and apply, so a dry-run is advisory.
- Dry-run defaults to **offline / no outbound**: schema + semantic validation + local plan only. Live checks (provider reachability, OIDC discovery, upstream probes) are opt-in via an explicit `--live-checks`, never the default.
- Failures are loud and machine-readable: the error names the offending section/field/step so a zero-touch caller (or an AI operator) can correct the profile and re-run deterministically.
- Validation is independent of where the profile came from (boot-embedded today; a standalone source later, per `req-tap-auth-config-source`) — the validator operates on the loaded document, not its origin.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-validate-1 | Validate All First | Proposed | All sections validate before any `apply` runs. | |
| req-boot-validate-2 | Unknown Rejected | Proposed | Unknown section keys / fields fail loud. | |
| req-boot-validate-3 | Dry Run Advisory + Offline | Proposed | `--dry-run`/`plan` validates and reports the best current plan (advisory, may drift) without mutating; defaults offline, live checks opt-in via `--live-checks`. | |
| req-boot-validate-4 | Loud Machine-Readable Failure | Proposed | Validation errors name the offending location precisely. | |
| req-boot-validate-5 | Semantic Pre-Resolution | Proposed | Beyond schema shape, handlers semantically validate (unknown plugin/collector/secret-ref, bad version, impossible config) before any `apply` mutates. | |

---

### Fixed Phase Order
----
RID: `req-boot-phases`  
Status: `Implemented`

Boot runs sections in a fixed, code-defined phase order. Profiles cannot reorder phases.

#### Implementation

> **v0 phase order: `auth → population`** (see [v0 Scope](#v0-scope-minimal-useful)). The fuller `bootstrap → identity → auth → population` described below is the future shape: v0 needs neither a separate `bootstrap` actor-resolve phase nor an `identity` keystone phase, because nothing writes through the service layer before `auth`. In v0 the boot actor is resolved *in* the `auth` phase (after `sync_auth` creates it) and bound (`acting_as`) for `population`.

- Coarse phase order is hardcoded, not config. **v0: `auth → population`** (the fuller order below is added in code as those phases gain content).
- **`bootstrap` resolves the boot actor first.** Identity, auth, and population are all service-layer writes, and the auth doctrine forbids `User=None` at the service boundary (`req-tap-auth-actor-model`) — so a named actor must exist before the *first* boot write. The `bootstrap` pre-phase creates-or-resolves the `tap_bootloader` `program` built-in actor (`req-tap-auth-builtins`); every subsequent boot write runs as `tap_bootloader`. The chicken-and-egg of the *first* actor is resolved cleanly: creating it is a low-level bootstrap write *below* the named-actor contract — the same place the auth spec puts migrations / raw table creation — and once it exists, identity/auth/population all go through the service layer as a named actor. This supersedes any "identity is the first phase" reading: identity writes the keystone, which needs the actor, so it cannot be first.
- **Authority, scoped — not omnipotence.** Boot writes need *authorization*, and capabilities sync in the `auth` phase, so the bootloader actor must be able to write during `identity`. Rather than implicit boot-omnipotence, the `bootstrap` pre-phase grants `tap_bootloader` an **explicit, least-privilege, code-defined boot-capability bundle** — exactly what boot needs (`grid.write`, `grid.import_grift`, the auth/capability/provider-management capabilities, `config.manage`, `cares.run_collectors`) and no more. It deliberately **excludes destructive grid demolition boot never needs** — `grid.purge` (DEBUG-destructive) and `grid.delete` — so a boot *bug* cannot nuke the grid. Boot's own destructive operations (keystone overwrite, capability prune, user deactivation) live in the auth/config/capability domain, not arbitrary grid mutation, so the exclusion costs boot nothing.
  - This bounds the blast radius of boot *bugs* (anti-footgun, `req-boot-trust`); it is **not** a sandbox against a *malicious* profile. Because the bundle includes capability-management, a malicious trusted profile could self-escalate — accepted, since boot config is code-level-trusted by design. Least-privilege here protects against accidents and documents boot's reach: the right level of defense, not security theater.
  - The grant is established at `bootstrap` (resolve the actor + grant its scoped bundle) before `identity` — an explicit scoped grant, not a disabled gate. This supersedes the earlier "implicit boot privilege" framing and settles the authz chicken-and-egg cleanly.
- The load-bearing invariant remains **auth before population**: the remaining `program` built-in actors, capabilities, and grants land in the `auth` phase before `population` seeds or collects under them.
- Profiles control **what is in** each section and the **intra-population** step order (`req-boot-population`) — never the phase sequence itself.
- Phase order is intentionally rigid until there is a concrete reason to relax it; new phases are added in code with explicit placement, not declared by profiles.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-phases-1 | Fixed Order | Proposed | Phase order (`bootstrap → identity → auth → population`) is code-defined; profiles cannot reorder phases. | |
| req-boot-phases-2 | Auth Before Population | Proposed | Auth (capabilities, built-in actors, grants) is applied before any actor-attributed population work. | |
| req-boot-phases-3 | Bootstrap Actor First | Proposed | A `bootstrap` pre-phase resolves the `tap_bootloader` actor before identity; all boot writes run as it, so no boot write is `User=None`. | |
| req-boot-phases-4 | Least-Privilege Boot Actor | Proposed | `tap_bootloader` is granted an explicit least-privilege boot-capability bundle (no `grid.purge`/`grid.delete`), not full admin — bounding the blast radius of boot bugs. | |

---

### Population Phase
----
RID: `req-boot-population`  
Status: `Implemented`

The population phase brings plugins online and populates them, as an ordered list of declared, interleavable steps.

#### Implementation

> **v0:** built — it maps directly onto the existing standup ops (`import_plugin_grift` path + `reconcile_collector_nodes` + collector firing). With `req-boot-validate` deferred, the unknown-key pre-resolution below is v0's validate-before-mutate.

- The `population` section is an **ordered** list of steps; each step is one of the v1 step-types:
  - `seed-plugin`: bring a plugin online — its types/edges/searches are registered (already done at `ready()`), then its GRIFT seed bundles are imported via the `import_plugin_grift` path. **Convergence caveat:** GRIFT dedups by batch identity — re-importing an *identical* batch is skipped, so an *edited* bundle does **not** converge on re-boot unless its batch identity changes. Boot resolves this explicitly rather than assuming upsert: the default is **durable version-bumped batches** (a plugin bumps its batch version when content changes, so the new identity converges), with a **DEBUG-only boot force/reimport** mode for dev iteration; production never blind-force-reimports. This decision is named so it is chosen, not silently assumed — the trap is an edited-but-not-bumped bundle that silently skips while boot reports success.
  - `fire-collector`: fire a collector via `run_collection`, with the per-profile `on_failure` and sequential-ordering semantics absorbed from `spec-dev-boot-collectors.md`.
- Steps run **strictly in declared order, sequentially, no overlap**. The declared order is load-bearing: a collector that reads another collector's output must be ordered after it so its edges mint in one boot pass (the established collector-pipeline dependency, stated generically).
- v1 default arrangement mirrors today: all `seed-plugin` steps, then `fire-collector` steps. The step model deliberately permits **interleaving** (seed a plugin, fire its collectors, seed the next) so that a plugin whose collector depends on a prior plugin being fully *online and collected* can be expressed without restructuring.
- **Open seam (let samsite teach us):** whether `fire-collector` stays a top-level population step or migrates into a plugin-owned "after I am online, fire these" hook is deferred. The step model is chosen so either outcome is a later refinement, not a rewrite. v1 does not require plugin-owned collector hooks; it only refuses to foreclose them.
- A `seed-plugin` or `fire-collector` step naming an unknown plugin/collector key fails loud before any population step runs (pre-resolution, as `fire_boot_collectors` does today).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-population-1 | Ordered Steps | Proposed | Population is an ordered list of steps applied strictly in order, sequentially. | |
| req-boot-population-2 | Two Step-Types | Proposed | v1 step-types are `seed-plugin` and `fire-collector`. | |
| req-boot-population-3 | Interleaving Permitted | Proposed | The model allows seed/fire steps to interleave, not only seed-all-then-fire-all. | |
| req-boot-population-4 | Unknown Key Fails | Proposed | An unknown plugin/collector key aborts before any population step runs. | |
| req-boot-population-5 | Collector Semantics Absorbed | Proposed | `fire-collector` preserves `run_collection`, `on_failure`, and ordered-firing semantics. | |
| req-boot-population-6 | GRIFT Convergence Explicit | Proposed | `seed-plugin` convergence is bounded by GRIFT batch identity: version-bumped batches converge; a DEBUG-only force/reimport serves dev; production never blind-force-reimports; edited-but-not-bumped must not silently skip-as-success. | |

---

### Identity Section
----
RID: `req-boot-identity`  
Status: `Proposed`

If no keystone exists on the grid at boot, the bootloader lays down a generic instance keystone so a zero-touch standup is always self-described; it never overrides a keystone that already exists.

#### Status Details

**Backlog, not critical path.** A deliberately deferred refinement (formalized here from a shot-from-the-hip idea). In v0 the instance keystone comes from plugin GRIFT — the samsite bundle already lays down the "Samsite" keystone (`spec-grid-keystone.md`), read oldest-first as the foundational context. Boot writes no keystone in v0.

#### Implementation

- The fallback is owned by `tap_boot` (a future `identity` phase) and writes through the `tap_grid` keystone service as the `tap_bootloader` actor.
- It is **create-if-absent only**: if any keystone already exists on the grid, boot leaves it untouched (the plugin-GRIFT or operator keystone wins). Only an empty grid gets the generated keystone.
- The generic keystone is built from profile envelope metadata (a `title` + `description` describing the instance) plus the grid identity, and ships a `context_schema_json` documenting its `context_json` to satisfy the keystone self-describing contract (`req-grid-keystone-validation`). Adding that `title`/`description` to the profile envelope is part of this backlog item.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-identity-1 | Generate If Absent | Proposed | If no keystone exists at boot, a generic instance keystone is generated from profile metadata; an existing keystone is never overridden. | Backlog |
| req-boot-identity-2 | Self-Describing | Proposed | The generated keystone ships `context_json` paired with a `context_schema_json` that validates it. | Backlog |

---

### Idempotent Re-Apply
----
RID: `req-boot-idempotent`  
Status: `Implemented`

Re-applying a profile converges the instance to the declared state without duplication or error.

#### Implementation

> **v0:** relies on the underlying ops already being idempotent in practice (`sync_auth` hard-sync, `reconcile_collector_nodes`, GRIFT batch-identity dedup, collector upsert/OCC). The **formal** convergence contract + convergence tests below are deferred.

- Boot is safe to re-run, but idempotency is scoped to **declared domain state**, not operational/audit state. Re-applying the same profile converges the declared resources — no duplicated nodes/edges/actors/keystones, no hard error — but operational records *do* and *should* append: log lines, boot events, `CollectionJob`s, entity history/versions, timestamps, and any FLIP records are an append-only audit trail of each run, not domain state to converge. "Same instance state" means same *declared* state; the audit trail honestly shows that boot ran twice.
- Each section handler is responsible for its own declared-state convergence: auth capability sync is a hard-sync, initial-admin is add/update-only (`req-tap-auth-boot`), identity keystone is create-or-update (`req-boot-identity`), `seed-plugin` converges only as far as GRIFT batch identity allows (`req-boot-population`), `fire-collector` re-collection converges via the collector's own upsert/OCC behavior.
- Convergence, not blind replay: a re-apply updates changed declared resources and leaves the rest, rather than re-creating from scratch; it does not suppress the operational append trail.
- Idempotency is what makes zero-touch standup re-runnable after a partial failure: fix the cause, re-run the same profile.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-idempotent-1 | Declared State Converges | Proposed | Re-applying converges declared domain state (no duplicated domain objects, no error); operational/audit records (logs, boot events, jobs, history, FLIP) may append. | |
| req-boot-idempotent-2 | Section-Owned | Proposed | Each handler owns its own declared-state convergence semantics. | |

---

### Config-As-Code Trust Model
----
RID: `req-boot-trust`  
Status: `Implemented`

Boot config is trusted at the same level as application code. Guards defend against malformed profiles, not against the operator.

#### Implementation

- Boot is **zero-touch and lights-out**: no interactive prompts, ever. The profile fully declares intent; the bootloader applies it without human interaction.
- Boot config is **code-level-trusted**: a privileged operator's profile may declare powerful, destructive changes (keystone overwrite, capability prune, user deactivation). The bootloader does **not** sandbox the operator's intent and makes no attempt to defend against a malicious boot config — that trust boundary is the same one we extend to module code.
- The guards that exist — full-profile validation, `--dry-run`, idempotent convergence, loud failure — are for **correctness and operability**, not security against the operator. Their job is to stop a *malformed* profile from silently bricking an unattended, zero-touch standup, not to second-guess a *well-formed* one.
- This is the boot analogue of the auth recovery-floor doctrine (`req-tap-auth-policy`): some layer is trusted-by-design so the system can be stood up and recovered; boot is that layer for instance state.
- Generating a profile (interactively or via a helper) is explicitly **out of scope and deferred** — boot only ever *applies* config-as-code. (See Backlog: profile generator.)

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-trust-1 | Zero-Touch | Proposed | Boot never prompts; it applies a declared profile without interaction. | |
| req-boot-trust-2 | Operator-Trusted | Proposed | Boot does not sandbox the operator; destructive declared changes are permitted. | |
| req-boot-trust-3 | Guards Are Anti-Footgun | Proposed | Validation/dry-run/idempotency defend against malformed profiles, not the operator. | |

---

### Secret References Only
----
RID: `req-boot-secrets`  
Status: `Implemented`

Boot profiles reference secrets; they never contain them.

#### Implementation

- Profile sections that need secrets carry **references** to keys under `TAP_SECRETS_ROOT`; the referenced secret is resolved at apply time by the owning handler.
- Secret values are never embedded in profile files and never persisted to the database (consistent with `req-tap-auth-providers` secret handling).
- A reference to a missing secret fails loud at apply (and is surfaced by `--dry-run` where the check is offline-safe).
- Boot logging redacts secret values (`req-boot-report`).

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-secrets-1 | References Only | Proposed | Profiles carry secret references under `TAP_SECRETS_ROOT`, never values. | |
| req-boot-secrets-2 | Missing Secret Fails | Proposed | An unresolved secret reference fails loud at apply. | |

---

### Spawn Bridge
----
RID: `req-boot-spawn-bridge`  
Status: `Implemented`

The dev spawn flow stands instances up through the bootloader, so dev and customer standup share one path.

#### Implementation

- `scripts/spawn-session.sh` invokes the bootloader (`manage.py boot --profile <id>`) instead of hand-running `import_plugin_grift`, `fire_boot_collectors`, and `createsuperuser` as separate ad hoc steps.
- The de-facto spawn ordering becomes the bootloader's declared phases; the bash script keeps only its dev-host concerns (worktree, ports, `.env.local`, secrets bind-mount, credentials file).
- The spawn-created `admin` superuser joining `tap_admin` (`req-tap-auth-local-5`) runs through the bootloader's identity/auth path, not a separate shell step.
- Migrations remain in the container entrypoint and run before the bootloader (precondition, not a boot phase).
- Dev and customer standup exercising the same bootloader is the mechanism that keeps boot dog-fooded before any customer relies on it.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-spawn-bridge-1 | Spawn Calls Bootloader | Proposed | `spawn-session.sh` stands up via the bootloader, not ad hoc management commands. | |
| req-boot-spawn-bridge-2 | One Standup Path | Proposed | Dev and customer standup use the same bootloader path. | |
| req-boot-spawn-bridge-3 | Admin Bridge Through Boot | Proposed | The `admin` → `tap_admin` bridge runs through boot, not a separate shell step. | |

---

### Boot Logging
----
RID: `req-boot-report`  
Status: `Implemented`

Boot logs what it did. A durable boot-report artifact is deferred.

#### Implementation

- The bootloader logs each section/step action — added / updated / synced / fired / skipped — using the standard TAP logging conventions (`spec-tap-logging.md`, site-token discipline).
- The `tap_bootloader` actor resolved in the `bootstrap` pre-phase (`req-boot-phases`) is also the **logging-context actor** for the boot phase: it is bound at "bootloader operation start" (`req-tap-auth-logging`), so every boot log line — and every Flaw emitted during boot (`spec-tap-flaw-v0.md`) — is attributed to it without extra plumbing. The one actor serves as writer, authorization subject, and log attribution at once.
- Secret values are redacted in all boot logs (`req-boot-secrets`).
- Logging is the v1 record of a boot; a durable, queryable boot-report node/model is deferred to backlog.
- Under failure, logs name the failed section/step and reason so an unattended caller can diagnose and re-run.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-report-1 | Actions Logged | Proposed | Each boot action is logged with the standard conventions. | |
| req-boot-report-2 | Secrets Redacted | Proposed | Boot logs never contain secret values. | |

---

## Suggested Implementation Sequence (v0 minimal)

All in the new `tap_boot` app; domain apps only gain/expose callable ops.

1. Create the `tap_boot` app; add it **first** in `INSTALLED_APPS`. Add `manage.py boot --profile <name> [--allow-empty]` + a small boot context (resolve `tap_bootloader`, one `acting_as` around population).
2. Profile load: `--profile` > `TAP_BOOT_PROFILE`; load `boot/<id>.json` (reuse the existing loader/shape); deploy requires a profile (`req-boot-profile`).
3. `auth` phase: call `tap_auth.sync_auth()`; resolve `tap_bootloader`; call a new `tap_auth.ensure_initial_admin()` (add/update-only, joins `tap_admin` — absorbs spawn's `createsuperuser` + group-join; `req-tap-auth-boot` step 4).
4. `population` phase (under `acting_as(tap_bootloader)`): seed plugins (the `import_plugin_grift` path), `reconcile_collector_nodes()`, then fire collectors via a new callable `fire_boot_collectors_from_profile()` extracted from the command. Unknown plugin/collector key fails loud first (`req-boot-population`).
5. Bridge `spawn-session.sh`: replace steps 5.9 / 6 / 6.1 / 6.5 + the `tap_admin` group-join with one `manage.py boot --profile "$TAP_BOOT_PROFILE"` (passing the `DJANGO_SUPERUSER_*` env it already resolves). Keep worktree / ports / `.env.local` / secrets-mount / password / `.dev-credentials`.
6. Tests + status flips: fresh-DB `boot --profile samsite` reaches the same end-state as the bash spawn; bridge runs green. Flip the v0 reqs `Proposed → Implemented`; leave `req-boot-sections` / `req-boot-validate` (OIDC-driven) and `req-boot-identity` (backlog) `Proposed`.

Deferred (build when the demand signal arrives, not before): the section-handler framework + two-layer validation (`req-boot-sections` / `req-boot-validate`, first consumer = authN Google OIDC config); the keystone fallback (`req-boot-identity`); `--dry-run`/`plan`; the formal idempotency contract; the durable boot report.

## Backlog

Deferred out of the v0 minimal path (see [v0 Scope](#v0-scope-minimal-useful)), to be built when their demand signal arrives:

- **App-registered section handlers + registry + per-section schema composition (`req-boot-sections`), two-layer validate-before-apply + `--dry-run` (`req-boot-validate`)** — first consumer is the authN Google OIDC provider configuration (`req-tap-auth-providers`); built then, so the real config defines the section/schema shape.
- **Instance keystone fallback (`req-boot-identity`)** — generate-if-absent + the profile envelope `title`/`description`; not critical path.
- **Formal idempotency convergence contract + tests (`req-boot-idempotent`)** — v0 relies on op-level idempotency.

Longer-horizon:

- Profile generator helper (CLI or otherwise) that *produces* a boot profile — authoring is separate from applying; this would be a convenience, not a requirement.
- Plugin-owned collector-firing hooks (resolve the `req-boot-population` open seam once samsite teaches us).
- Plugin dependency-graph resolution (v1 relies on declared order; a real DAG is deferred).
- Durable, queryable boot-report node/model (v1 logs only).
- Profile inheritance / composition (multiple profiles, overlays, base+override).
- Satellite / headless boot variants (where no human admin is expected; intersects `req-tap-auth-boot` relaxations).
- Standalone (non-boot-embedded) config source for sections (intersects `req-tap-auth-config-source`).

## Status Vocabulary

| Status States |  |
| --- | --- |
| Proposed | Requirement has been designed but not yet accepted for implementation. |
| Approved for Development | Requirement is accepted and ready to be implemented. |
| In Development | Actively being worked on. |
| Implemented | Has been written. |
| Verified | Has met the acceptance criteria. |
| Refactoring | In the process of being re-worked. |
| Deprecating | In the process of being deprecated. |
| Deprecated | No longer part of the current architecture. |
