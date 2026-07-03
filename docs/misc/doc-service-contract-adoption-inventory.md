# Service Contract Adoption Inventory

Captured 2026-07-03, during the service-layer-boundary spec work (pairs with
`specs/spec-service-layer-boundary.md`, still `Proposed`). This is a thinking /
survey document, not a spec and not scheduled implementation. It answers one
question asked across the whole app + plugin tree:

> **Where could we implement the formal service contract — the guarded service
> boundary — and where would that be the wrong tool?**

It complements [Non-Grid Surface Inventory](doc-non-grid-surface-inventory.md)
(which maps surfaces that don't touch the grid) and the per-app auth work in
[Auth Per-App Standards](doc-auth-per-app-standards.md).

Method: four parallel read-only inspections (tap_auth; tap_cares/tap_boot/tap_plugins;
all 12 plugins; tap_api/web/viz/health/secrets + a repo-wide direct-write sweep),
each grounded in the actual source. Every claim below carries a `file:line`.

---

## The headline: two families, not one worklist

The convention's premise is *"every public operation checks permission first."*
That premise splits the codebase into **two families**, and conflating them is the
main risk:

- **Family A — gate-able service boundaries.** Layers that front a protected
  resource at *runtime*, after the auth system exists. These *adopt the convention
  as written*: three zones, `__all__` of gated operations, contract module,
  below-gate impl.
- **Family B — un-gateable layers.** Layers that run *before or beneath* the gate
  system, so a capability check is structurally unavailable to them. For these,
  **"public at all" is the risk** — every public symbol is a permanently
  un-lockable privileged door. Their defense is *surface-minimization + import
  encapsulation + a runtime context self-check*, **not** a gate. Trying to bolt
  `@requires_capability` onto them is a category error (you'd be gating the thing
  that mints the gate).

The single most important through-line: **"can't gate the gate" (tap_auth's
`policy`/`enforcement`/`actors`) and "can't gate before the gate exists"
(tap_boot, pre-boot) are the same phenomenon.** They belong in the boundary spec
as a named *un-gateable-layer variant*.

### Ranked candidacy

| Surface | Family | Score | One-line |
| --- | --- | :---: | --- |
| **tap_cares** | A | **5/5** | Largest live front-door cluster; 6 grid-mutating ops, only 1 gated at the gateway today. Strongest payoff. |
| **tap_auth** | A (+ B carve-out) | **3/5** | Spec-named next adopter, but the clean gateway is *small* (3 session verbs); `sync.py` is opt-out, `policy/enforcement/actors` are Family B. |
| **tap_plugins** | A | **3/5** | Real but small: `seed_plugin` (ungated writer) + `get_plugin_report` (gated, wrong shape). |
| **pre-boot (`tap/preboot.py`)** | **B** | **—** | ~22 public pre-auth privileged functions, no `__all__`. **The real exposure.** Minimize, don't gate. |
| **tap_boot** | **B** | **—** | Already near-sealed (steps are `_`-private); finish the seal. Do **not** gate `run_boot`. |
| Plugin tier (12) | A (future) | **1/5** | No services, routers, own caps, or direct writes. `lotr` is the one seed. Correctly premature. |
| tap_api / tap_web / tap_viz | — | **1/5** | Clean callers of the grid gateway. Nothing to adopt. |
| tap_health / secrets subsystem | — | **1/5** | Read-only infra; no mutation front-door. |

**Direct-write sweep (repo-wide): clean.** The direct-write baseline is drained to
zero (`tap/guards/baselines/direct_write.txt` = header only). The *only* two direct
writes to a TAP-managed `BaseModel` in the first-party tree are both in
`tap_cares/scheduler.py:240,263`, and both carry reviewed inline `# TAP-WRITE-COV:`
tokens (program-actor bookkeeping; atomic single-SQL compare-and-set claim). No
unsanctioned bypass exists anywhere.

---

## Family A — gate-able service boundaries

### 1. tap_cares — 5/5, the strongest adopter

**Protected resource:** INTERNAL_ONLY grid nodes (CollectionJob, Collector,
Schedule, ScheduleFire) + collector execution.

**Front-door cluster (spread across three flat modules today):**

| Function | Location | Mutates | Gated at gateway? |
| --- | --- | --- | :---: |
| `run_collection` | `tap_cares/services.py:154` | CollectionJob + edge, enqueues task | ✅ `@requires_capability("cares.run_collectors")` |
| `self_test_collector` | `tap_cares/services.py:72` | read-only self-test | ✗ (public, ungated) |
| `fire_collector_and_await` | `tap_cares/services.py:306` | calls `run_collection` | ✗ (gate is downstream) |
| `create_schedule` | `tap_cares/scheduler.py:171` | `create_node("schedule")` + edge | ✗ |
| `set_schedule_enabled` | `tap_cares/scheduler.py:213` | `patch_node` + direct `.update()` | ✗ |
| `evaluate_tick` | `tap_cares/scheduler.py:364` | claims + creates ScheduleFire, fires | ✗ |
| `reconcile_collector_nodes` | `tap_cares/registry.py:131` | `write_batch` Collector nodes | ✗ |

Real external callers confirm these are front doors: `evaluate_tick` ← the tick task
(`tap_cares/task_backend.py:46`); `reconcile_collector_nodes` ← `manage.py boot` and
a mgmt command (`tap_cares/management/commands/reconcile_collectors.py:32`).

**Current state:** flat modules, no `services/` package, no `__all__`, no contract
module; **only 1 of 6 grid-mutating public functions carries a gateway gate.** The
other five bind a program actor and lean entirely on the *stateless write backstop*
`assert_write_authorized` (`tap_auth/enforcement.py:187`) — defense-in-depth is
present (waivers at `scheduler.py:270,304,323,347`, `registry.py:230`), but the
gateway-level gate the convention requires is absent on 5/6.

**Worklist:**
1. Create `tap_cares/services/` package; move the seven functions into a gateway
   `__init__.py`.
2. Gate every grid-mutating export — `create_schedule`/`set_schedule_enabled` under a
   `cares.manage_schedules` cap; `evaluate_tick`/`reconcile_collector_nodes` under the
   program vocabulary they already run as. Decide gates for the two currently-ungated
   public reads.
3. Push `_scheduler_ctx`, `_claim_and_create_fire`, `_finalize_*`, slot helpers
   below-gate (most already `_`-prefixed — good).
4. `__tap_contract_modules__ = ("types",)` for the result dataclasses
   (`CollectorSelfTestResult` et al., currently in `collectors/readiness.py`).
5. Keep `register_collector`/`get_collector` (in-memory, `ready()`-time, no grid) out
   of the gateway.

### 2. tap_auth — 3/5, named next adopter, but a *split* surface

tap_auth is unusual: it **defines** the gate mechanism *and* owns protected state.
Its surface splits four ways, and only the first is a clean Family-A gateway:

- **Session invalidation (Family A):** `invalidate_all_sessions`
  (`tap_auth/sessions.py:41`), `invalidate_user_sessions` (`:57`),
  `invalidate_session` (`:80`). Already authorize `auth.manage_sessions` — but via an
  **inline `authorize(...)`** in the body (`:46,63,83`), not the `@requires_capability`
  decorator the guard recognizes, and they take a positional `actor` instead of the
  `caller_context` kwarg. `resolve_user` (`:94`) is an ungated user-table read.
- **`sync.py` (opt-out):** `sync_capabilities`/`sync_protected_groups`/
  `sync_builtin_actors`/`ensure_initial_admin` (`sync.py:94,194,286,332`) write
  Capability/Group/Permission/User by direct ORM. The module docstring
  (`sync.py:14-18`) declares them migration-class, out of the service-layer contract.
  → must be a **reviewed opt-out** (`req-service-boundary-discovery-2`), named as a
  deliberately-open edge, **not** silently ungated.
- **`policy`/`enforcement`/`actors` (Family B — can't gate the gate):**
  `policy.authorize`/`policy.can` (`policy.py:99,120`), `requires_capability`/
  `gates_per_operation` (`enforcement.py:76,103`), `get_builtin_actor`/`acting_as`
  (`actors.py:42,64`). The gate is *built from* these; gating them with the gate is
  infinite regress. They live **outside** the guarded package by necessity — the
  mechanism a gateway consumes, not a gateway.
- **allauth adapter (AuthN edge, not a service op):** `pre_social_login`/`save_user`
  → `_sync_external_identity` (`adapter.py:98,158,192`).

**Current state:** `tap_auth/__init__.py` is empty (0 lines); no `services/`; the only
`__all__` in the app is a health probe (`health.py:88`). Public/private split by habit.

**Worklist:** create `tap_auth/services/` hosting the three session verbs (convert
inline authorize → decorator, switch to `caller_context`); contract module for the
exception taxonomy (`AuthzError` + subclasses) and public enums (`AccessDecision`,
`RiskLevel`, `CapabilitySpec`…); mark `sync.py` as reviewed opt-out; state the
gate-machinery asymmetry in the spec so the guard never tries to gate `policy`/
`enforcement`/`actors`. Needs an `auth.read`-style cap minted for the user reads
(none exists today).

**Composition is already correct.** Session ops gate `auth.manage_sessions` in
tap_auth's own layer; `tap_grid.services` gates only `grid.*` and imports the gate
*mechanism* (not a migrated-down cap) from `tap_auth.enforcement`
(`services/__init__.py:27-32`). Two gates, two owners — exactly the compose-up shape.

**⚠ Latent coupling to clean up:** `enforcement.py:42` imports
`WRITE_SCOPE_CAPABILITIES`/`service_write_scope` from `tap_grid.write_guard` — a
sideways **tap_auth → tap_grid** dependency. Doesn't break composition, but the
standing `avoid-tap-app-interdependencies` posture would push that write-scope
contextvar *down* into `tap/`. Worth folding into the adoption work.

### 3. tap_plugins — 3/5, small real surface

- `seed_plugin` (`tap_plugins/seeding.py:68`) — writes grid via `grift_import`;
  **ungated at its own layer**, defended only by the downstream `grid.import_grift`
  gate + write backstop (waiver at `seeding.py:119`).
- `get_plugin_report` (`tap_plugins/report.py:92`) — a gated read, but via **inline**
  `policy.authorize(..., "plugins.read")` (`report.py:113`), the exact seam the
  docstring at `report.py:105` flags for the service-layer refactor.
- `build_report` (`report.py:117`) — trusted-CLI pure builder; stays ungated but then
  must **not** sit in the gateway `__all__` (expose as a below-gate util the CLI
  imports, mirroring `manage.py health`).

**Worklist:** `tap_plugins/services/` with `seed_plugin` + `get_plugin_report` in the
gateway; give `seed_plugin` its own `plugins.*` gate composing above
`grid.import_grift` (compose-up, not sole reliance on the downstream gate); convert the
inline authorize to the decorator; contract module for `BundleOutcome`/`PluginManifest`.

> **Nuance:** the authed git-source plugin *install* path (github_pat via GIT_ASKPASS)
> is **not** in tap_plugins — it's in the pre-boot substrate
> (`tap/plugin_source_auth.py`, `tap/preboot.py:install_plugins`), deliberately pushed
> down into `tap/` and running **pre-auth**. That's Family B, below.

### 4. Plugin tier (all 12) — correctly premature; `lotr` is the seed

No plugin has a `services/` package, registers an API router, defines its own
capability, or performs a direct BaseModel write. The tier is **model + collector +
read-panel**. The two grid mutations that exist both flow through the *already-gated
grid gateway*: `lotr` `patch_node` (`plugins/lotr/.../editors/character.py:58-66`) and
`gryphon_playground`'s test-only `delete_node` (`gridkin/runner.py:271`).

**`lotr` is the one designated first adopter** — the sole plugin with a plugin-owned
operation *pair* (a write `handle_save` + a read `list_characters_with_bio`). But even
lotr authorizes via the *grid's* `grid.write`; a plugin gateway only earns its keep
once lotr grows its **own** cap (e.g. `lotr.edit_character`) composing above
`grid.write`. **Trigger adoption when** a plugin grows (1) a tap_api router doing
protected work under `/api/v1/plugins/<slug>/`, or (2) an interactive mutation
warranting an app-level capability. Until then the tier correctly *inherits* the grid
boundary — a valid finding, not a gap.

### 5. Callers / read-only infra — nothing to adopt

- **tap_api** — exemplary caller: every mutation delegates to `tap_grid.services`
  (`routers/entities.py:52,67,77`; `routers/edges.py:61,79`), authorizing up-front
  before the lookup (closes the 404-before-403 oracle). No direct ORM writes.
- **tap_web** — presentation + caller; the generic editor POST
  (`views.py:336-359`) delegates to `descriptor.handle_save` → plugin `patch_node`,
  never `obj.save()`. Reads gate `grid.read` first (`views.py:257,306`).
- **tap_viz** — pure presentation; all `.objects` usage is `select_related().get()`.
- **tap_health** — read-only diagnostics; only write is a cache eviction
  (`probes.py:49`). Not a boundary.
- **secrets subsystem** (`tap/runtime_secrets.py`, `tap_cares/secrets/`,
  `tap_auth/providers/secrets.py`) — a **read** resolver, no grid state, no `Secret`
  model, already guarded for leak/size. Its own trust surface, not a *grid*-service
  boundary. At most a future *read*-gated boundary if secret access is ever
  centralized — out of this convention's scope.

---

## Family B — un-gateable layers (minimize, don't gate)

These run before/beneath the gate system. **The defense inverts:** you can't put a
lock on the door, so you minimize the number of doors, seal them structurally, and add
a runtime self-check. Same *defense-in-depth* shape the grid uses (static
direct-write lint + runtime `write_guard`), just with the capability check swapped for
**surface-minimization + import-encapsulation + context assertion**.

| | Family A (gated) | Family B (un-gateable) |
| --- | --- | --- |
| Front door | public **+ gated** | **minimized** to ~one entry point |
| Failure mode | public **without a gate** | **public at all** beyond the sealed entry |
| Static defense | capability gate on the gateway | public-surface **ceiling ratchet** |
| Structural lock | one-way import | **import-encapsulation** (external → `_impl`) — *primary* here |
| Runtime defense | `write_guard`/`read_guard` backstop | **context self-check** at the entry point |

### tap_boot — already near-sealed; finish the seal (do NOT gate)

`run_boot` (`tap_boot/orchestrator.py:50`) **cannot** be gated: its first act is
`sync_auth()`, which *mints* the capabilities, protected groups, and the
`tap_bootloader` actor (`orchestrator.py:104-109`); only then does it
`acting_as(bootloader)` for population writes. `@requires_capability` is unavailable at
the top of the very function that creates the capability system. Its true front door is
the process entrypoint `manage.py boot` (`management/commands/boot.py`), authorized by
OS/deploy trust. Its grid writes **compose down** through the already-guarded
grid/GRIFT boundaries.

**The good case.** Every boot *step* is already `_`-private
(`_phase_auth`…`_apply_fire_collector`, `orchestrator.py:104-262`) — boot steps are
**not** publicly importable today, which is exactly the target. Residual public
surface (no `__all__` anywhere in tap_boot): `run_boot` + `check_profile`
(`orchestrator.py:50,79`), profile loaders `load_profile`/`profile_ids`/`boot_dir`
(`profile.py:98,94,89`), the step dataclasses `SeedPluginStep`/`FireCollectorStep`/
`BootProfile` (`profile.py:35,47,66`), and exceptions.

**Seal worklist (cheap):** add `__all__ = ("run_boot",)` (+ maybe `check_profile`) to
`orchestrator.py`; treat the profile dataclasses/loaders as a declared contract zone;
keep phases `_`-private (already true). **Do not** put capability gates on `run_boot`.

### pre-boot (`tap/preboot.py`) — WIDE OPEN; the real work

This is the surface most in tension with the minimize thesis. `tap/preboot.py` has
**~22 public functions and no `__all__`**, including privileged pre-auth operations any
importer can invoke out of band: `install_plugins` (`:254`), `install_plugin_specs`
(`:156`), `uv_install_args` (`:216`), `take_snapshot` (`:546`), `conformance_gate`
(`:361`), `reconciliation_guard` (`:406`), `dependency_consistency_guard` (`:453`),
`run_preboot` (`:610`), `main` (`:637`). It has a script `main()` entry but exports
everything around it — privileged, pre-auth, un-lockable, and fully importable.

Adjacent shared substrate is legit but un-advertised: `tap/source_scan.py` (11 public
symbols, no `__all__`), `tap/ratchet.py` (4 public, no `__all__`). **Good models exist
in the same tree:** `tap/guards/__init__.py:25` (clean 5-name `__all__`),
`tap/plugin_source_auth.py:195` (clean 9-name `__all__`) — the discipline is achievable.

**Worklist:** collapse `preboot.py`'s public surface to `run_preboot`/`main` + a small
reviewed set; `_`-prefix the install/snapshot/gate internals; add `__all__`; give
`source_scan.py`/`ratchet.py` an `__all__` advertising their intended shared surface.

### Three buildable mechanisms (two are new controls)

1. **Public-surface ceiling ratchet — HIGH feasibility, rails already exist.** The
   *inverse* of the service-gateway guard: AST-count non-`_` top-level defs/classes per
   boot/pre-boot module and ratchet the count **downward** — a new public symbol fails
   the build. `ratchet_ceiling` (`tap/ratchet.py:52`) and the `CeilingRatchet` Guard
   base (`tap/guards/base.py:85`) already exist and power four guards
   (`callsite`, `json_naming`, `mypy`, cold-boot). Build on the shared `parse_file` +
   `ScopeStackVisitor` from `source_scan.py`.
2. **Import-encapsulation guard (external → `_impl`) — the highest-value MISSING
   control.** `spec-service-layer-boundary.md req-service-boundary-inviolability-1`
   marks it a gap; confirmed **no such guard exists** (grep of `tap/guards/` found
   nothing). For Family B this is the *primary* structural lock, because there's **no
   gate behind the door** — it's the thing that actually prevents out-of-band
   invocation of a public boot internal. Same DIY-AST shape as the other tree-scanners.
3. **Runtime context self-check (George's proposal) — the runtime half.** Once the boot
   entry is called, it inspects **ambient system state** to decide if it's a legitimate
   boot context vs. an in-request / re-entrant / out-of-band call, and **errors loud**
   if illegitimate. Assessed against tap_boot's *actual* invocation model (traced):

   **The invocation model is narrow and well-behaved.** `run_boot`
   (`tap_boot/orchestrator.py:50`) is called from exactly two management-command
   `handle()` bodies — `manage.py boot` (`management/commands/boot.py:89`) and
   `manage.py cold_boot_gate` (`management/commands/cold_boot_gate.py:267`) — plus tests.
   **Correction to an earlier worry:** tap_boot has **no `AppConfig.ready()` at all**
   (`tap_boot/apps.py` states verbatim "it needs no ready()"; the provisioning check
   moved to tap_health). So the feared "boot runs during app init" case **does not
   exist** — `run_boot` is always reached at the top of a management-command `handle()`,
   *after* `apps.populate()` completed, never from a view, never during init.

   - **Primary signal — a confirmed-*positive* stack check (preferred over
     evidence-of-absence).** The stable positive fact is that every `manage.py <cmd>`
     runs through Django's `BaseCommand.execute() → handle()`, and the executing
     `Command` instance sits in the call stack as a frame's `self`. So walk `f_back`
     from `run_boot` and assert an *allowed boot Command* is in the call chain:

     ```python
     import sys
     from django.core.management.base import BaseCommand

     _ALLOWED_BOOT_COMMANDS = frozenset({
         "tap_boot.management.commands.boot",
         "tap_boot.management.commands.cold_boot_gate",
     })

     def _assert_invoked_via_boot_command() -> None:
         frame = sys._getframe(1)
         while frame is not None:
             cmd = frame.f_locals.get("self")
             if isinstance(cmd, BaseCommand) and type(cmd).__module__ in _ALLOWED_BOOT_COMMANDS:
                 return  # confirmed positive
             frame = frame.f_back
         raise BootError("run_boot must run via `manage.py boot`/`cold_boot_gate`, not be called directly")
     ```

     Why this is positive-not-fragile: it confirms the *actual call chain* passes
     through a real `BaseCommand` of a named command — not the absence of something.
     `BaseCommand.execute → handle` is **stable public Django API**, not an internal
     frame (this corrects an earlier over-broad "stack inspection is fragile" worry —
     that's true of arbitrary internals, not of the management-command boundary). Keying
     on `type(cmd).__module__` + `isinstance(BaseCommand)` survives Django file-layout
     changes. Forge cost is far higher than a contextvar/env marker — you'd have to get a
     real `BaseCommand` subclass instance of the right module into a live frame — while
     still not defending against a determined in-process attacker (out of the honest
     threat model; they'd call `_impl` directly). Covers **both** real callers
     (`manage.py boot`; `cold_boot_gate` calling `run_boot` from `_step_boot_test_all`
     with its own Command still up-stack) and legitimately passes `call_command("boot")`.
   - **Test carve (named, not hidden):** tests call `run_boot` directly → no command
     frame → would fail. Add an explicit bypass keyed on the trusted test environment
     (`settings.TESTING` / `PYTEST_CURRENT_TEST`), named as a deliberate carve.
   - **Re-entrancy → a module-level run-once sentinel** (`_BOOT_INVOKED` flipped on first
     entry; a second in-process `run_boot` errors). The stack check passes a *legitimate*
     second invocation within one command run, so double-boot protection is separate: the
     stack check answers "is this a real boot invocation," the sentinel answers "is this
     the *first* one." **Neither exists today** — no run-once guard, lock, or context
     check is present in tap_boot.
   - **Optional secondary — request-context absence.** At `run_boot` entry, before it
     binds its actor via `acting_as(bootloader)` (`orchestrator.py:71-72`), a legit CLI
     boot has no ambient caller context (`tap_grid.caller_context.get_caller_context()` →
     `None`; ContextVar at `tap_grid/caller_context.py:37`); an in-request invocation
     carries a request-bound `CallerContext` from `CallerContextMiddleware`
     (`tap_auth/middleware.py:51-55`). This only *adds* coverage for the contrived
     "`call_command('boot')` wired into a live view" case the stack check would pass;
     it's the ambient analogue of `write_guard` but weaker (evidence-of-absence). Keep as
     defense-in-depth, not the primary signal.
   - **`apps.ready` is the WRONG signal** — reject it. It is `True` during legitimate
     boot *and* `True` in a web worker serving a request, so `assert apps.ready`
     **false-passes the exact threat**. (tap_boot has no `AppConfig.ready()`, so the
     negative form guards a case that can't occur here either.)
   - **Prefer confirmed-positive / ambient facts over a caller-set marker** — a marker is
     a paddable *declaration* the bad caller can also set; the stack chain and ambient
     contextvars are harder-to-forge *structural facts* (same instinct as
     `spec-tap-callsite-identity`). Belt-and-suspenders process-role certainty beyond the
     management-command frame would require a trusted entrypoint-set marker — accept and
     **name** that it's a declaration, not a structural fact.
   - **Honest threat model:** the primary value is catching **accidental / out-of-band
     re-invocation** (a plugin/test/mgmt-command re-running boot mid-flight and
     corrupting boot-time state), **not** stopping an in-process attacker (who has
     bigger levers than re-calling boot). State that plainly; don't overclaim it as an
     attack mitigation.
   - Illegitimate *context* → error, loud; already-done idempotent work → no-op.

---

## Cross-cutting: the convention's own machinery is still unbuilt

Any Family-A adopter today would be adopting a convention whose enforcement is itself
still being generalized. Blockers to resolve first (or alongside the first new adopter):

- **No `__all__` on the grid gateway yet.** `tap_grid/guards/service_gateway.py:4`
  literally says "Until `tap_grid.services.__all__` exists" it uses non-`_` top-level
  defs as the export inventory proxy.
- **No `__tap_contract_modules__` marker exists anywhere** — the zone-declaration
  primitive is unbuilt.
- **The shared/discovered boundary guard doesn't exist.**
  `tap_grid/guards/service_gateway.py:21` is hardcoded to `tap_grid/services/`. It must
  be lifted to filesystem discovery of `<app>/services/` +
  `__tap_contract_modules__`-awareness + the well-formed-boundary / opt-out checks
  before tap_cares/tap_auth/tap_plugins can get *any* enforcement from adopting.
- **The import-encapsulation guard doesn't exist** (see Family B #2) — a gap for *both*
  families, but load-bearing for Family B.

---

## Suggested sequencing

1. **Generalize the guard** off the hardcoded grid path (`req-service-boundary-guard`
   / `-discovery`) and land the `__all__` + `__tap_contract_modules__` primitives on the
   *existing* grid instance. Nothing new adopts safely until this exists.
2. **tap_cares first (5/5)** — highest payoff, natural package boundary, already a
   partial adopter; proves the convention generalizes on a real second consumer.
3. **Build the two Family-B controls** (public-surface ceiling ratchet +
   import-encapsulation guard) and **seal `tap/preboot.py`** — cheap, high-value, and
   the ceiling ratchet is buildable on existing rails today.
4. **tap_auth (3/5)** — the spec-named adopter; smaller gateway but proves the
   opt-out (`sync.py`) and gate-machinery-carve-out (`policy`/`enforcement`/`actors`)
   patterns, and lets us clean the `enforcement.py:42` sideways coupling.
5. **tap_plugins (3/5)** — convert the inline authorize, give `seed_plugin` its own
   composing gate.
6. **Plugin tier** — leave `Proposed`; adopt when `lotr` (or another) grows its own
   capability. `lotr` is the pre-designated pilot.

---

## Appendix — what legitimately stays *out* of the convention

Named deliberately so the survey doesn't imply completeness (honest-risk discipline):

- `tap_auth/sync.py` — migration-class bootstrap; reviewed **opt-out**.
- `tap_auth` `policy`/`enforcement`/`actors` — the gate machinery; can't gate the gate.
- `tap_boot` `run_boot` — mints the capability system; Family B, minimize not gate.
- `tap/preboot.py`, `tap/plugin_source_auth.py` — pre-auth substrate; Family B.
- secrets resolver, tap_health — read-only, no mutation front-door.
- `register_collector`/`get_collector`, `load_manifest`/`validate_manifest_classes` —
  in-memory / pure-parse, no grid, no auth.
- The plugin tier — inherits the grid boundary until it grows an owned capability.
