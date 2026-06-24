---
title: tap_boot Implementation — Session Handoff
date: 2026-06-24
status: handoff
audience:
  - llm
  - developer
related_docs:
  - docs/misc/doc-auth-per-app-standards.md
related_specs:
  - specs/spec-tap-boot-v0.md
  - tap_auth/specs/spec-tap-auth-v0.md
---

# tap_boot Implementation — Session Handoff

> **✅ LANDED (2026-06-24).** tap_boot v0 is implemented, tested, and bridged into `spawn-session.sh`.
> See the "Status — v0 landed" note in **`specs/spec-tap-boot-v0.md`** for the as-built summary
> (command, ordered-steps profile, reused/new ops, tests, live samsite proof). This handoff is now a
> historical planning artifact.

> **⚠️ SUPERSEDED (2026-06-24).** This handoff's *layering* is wrong: it places the boot section
> primitive + identity handler in `tap_grid`. The corrected design is **`tap_boot` owns ALL boot
> logic** (domain apps stay boot-agnostic and merely expose ops boot calls), and v0 scope is
> downsized to **minimal-useful**. Follow the corrected **`specs/spec-tap-boot-v0.md`** (its "v0
> Scope" section) and the `tap-boot-architecture` memory — **not** this document's layering/scope.
> Retained only for its still-accurate reuse-point inventory (existing ops, signatures, and which
> logic is trapped in management commands).

Build the `tap_boot` app: one declarative `manage.py boot` that stands a TAP instance up from a
fresh DB to a populated, usable system — superseding the ordered bash steps in
`spawn-session.sh`. This is **item 2 of `step-rampart-launch-ready`** (mid-July, TAP functionally
complete). Read **`specs/spec-tap-boot-v0.md`** first (all 12 reqs `Proposed`); this handoff is the
scoped plan + the decisions already made, so the build doesn't re-derive them.

## Why it's not from-zero

The boot **operations already exist** and work (the bash spawn proves it): `sync_auth`,
`import_plugin_grift`, `reconcile_collector_nodes()` (a function), `fire_boot_collectors`. tap_boot
is the **orchestration framework** around them — declarative profile, phases, schema-validated,
one actor context. So it's "build the machinery + wire existing ops," not greenfield logic.

## The LOCKED 80/20 cut (George, 2026-06-24)

Do the high-value machinery + wiring now; defer the disproportionate-cost robustness/authN items.
George's one amendment to the original cut: **per-section JSON-Schema composition is IN, not
deferred — "everything should have a schema, always."**

### In the consolidated push (~5–7 focused days)

- **`tap_boot` app + `manage.py boot --profile <name>` + `--dry-run`** (offline: validate + plan, no mutation).
- **Boot context** — a `bootstrap` pre-phase ensures `tap_bootloader` exists + holds its
  `BOOTLOADER_BUNDLE` (least-privilege; no `grid.purge`/`grid.delete`), then the whole run executes
  under one `acting_as(BOOTLOADER)`. This is the proper home that **consolidates** the
  `acting_as(BOOTLOADER)` bindings currently scattered in `reconcile_collectors` / `fire_boot_collectors`.
- **Section-handler primitive (lives in `tap_grid`, `req-boot-app-4`):** a flat `Registry`
  (`tap_grid/registry.py` `Registry`, duplicate key → `ImproperlyConfigured`, no merge_fn) +
  a `BootSectionHandler` base bundling `section_key`, a **mandatory** JSON Schema fragment, and
  `validate(data)` / `plan(data)` / `apply(data)`. Registering without a schema = error
  (`req-boot-sections-3`). Each handler gets **only its own section's data** (config isolation).
- **Fixed phase order** (code, not config): `bootstrap → identity → auth → population`.
- **Multi-section profile** envelope + loader (supersedes the flat `tap_cares/schemas/boot-profile.schema.json`).
- **Two-layer validation, both before any mutation** (`req-boot-validate`): (1) **schema** — compose
  registered handlers' fragments into the envelope schema, validate strictly (`additionalProperties:false`,
  unknown sections/fields fail loud); (2) **semantic** — each handler's `validate` resolves refs /
  catches impossible config / unknown plugin-collector-secret keys up front. Errors name the offending location.
- **Section handlers (wrap existing ops):**
  - `identity` → **tap_grid**: write the instance keystone (`spec-grid-keystone.md`, create-or-update) as bootloader, guaranteed before population.
  - `auth` → **tap_auth**: `sync_auth` (caps/groups/actors) + initial admin. **No provider config — that's the authN track.**
  - `population` → **tap_boot**-owned dispatcher: ordered steps `seed-plugin` (`import_plugin_grift`) + `fire-collector` (`run_collection`); strictly ordered, sequential, interleavable; unknown key aborts before any step.
