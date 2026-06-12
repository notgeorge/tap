# TAP Boot v0 Specification

## Philosophy

`tap_boot`-style booting is how a TAP instance goes from a fresh database to a usable, populated, self-describing instance — **declaratively, deterministically, and with zero human interaction**. Today that journey is split between a flat collector-only boot profile (`tap_cares`' `fire_boot_collectors`) and `scripts/spawn-session.sh`, which does the *actual* ordered standup in bash: migrate → `import_plugin_grift` → fire collectors → `createsuperuser`. The orchestration lives in a dev shell script, which means a customer standup has no declared, reproducible contract.

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
| req-boot-app | [Bootloader Ownership](#bootloader-ownership) | Proposed | One `manage.py` bootloader is the canonical standup |
| req-boot-profile | [Multi-Section Profile](#multi-section-profile) | Proposed | Config-as-code profile with named sections; supersedes the flat collector profile |
| req-boot-sections | [App-Registered Section Handlers](#app-registered-section-handlers) | Proposed | Registry-backed handlers; mandatory schema fragment; duplicate section = hard error |
| req-boot-validate | [Validate Before Apply](#validate-before-apply) | Proposed | Validate every section before applying any; dry-run; fail loud |
| req-boot-phases | [Fixed Phase Order](#fixed-phase-order) | Proposed | identity → auth → population; auth strictly before actor-attributed work |
| req-boot-population | [Population Phase](#population-phase) | Proposed | Declared, ordered, interleavable seed-plugin / fire-collector steps |
| req-boot-identity | [Identity Section](#identity-section) | Proposed | First-class grid identity + instance keystone, guaranteed before population |
| req-boot-idempotent | [Idempotent Re-Apply](#idempotent-re-apply) | Proposed | Re-applying a profile converges; standup is repeatable |
| req-boot-trust | [Config-As-Code Trust Model](#config-as-code-trust-model) | Proposed | Boot config is code-level-trusted; guards are anti-footgun, not anti-operator |
| req-boot-secrets | [Secret References Only](#secret-references-only) | Proposed | Profiles reference `TAP_SECRETS_ROOT` keys, never embed secrets |
| req-boot-spawn-bridge | [Spawn Bridge](#spawn-bridge) | Proposed | `spawn-session.sh` calls the bootloader; dev == customer standup |
| req-boot-report | [Boot Logging](#boot-logging) | Proposed | Boot logs actions with secrets redacted; durable report deferred |

---

### Bootloader Ownership
----
RID: `req-boot-app`  
Status: `Proposed`

A single bootloader command is the canonical path that stands a TAP instance up from a fresh, migrated database to a usable, populated, self-describing instance. It is a platform capability, not a plugin.

#### Implementation

- The bootloader is an explicit `manage.py` command (e.g. `manage.py boot`), not silent app-startup mutation.
- It owns: profile resolution and load, full-profile validation, fixed phase sequencing, per-section dispatch to registered handlers, idempotent application, and action logging.
- It does **not** own provider/auth/collector internals — each is owned by its capability app's section handler (`req-boot-sections`). The bootloader is the orchestrator and the contract enforcer.
- Database migrations remain in the container entrypoint (idempotent, safe to re-run) and are a precondition of boot, not a boot phase.
- The bootloader is the canonical standup for **both** dev (`spawn-session.sh`, `req-boot-spawn-bridge`) and customer deployments, so the path is dog-fooded continuously before a customer sees it.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-app-1 | Explicit Command | Proposed | Boot is an explicit `manage.py` command, not startup-time mutation. | |
| req-boot-app-2 | Single Orchestrator | Proposed | One bootloader owns sequencing, validation, and dispatch; sections own their internals. | |
| req-boot-app-3 | Canonical Standup | Proposed | The same bootloader path is used for dev and customer standup. | |

---

### Multi-Section Profile
----
RID: `req-boot-profile`  
Status: `Proposed`

A boot profile is a single config-as-code document composed of named sections.

#### Implementation

- A profile is a version-controlled file (selected as today: `--profile` flag > `TAP_BOOT_PROFILE` env > none ⇒ clean no-op for outbound work).
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

---

### App-Registered Section Handlers
----
RID: `req-boot-sections`  
Status: `Proposed`

Each capability app owns its profile section through a registered handler. Apps cannot overwrite each other's sections.

#### Implementation

- A section handler bundles: a stable `section_key`, a **mandatory** JSON Schema fragment for that section's shape, and an `apply(section_data, *, dry_run)` callable.
- Handlers register on a `tap_grid` `Registry` (`tap_grid/registry.py`), which **raises `ImproperlyConfigured` on a duplicate key** by default (no `merge_fn`). Two apps registering the same `section_key` is therefore a hard startup error — the immutability is structural, not convention.
- Registering a handler without a schema fragment is itself a registration error: every section is schema-described or it does not exist.
- The bootloader passes each handler **only its own section's data**. A handler has no access to other sections' data, so cross-section overwrite is structurally impossible.
- Section ownership in v1: `identity` → `tap_grid` (`req-boot-identity`); `auth` → `tap_auth` (`req-tap-auth-boot`); `population` → bootloader-owned step dispatcher over plugin/collector step-types (`req-boot-population`).
- The registry is populated at app `ready()` time (read-only registration only, consistent with `req-plugin-load-v0-ready-readonly`); the handlers' `apply` runs only under the explicit boot command.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-sections-1 | Registered Handlers | Proposed | Sections are provided by app-registered handlers on a `tap_grid` registry. | |
| req-boot-sections-2 | Duplicate Section Fails | Proposed | Two handlers for one `section_key` raise `ImproperlyConfigured` at startup. | |
| req-boot-sections-3 | Schema Mandatory | Proposed | A handler without a JSON Schema fragment cannot register. | |
| req-boot-sections-4 | Section Isolation | Proposed | A handler receives only its own section's data; cross-section writes are impossible. | |

---

### Validate Before Apply
----
RID: `req-boot-validate`  
Status: `Proposed`

The whole profile is validated before any of it is applied.

#### Implementation

- The bootloader validates **every** present section against its owning handler's schema fragment **before** invoking **any** handler's `apply`. A single invalid section aborts the run before mutation.
- Unknown section keys and unknown fields within a section fail loud (`additionalProperties: false` discipline at the section level).
- A `--dry-run` mode validates the full profile and reports the planned actions (which sections, which population steps, in what order) **without mutating** state — the Terraform-`plan` analogue.
- Failures are loud and machine-readable: the error names the offending section/field/step so a zero-touch caller (or an AI operator) can correct the profile and re-run deterministically.
- Validation is independent of where the profile came from (boot-embedded today; a standalone source later, per `req-tap-auth-config-source`) — the validator operates on the loaded document, not its origin.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-validate-1 | Validate All First | Proposed | All sections validate before any `apply` runs. | |
| req-boot-validate-2 | Unknown Rejected | Proposed | Unknown section keys / fields fail loud. | |
| req-boot-validate-3 | Dry Run | Proposed | `--dry-run` validates and reports the plan without mutating. | |
| req-boot-validate-4 | Loud Machine-Readable Failure | Proposed | Validation errors name the offending location precisely. | |

---

### Fixed Phase Order
----
RID: `req-boot-phases`  
Status: `Proposed`

Boot runs sections in a fixed, code-defined phase order. Profiles cannot reorder phases.

#### Implementation

- Coarse phase order is hardcoded: `identity → auth → population`. It is code, not config.
- The load-bearing invariant is **auth strictly before any actor-attributed work**: named `program` built-in actors (bootloader/system/scheduler/collector runners) must exist before anything seeds or collects under a named actor (`req-tap-auth-actor-model` sequencing; `req-tap-auth-builtins`). The `auth` phase creates them; the `population` phase consumes them.
- Profiles control **what is in** each section and the **intra-population** step order (`req-boot-population`) — never the phase sequence itself.
- Phase order is intentionally rigid until there is a concrete reason to relax it; new phases are added in code with explicit placement, not declared by profiles.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-phases-1 | Fixed Order | Proposed | Phase order is code-defined; profiles cannot reorder phases. | |
| req-boot-phases-2 | Auth First | Proposed | Auth (and its built-in actors) is applied before any actor-attributed population work. | |

---

### Population Phase
----
RID: `req-boot-population`  
Status: `Proposed`

The population phase brings plugins online and populates them, as an ordered list of declared, interleavable steps.

#### Implementation

- The `population` section is an **ordered** list of steps; each step is one of the v1 step-types:
  - `seed-plugin`: bring a plugin online — its types/edges/searches are registered (already done at `ready()`), then its GRIFT seed bundles are imported via the `import_plugin_grift` path.
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

---

### Identity Section
----
RID: `req-boot-identity`  
Status: `Proposed`

The instance's identity — grid identity and its keystone(s) — is a first-class boot section, applied before population.

#### Implementation

- The `identity` section carries the instance grid identity and the instance keystone(s) (`spec-grid-keystone.md`): the foundational self-description any reader (operator, agent, Codex) consults to learn what the instance is.
- The keystone is **create-or-update**: applying a keystone that already exists updates it rather than erroring, and the change persists in history (per `req-boot-trust` — boot is privileged and overwrite is allowed by design).
- The bootloader **guarantees the instance keystone is laid down before the population phase**, so plugins layer onto an already-self-described instance rather than racing to define it.
- The instance keystone is owned by boot, not seeded incidentally as ordinary plugin GRIFT — elevating the most foundational artifact to a guaranteed, first-class step. (Plugins may still contribute their own keystones via their seed bundles; the *instance* keystone is the boot-owned one.)
- Identity application is idempotent (`req-boot-idempotent`): re-applying converges the keystone to the declared state, with prior versions retained in history.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-identity-1 | First-Class Section | Proposed | Grid identity + instance keystone are a dedicated boot section, not incidental GRIFT. | |
| req-boot-identity-2 | Before Population | Proposed | The instance keystone is guaranteed laid down before any population step. | |
| req-boot-identity-3 | Create Or Update | Proposed | Applying a keystone that exists updates it; changes persist in history. | |

---

### Idempotent Re-Apply
----
RID: `req-boot-idempotent`  
Status: `Proposed`

Re-applying a profile converges the instance to the declared state without duplication or error.

#### Implementation

- Boot is safe to re-run: applying the same profile twice yields the same instance state, not duplicated nodes/edges/actors or a hard error.
- Each section handler is responsible for its own convergence: auth capability sync is a hard-sync, initial-admin is add/update-only (`req-tap-auth-boot`), identity keystone is create-or-update (`req-boot-identity`), `seed-plugin` uses GRIFT upsert semantics, `fire-collector` re-collection converges via the collector's own upsert/OCC behavior.
- Convergence, not blind replay: a re-apply updates what changed and leaves the rest, rather than re-creating from scratch.
- Idempotency is what makes zero-touch standup re-runnable after a partial failure: fix the cause, re-run the same profile.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-idempotent-1 | Converges | Proposed | Re-applying a profile yields the same state, no duplication, no error. | |
| req-boot-idempotent-2 | Section-Owned | Proposed | Each handler owns its own convergence semantics. | |

---

### Config-As-Code Trust Model
----
RID: `req-boot-trust`  
Status: `Proposed`

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
Status: `Proposed`

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
Status: `Proposed`

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
Status: `Proposed`

Boot logs what it did. A durable boot-report artifact is deferred.

#### Implementation

- The bootloader logs each section/step action — added / updated / synced / fired / skipped — using the standard TAP logging conventions (`spec-tap-logging.md`, site-token discipline).
- Secret values are redacted in all boot logs (`req-boot-secrets`).
- Logging is the v1 record of a boot; a durable, queryable boot-report node/model is deferred to backlog.
- Under failure, logs name the failed section/step and reason so an unattended caller can diagnose and re-run.

#### Acceptance Criteria

| ACID | Title | Status | Description | Notes |
| --- | --- | :---: | --- | --- |
| req-boot-report-1 | Actions Logged | Proposed | Each boot action is logged with the standard conventions. | |
| req-boot-report-2 | Secrets Redacted | Proposed | Boot logs never contain secret values. | |

---

## Suggested Implementation Sequence

Guidance for implementation sessions, not a required order:

1. Define the bootloader command + section-handler registry (on the `tap_grid` registry) + the full-profile validate-before-apply loop + `--dry-run`.
2. Implement the `identity` section (grid identity + instance keystone, create-or-update) and wire it first.
3. Implement the `population` section step dispatcher, absorbing `fire_boot_collectors` as the `fire-collector` step-type and `import_plugin_grift` as the `seed-plugin` step-type; preserve ordered, sequential firing.
4. Register `tap_auth`'s `auth` section handler (its internal ordering is `req-tap-auth-boot`); enforce the auth-before-population phase invariant.
5. Bridge `spawn-session.sh` onto the bootloader; converge the dev standup onto the same path.

## Backlog

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