- **Secret references** → resolved from `TAP_SECRETS_ROOT` (mechanism exists; wire profile refs → resolution).
- **Spawn bridge** — replace `spawn-session.sh` Steps 5.9–6.5 (`sync_auth` / `import_plugin_grift` /
  `reconcile_collectors` / `fire_boot_collectors`) with one `manage.py boot --profile`.
- **Redacted boot logging** (actions logged, secrets never).

### Deferred (the expensive 20% — named, pick off later)

| Deferred | Why |
| --- | --- |
| Formal idempotency contract + convergence tests (`req-boot-idempotent`) | Ops are idempotent in practice (sync_auth, reconcile, keystone create-or-update, GRIFT); the guaranteed "every section converges" contract is the long tail. |
| GRIFT edited-bundle convergence (version-bumped batches + DEBUG force-reimport, `req-boot-population-6`) | Rely on batch identity for now; **name the caveat** (edited-but-not-bumped silently skips). |
| Provider validation / self-tests in the `auth` section (`req-tap-auth-providers`) | The authN provider framework — lands with the login work, not here. |
| Live checks (`--live-checks`: provider reachability, OIDC discovery, upstream probes) | authN-coupled. `--dry-run` stays offline-only. |
| Durable boot report (`req-boot-report`) | Spec already defers; log-only now. |

## Layering (decided)

- **tap_grid** owns the *primitive*: `boot_section_registry` (a `Registry` instance) + `BootSectionHandler`
  base, **and** the `identity` handler. (tap_grid is the core; everyone depends on it — putting the
  base here avoids a backward `tap_grid → tap_boot` dependency.)
- **tap_boot** (new app) owns orchestration: `manage.py boot`, the phase sequencer, profile loader,
  schema-composition + validation runner, the boot context, **and** the `population` handler.
- **tap_auth** owns the `auth` handler.
- `INSTALLED_APPS`: add `tap_boot` (it orchestrates tap_auth/tap_grid/tap_cares/tap_plugins, so after them).

## Reuse points

- `tap_grid/registry.py` `Registry` (flat, duplicate → `ImproperlyConfigured`).
- `tap_auth.sync.sync_auth()` (idempotent) for `auth`; factor a `bootstrap_bootloader()` (ensure
  *just* `tap_bootloader` + `BOOTLOADER_BUNDLE`) for the `bootstrap` pre-phase — the first-actor
  chicken-and-egg is a low-level write below the named-actor contract (`req-boot-phases`).
- `tap_auth.actors.acting_as` + `get_builtin_actor(BOOTLOADER)` for the boot context.
- `tap_cares.registry.reconcile_collector_nodes()` (function) for population reconcile.
- `import_plugin_grift` + `fire_boot_collectors` — factor callable functions out of the commands if
  the logic isn't already function-accessible.
- `jsonschema` (already a dep) for schema validation; `spec-grid-keystone.md` for the identity keystone.

## Build sequence (bottom-up)

1. tap_grid: `boot_section_registry` + `BootSectionHandler` base (the primitive).
2. tap_boot app skeleton + the boot context (`bootstrap` + `acting_as`).
3. Profile envelope + loader + schema composition + the two-layer validation runner.
4. Phase sequencer (`bootstrap → identity → auth → population`).
5. Section handlers: `identity` (tap_grid), `auth` (tap_auth), `population` (tap_boot).
6. `manage.py boot` (`--profile`, `--dry-run`).
7. Spawn bridge (`spawn-session.sh`).
8. Tests + flip the relevant `spec-tap-boot-v0` req statuses `Proposed → Implemented`.

## Done-test

A profile (samsite) that boots an instance **equivalent to the current bash spawn** — capabilities/
actors synced, instance keystone laid down, plugins seeded, collector nodes reconciled, boot
collectors fired — via `manage.py boot --profile samsite`, with `--dry-run` reporting the plan
without mutating. Compare the result against a current bash-spawn instance.

## After this

Then the authN/login work (Google OIDC + a login page) — the other launch-gate auth item, entirely
unbuilt; the `auth` section's provider config is its boot-side seam. See `doc-auth-session-handoff.md`
(authZ, mostly done) and `spec-tap-auth-v0.md` providers/google-oidc/local sections (the steps).
